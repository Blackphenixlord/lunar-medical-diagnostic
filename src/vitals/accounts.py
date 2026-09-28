"""Who can use VITALS, and how they prove it: a PIN.

WHAT LIVES HERE
    - Accounts: a name, a role, a hashed PIN, and (for crew) a profile.
    - Checking a PIN, with a short lockout after too many wrong tries.
    - Sessions: a random token handed to the browser as a cookie after login.

WHAT DOES NOT
    Anything medical. The server asks this module "who is this?" and nothing more.

ROLES
    astronaut    uses the astronaut screen (AUI) and can ask VITALS
    ground       ground crew screen (not built yet)
    doctor       doctor screen (not built yet)

ONE PIN PER PERSON
    A login is a PIN with no username, so two people may not share a PIN.
    Per-person PINs are also what let a report say who withheld what and who
    reviewed it - a shared "ground crew PIN" could not.

PINS ARE NEVER STORED
    Only a salted PBKDF2 hash (Python's built-in hashlib, no extra install).
    Real accounts live in accounts.json, which is gitignored. The repo ships
    accounts.example.json with demo accounts so a fresh clone still works.

EMERGENCY ACCESS
    A crewmember who is hurt or panicking must not be locked out of help by a
    forgotten PIN. `start_emergency_session()` opens the astronaut screen as an
    unnamed crewmember. It sees no profile and no history, and the ground crew
    will see the case marked as emergency access.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCOUNTS_FILE = Path(os.environ.get("VITALS_ACCOUNTS", REPO_ROOT / "accounts.json"))
EXAMPLE_ACCOUNTS_FILE = REPO_ROOT / "accounts.example.json"

ROLES = ("astronaut", "ground", "doctor")

PIN_MIN_DIGITS = 4
PIN_MAX_DIGITS = 6

# Lockout: after this many wrong PINs from one screen, make it wait.
MAX_WRONG_TRIES = 5
LOCKOUT_SECONDS = 30

# Sign out a session nobody has used for this long. Station screens are shared.
IDLE_TIMEOUT_SECONDS = 10 * 60

# PBKDF2 work factor. High enough to slow guessing, low enough that a login on
# a Raspberry Pi still takes well under a second per account.
HASH_ITERATIONS = 100_000


class AccountError(Exception):
    """A problem with the accounts file or with adding an account."""


# --- PINs --------------------------------------------------------------------

def is_valid_pin(pin: str) -> bool:
    return pin.isdigit() and PIN_MIN_DIGITS <= len(pin) <= PIN_MAX_DIGITS


def hash_pin(pin: str) -> str:
    """Return 'pbkdf2$<iterations>$<salt hex>$<hash hex>'."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, HASH_ITERATIONS)
    return f"pbkdf2${HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def pin_matches(pin: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(digest.hex(), digest_hex)   # constant-time compare


# --- accounts ----------------------------------------------------------------

@dataclass
class Account:
    id: str
    name: str
    role: str
    pin_hash: str
    profile: dict[str, Any] = field(default_factory=dict)


def accounts_path() -> Path:
    """The real accounts file if it exists, otherwise the demo one."""
    return ACCOUNTS_FILE if ACCOUNTS_FILE.exists() else EXAMPLE_ACCOUNTS_FILE


def load_accounts(path: Optional[Path] = None) -> list[Account]:
    path = Path(path) if path else accounts_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise AccountError(f"no accounts file at {path}") from None
    except json.JSONDecodeError as exc:
        raise AccountError(f"{path} is not valid JSON: {exc}") from None

    accounts = []
    for entry in raw.get("accounts", []):
        account = Account(
            id=entry["id"],
            name=entry["name"],
            role=entry["role"],
            pin_hash=entry["pin_hash"],
            profile=entry.get("profile", {}),
        )
        if account.role not in ROLES:
            raise AccountError(f"account {account.id}: unknown role '{account.role}'")
        accounts.append(account)
    return accounts


def add_account(path: Path, account_id: str, name: str, role: str, pin: str,
                profile: Optional[dict] = None) -> None:
    """Add one account to an accounts file, creating the file if needed."""
    if role not in ROLES:
        raise AccountError(f"role must be one of {', '.join(ROLES)}")
    if not is_valid_pin(pin):
        raise AccountError(f"PIN must be {PIN_MIN_DIGITS}-{PIN_MAX_DIGITS} digits")

    existing = load_accounts(path) if Path(path).exists() else []
    if any(a.id == account_id for a in existing):
        raise AccountError(f"an account with id '{account_id}' already exists")
    if any(pin_matches(pin, a.pin_hash) for a in existing):
        raise AccountError("someone already uses that PIN - pick another")

    entries = [a.__dict__ for a in existing]
    entries.append({"id": account_id, "name": name, "role": role,
                    "pin_hash": hash_pin(pin), "profile": profile or {}})
    Path(path).write_text(json.dumps({"accounts": entries}, indent=2) + "\n", encoding="utf-8")


# --- sessions ----------------------------------------------------------------

@dataclass
class Session:
    token: str
    account_id: Optional[str]      # None for emergency access
    name: str
    role: str
    profile: dict[str, Any]
    emergency: bool = False
    last_seen: float = field(default_factory=time.time)

    def public(self) -> dict[str, Any]:
        """What the browser is allowed to know about the person logged in."""
        return {"name": self.name, "role": self.role,
                "emergency": self.emergency, "profile": self.profile}


class LoginDesk:
    """Checks PINs, counts wrong tries, and keeps the list of live sessions.

    One of these lives in the server. The HTTP server is threaded, so every
    change to shared state happens under a lock.
    """

    def __init__(self, accounts: list[Account], clock=time.time):
        self.accounts = accounts
        self.clock = clock                      # swappable so tests can move time
        self._sessions: dict[str, Session] = {}
        self._wrong_tries: dict[str, int] = {}  # per screen (client address)
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    # login ---------------------------------------------------------------

    def seconds_locked(self, client: str) -> int:
        remaining = self._locked_until.get(client, 0) - self.clock()
        return max(0, int(remaining + 0.999))

    def log_in(self, pin: str, client: str) -> Session:
        """Return a new session, or raise LoginRefused with a message for the screen."""
        wait = self.seconds_locked(client)
        if wait:
            raise LoginRefused(f"Too many wrong PINs. Try again in {wait} seconds.", wait)

        account = next((a for a in self.accounts if pin_matches(pin, a.pin_hash)), None)

        with self._lock:
            if account is None:
                tries = self._wrong_tries.get(client, 0) + 1
                self._wrong_tries[client] = tries
                if tries >= MAX_WRONG_TRIES:
                    self._wrong_tries[client] = 0
                    self._locked_until[client] = self.clock() + LOCKOUT_SECONDS
                    raise LoginRefused(
                        f"Too many wrong PINs. Try again in {LOCKOUT_SECONDS} seconds.",
                        LOCKOUT_SECONDS)
                raise LoginRefused("Wrong PIN.")

            self._wrong_tries.pop(client, None)
            return self._open(Session(token=secrets.token_urlsafe(32), account_id=account.id,
                                      name=account.name, role=account.role,
                                      profile=account.profile, last_seen=self.clock()))

    def start_emergency_session(self) -> Session:
        with self._lock:
            return self._open(Session(token=secrets.token_urlsafe(32), account_id=None,
                                      name="Unnamed crewmember", role="astronaut",
                                      profile={}, emergency=True, last_seen=self.clock()))

    def _open(self, session: Session) -> Session:
        self._sessions[session.token] = session
        return session

    # every request -------------------------------------------------------

    def session_for(self, token: Optional[str]) -> Optional[Session]:
        """The live session for a cookie token, or None. Using it keeps it alive."""
        if not token:
            return None
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if self.clock() - session.last_seen > IDLE_TIMEOUT_SECONDS:
                del self._sessions[token]
                return None
            session.last_seen = self.clock()
            return session

    def log_out(self, token: Optional[str]) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)


class LoginRefused(Exception):
    def __init__(self, message: str, retry_after: int = 0):
        super().__init__(message)
        self.retry_after = retry_after
