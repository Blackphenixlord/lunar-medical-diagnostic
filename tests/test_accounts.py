"""PIN login: hashing, lockout, sessions, emergency access."""

import json

import pytest

from vitals import accounts
from vitals.accounts import (Account, AccountError, LoginDesk, LoginRefused, add_account,
                             hash_pin, is_valid_pin, load_accounts, pin_matches)


class Clock:
    """A clock the test can move forward, so nobody waits 30 real seconds."""
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def desk(clock):
    return LoginDesk([
        Account("a1", "Astronaut One", "astronaut", hash_pin("1234"), {"Height": "170 cm"}),
        Account("g1", "Ground One", "ground", hash_pin("5678")),
    ], clock=clock)


# --- PINs -------------------------------------------------------------------

def test_pin_is_never_stored_in_plain_text():
    stored = hash_pin("1234")
    assert "1234" not in stored
    assert stored.startswith("pbkdf2$")


def test_same_pin_hashes_differently_each_time():
    """Salted: two people's hashes cannot be compared to find a shared PIN."""
    assert hash_pin("1234") != hash_pin("1234")


def test_pin_matches_only_the_right_pin():
    stored = hash_pin("1234")
    assert pin_matches("1234", stored)
    assert not pin_matches("1235", stored)
    assert not pin_matches("1234", "garbage")


@pytest.mark.parametrize("pin,ok", [("1234", True), ("123456", True), ("123", False),
                                    ("1234567", False), ("12a4", False), ("", False)])
def test_pin_length_and_digits(pin, ok):
    assert is_valid_pin(pin) is ok


# --- logging in -------------------------------------------------------------

def test_right_pin_opens_a_session_for_that_person(desk):
    session = desk.log_in("1234", client="screen-1")
    assert session.name == "Astronaut One"
    assert session.role == "astronaut"
    assert desk.session_for(session.token) is session


def test_wrong_pin_is_refused(desk):
    with pytest.raises(LoginRefused):
        desk.log_in("0000", client="screen-1")


def test_five_wrong_pins_lock_that_screen_for_30_seconds(desk, clock):
    for _ in range(accounts.MAX_WRONG_TRIES - 1):
        with pytest.raises(LoginRefused) as exc:
            desk.log_in("0000", client="screen-1")
        assert exc.value.retry_after == 0

    with pytest.raises(LoginRefused) as exc:
        desk.log_in("0000", client="screen-1")
    assert exc.value.retry_after == accounts.LOCKOUT_SECONDS

    # Even the right PIN waits out the lockout...
    with pytest.raises(LoginRefused):
        desk.log_in("1234", client="screen-1")
    # ...but another screen is not affected...
    assert desk.log_in("1234", client="screen-2")
    # ...and after the wait the first screen works again.
    clock.now += accounts.LOCKOUT_SECONDS + 1
    assert desk.log_in("1234", client="screen-1")


def test_idle_session_expires(desk, clock):
    session = desk.log_in("1234", client="screen-1")
    clock.now += accounts.IDLE_TIMEOUT_SECONDS - 1
    assert desk.session_for(session.token) is not None      # still in use: stays alive
    clock.now += accounts.IDLE_TIMEOUT_SECONDS + 1
    assert desk.session_for(session.token) is None


def test_log_out_ends_the_session(desk):
    session = desk.log_in("1234", client="screen-1")
    desk.log_out(session.token)
    assert desk.session_for(session.token) is None


def test_unknown_or_missing_token_has_no_session(desk):
    assert desk.session_for(None) is None
    assert desk.session_for("not-a-real-token") is None


def test_emergency_session_is_an_unnamed_astronaut_with_no_profile(desk):
    session = desk.start_emergency_session()
    assert session.role == "astronaut"
    assert session.emergency is True
    assert session.profile == {}
    assert session.account_id is None


def test_public_view_never_includes_the_pin_hash(desk):
    session = desk.log_in("1234", client="screen-1")
    assert "pin" not in json.dumps(session.public()).lower()


# --- the accounts file ------------------------------------------------------

def test_add_account_then_load_it(tmp_path):
    path = tmp_path / "accounts.json"
    add_account(path, "a1", "Alex", "astronaut", "2468", {"Height": "180 cm"})
    [account] = load_accounts(path)
    assert account.name == "Alex"
    assert pin_matches("2468", account.pin_hash)
    assert "2468" not in path.read_text()


def test_two_people_cannot_share_a_pin(tmp_path):
    """Login is PIN-only, so a shared PIN would log in as the wrong person."""
    path = tmp_path / "accounts.json"
    add_account(path, "a1", "Alex", "astronaut", "2468")
    with pytest.raises(AccountError):
        add_account(path, "a2", "Sam", "astronaut", "2468")


@pytest.mark.parametrize("role,pin", [("pilot", "2468"), ("astronaut", "12")])
def test_bad_role_or_pin_is_refused(tmp_path, role, pin):
    with pytest.raises(AccountError):
        add_account(tmp_path / "accounts.json", "a1", "Alex", role, pin)


def test_the_demo_accounts_file_loads_and_covers_every_role():
    loaded = load_accounts(accounts.EXAMPLE_ACCOUNTS_FILE)
    assert {a.role for a in loaded} == set(accounts.ROLES)


def test_docker_image_ships_the_demo_accounts():
    """Found 27 Sep: the Dockerfile copied src/kb/prompts but not the accounts
    file, so the server would refuse to start inside Docker and on the Jetson."""
    dockerfile = (accounts.REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY accounts.example.json" in dockerfile
