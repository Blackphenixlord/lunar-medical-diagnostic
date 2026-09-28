"""The browser interface.

Stdlib only - http.server, no Flask, no npm, no build step. That is a
requirement, not laziness: this has to run on a Jetson and two Raspberry Pis
that may have no working internet, and every dependency is one more thing that
can fail on the vehicle.

    python -m vitals serve      ->  http://127.0.0.1:8000

ROUTES
    GET  /              PIN login
    GET  /astronaut     astronaut screen (AUI)
    GET  /dev           the original developer page: full trace, cross-check
    GET  /api/health    is the KB loaded, is ollama up, what models exist
    GET  /api/examples  the prompt bank, so the UI can offer real complaints
    GET  /api/me        who is logged in (401 if nobody)
    POST /api/login     {"pin": "1234"} -> sets the session cookie
    POST /api/emergency skip the PIN: astronaut screen as an unnamed crewmember
    POST /api/logout
    POST /api/ask       {"complaint": "...", "model": "...",
                         "corrections": {"back_pain": false}} -> the full answer
                        (needs an astronaut session; corrections are optional)

LOGIN
    Pages are just code and are served to anyone; the DATA is what is
    protected. Every API call that touches a person or asks the model checks
    the session cookie here, on the server. Hiding a button in the browser is
    not security - anyone can call the API directly.

THE SERVER OWNS NO MEDICAL LOGIC WHATSOEVER. It is a thin shell around exactly
the same pipeline the CLI uses, so the UI can never drift from what
`vitals ask` does. If they ever disagree, that is a bug in this file.
"""

from __future__ import annotations

import json
import re
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import sensors
from .accounts import LoginDesk, LoginRefused, load_accounts
from .engine import diagnose
from .extract import KeywordExtractor
from .knowledge_base import KnowledgeBaseError, load_knowledge_base
from .ollama_client import DEFAULT_MODEL, OLLAMA_HOST, OllamaUnavailable, list_models
from .reason import ask
from .retrieval import retrieve

UI_DIR = Path(__file__).parent / "ui"

RETRIEVAL_LIMIT = 6

SESSION_COOKIE = "vitals_session"

# Which screen each role opens after login. Ground crew and doctor screens are
# not built yet, so they have no page; the login screen says so.
ROLE_PAGES = {"astronaut": "/astronaut", "ground": None, "doctor": None}

# Who may ask the model. The ground crew and doctor screens will add their own.
ASK_ROLES = {"astronaut"}

PAGES = {
    "/": "login.html",
    "/index.html": "login.html",
    "/astronaut": "astronaut.html",
    "/dev": "dev.html",
}


def run_pipeline(knowledge_base, complaint: str, model: str,
                 corrections: dict[str, bool] | None = None) -> dict[str, Any]:
    """The exact same sequence as `cmd_ask`. One pipeline, two front ends.

    `corrections` is the crewmember fixing a finding the extractor got wrong
    ("I said NO back pain"). It is applied after extraction, so it always wins.
    """
    started = time.time()

    observations = KeywordExtractor().extract(complaint, knowledge_base)
    observations.update(sensors.as_observations(sensors.read_all()))
    observations.update(clean_corrections(knowledge_base, corrections))

    retrieved = retrieve(knowledge_base, complaint, observations, limit=RETRIEVAL_LIMIT)
    answer = ask(knowledge_base, complaint, retrieved, observations=observations, model=model)
    readable = _readable_text(knowledge_base)

    return {
        "ok": True,
        "elapsed": round(time.time() - started, 1),
        "model": answer.model,
        "sensor_status": answer.sensor_status,
        "escalate": answer.escalate,
        "escalation_reason": readable(answer.escalation_reason),
        "escalation": _escalation_summary(knowledge_base, answer),
        "uncertainty": readable(answer.uncertainty),
        "next_questions": answer.next_questions,
        "dropped": answer.dropped,
        "known": _known_findings(knowledge_base, observations),
        "differential": [
            {
                "id": candidate.condition_id,
                "name": candidate.name,
                "urgency": candidate.urgency,
                "confidence": candidate.confidence,
                "reasoning": readable(candidate.reasoning),
                "supporting": [readable(text) for text in candidate.supporting],
                "against": [readable(text) for text in candidate.against],
                "recommend": candidate.recommend,
                "sources": candidate.sources,
            }
            for candidate in answer.differential
        ],
        "trace": {
            "findings": dict(sorted(observations.items())),
            "retrieved": [
                {
                    "id": item.id,
                    "name": item.condition.name,
                    "score": round(item.score, 1),
                    "why": item.why,
                }
                for item in retrieved
            ],
            "crosscheck": _crosscheck(knowledge_base, observations, answer),
        },
    }



def _escalation_summary(knowledge_base, answer) -> dict[str, Any]:
    """The alarm, as data the screen can act on.

    `level` is the most serious urgency among the conditions the escalation is
    about (at least "urgent" whenever it escalates), and `conditions` lists
    those conditions with their advice and sources from the KB. The screen
    leads with these - it must never show shoulder advice under a DCS alarm
    just because the model ranked shoulder first.
    """
    if not answer.escalate:
        return {"level": "none", "conditions": []}

    conditions = []
    for condition_id in answer.escalated_ids:
        condition = knowledge_base.conditions.get(condition_id)
        if condition is None:
            continue
        conditions.append({
            "id": condition_id,
            "name": condition.name,
            "urgency": condition.urgency,
            "recommend": condition.recommend,
            "sources": condition.sources,
        })

    # Most serious first.
    order = {"emergency": 0, "urgent": 1, "monitor": 2, "routine": 3}
    conditions.sort(key=lambda c: order.get(c["urgency"], 4))

    level = "urgent"
    if conditions and conditions[0]["urgency"] == "emergency":
        level = "emergency"
    return {"level": level, "conditions": conditions}


def _readable_text(knowledge_base):
    """Swap raw condition ids the model wrote ("msk_shoulder_overuse") for names.

    Acceptance criteria 2.1: the crew never sees a KB id. The model is told to
    use ids, so it sometimes leaks them into its own sentences.
    """
    names = {condition_id: condition.name
             for condition_id, condition in knowledge_base.conditions.items()}
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b") if names else None

    def readable(text: str) -> str:
        if not text or pattern is None:
            return text
        return pattern.sub(lambda match: names[match.group(1)], text)

    return readable


def clean_corrections(knowledge_base, corrections) -> dict[str, bool]:
    """Keep only present/absent corrections to real findings. Anything else is ignored.

    The browser sends these, so they are untrusted: an unknown finding id or a
    value other than true/false never reaches the pipeline. Scale findings
    (0-10) are allowed too, because the extractor records those as plain
    present/absent when no number was given ("my back hurts" -> back_pain: True).
    """
    cleaned = {}
    for finding_id, value in (corrections or {}).items():
        definition = knowledge_base.findings.get(finding_id)
        if definition is None or definition.type not in ("bool", "scale"):
            continue
        if isinstance(value, bool):
            cleaned[finding_id] = value
    return cleaned


def _known_findings(knowledge_base, observations: dict) -> list[dict[str, str]]:
    """What the system believes it knows, in the KB's own words, for the screen.

    Same data as trace.findings, but with the human label instead of the raw
    id, so the crew screen never has to show `hematuria: True`.
    """
    known = []
    for finding_id, value in sorted(observations.items()):
        definition = knowledge_base.findings.get(finding_id)
        label = definition.label if definition else finding_id
        if isinstance(value, bool):
            shown = "yes" if value else "no"
        elif definition and definition.type == "scale":
            shown = f"{value} / 10"
        elif definition and definition.unit:
            shown = f"{value} {definition.unit}"
        else:
            shown = str(value)
        # The "Wrong?" button flips yes/no, so only plain yes/no items get one.
        correctable = isinstance(value, bool) and definition is not None \
            and definition.type in ("bool", "scale")
        known.append({"id": finding_id, "label": label, "value": shown,
                      "correctable": correctable})
    return known


def _crosscheck(knowledge_base, observations: dict, answer) -> dict[str, str]:
    """How the deterministic engine voted on the same observations."""
    result = diagnose(knowledge_base, observations)
    engine_top = result.top.id if result.top else None

    if engine_top is None:
        return {
            "state": "insufficient",
            "text": "engine had too little to go on (it only sees extracted findings)",
        }

    engine_name = knowledge_base.conditions[engine_top].name

    if answer.top is None:
        return {
            "state": "insufficient",
            "text": f"engine says {engine_name}, model returned nothing",
        }
    if engine_top == answer.top.condition_id:
        return {"state": "agree", "text": f"agrees: {engine_name}"}

    return {
        "state": "disagree",
        "text": f"engine says {engine_name}, model says {answer.top.name}",
    }


class Handler(BaseHTTPRequestHandler):
    """Routing and JSON encoding. Nothing else belongs in here."""

    kb = None
    model = DEFAULT_MODEL
    desk: LoginDesk = None

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    # --- responses ---

    def _send(self, code: int, body: bytes, content_type: str,
              headers: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict, headers: dict | None = None) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"),
                   "application/json; charset=utf-8", headers)

    # --- request helpers ---

    def _body(self) -> dict:
        """The JSON request body. Raises ValueError if it is not JSON."""
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def _token(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie[SESSION_COOKIE].value if SESSION_COOKIE in cookie else None

    def _session(self):
        return self.desk.session_for(self._token())

    @staticmethod
    def _cookie(token: str, max_age: int | None = None) -> dict:
        """HttpOnly: page scripts cannot read it. SameSite=Strict: other sites cannot send it."""
        parts = [f"{SESSION_COOKIE}={token}", "Path=/", "HttpOnly", "SameSite=Strict"]
        if max_age is not None:
            parts.append(f"Max-Age={max_age}")
        return {"Set-Cookie": "; ".join(parts)}

    # --- routes ---

    def do_GET(self):
        if self.path in PAGES:
            return self._send(200, (UI_DIR / PAGES[self.path]).read_bytes(),
                              "text/html; charset=utf-8")
        if self.path == "/api/examples":
            return self._json(200, {"prompts": self._example_prompts()})
        if self.path == "/api/health":
            return self._json(200, self._health())
        if self.path == "/api/me":
            return self._me()
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        routes = {
            "/api/login": self._login,
            "/api/emergency": self._emergency,
            "/api/logout": self._logout,
            "/api/ask": self._ask,
        }
        route = routes.get(self.path)
        if route is None:
            return self._json(404, {"error": "not found"})
        try:
            payload = self._body()
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"ok": False, "error": "bad JSON"})
        return route(payload)

    # --- route bodies: login ---

    def _login(self, payload: dict):
        pin = str(payload.get("pin", ""))
        try:
            session = self.desk.log_in(pin, client=self.client_address[0])
        except LoginRefused as exc:
            code = 429 if exc.retry_after else 401
            return self._json(code, {"ok": False, "error": str(exc),
                                     "retry_after": exc.retry_after})
        return self._json(200, {"ok": True, **session.public(),
                                "page": ROLE_PAGES.get(session.role)},
                          self._cookie(session.token))

    def _emergency(self, payload: dict):
        session = self.desk.start_emergency_session()
        return self._json(200, {"ok": True, **session.public(), "page": ROLE_PAGES["astronaut"]},
                          self._cookie(session.token))

    def _logout(self, payload: dict):
        self.desk.log_out(self._token())
        return self._json(200, {"ok": True}, self._cookie("", max_age=0))

    def _me(self):
        session = self._session()
        if session is None:
            return self._json(401, {"ok": False, "error": "not logged in", "kind": "auth"})
        return self._json(200, {"ok": True, **session.public()})

    # --- route bodies: asking ---

    def _ask(self, payload: dict):
        session = self._session()
        if session is None:
            return self._json(401, {"ok": False, "error": "Log in first.", "kind": "auth"})
        if session.role not in ASK_ROLES:
            return self._json(403, {"ok": False, "kind": "auth",
                                    "error": f"The {session.role} role cannot ask VITALS."})

        complaint = str(payload.get("complaint", "")).strip()
        if not complaint:
            return self._json(400, {"ok": False, "error": "no complaint given"})

        model = str(payload.get("model") or self.model)
        corrections = payload.get("corrections")
        if not isinstance(corrections, dict):
            corrections = {}
        try:
            return self._json(200, run_pipeline(self.kb, complaint, model, corrections))
        except OllamaUnavailable as exc:
            return self._json(503, {"ok": False, "error": str(exc), "kind": "ollama"})
        except KnowledgeBaseError as exc:
            return self._json(500, {"ok": False, "error": str(exc), "kind": "kb"})

    # --- route bodies: open data ---

    @staticmethod
    def _example_prompts() -> list[dict]:
        try:
            from .bench import load_prompts
            prompts = load_prompts()
        except Exception:
            return []
        return [
            {"id": p["id"], "category": p.get("category", ""), "text": p["text"]}
            for p in prompts
        ]

    def _health(self) -> dict:
        try:
            models = list_models(OLLAMA_HOST)
            ollama = {
                "up": True,
                "models": models,
                "has_default": any(
                    name.split(":")[0] == self.model.split(":")[0] for name in models
                ),
            }
        except OllamaUnavailable as exc:
            ollama = {"up": False, "models": [], "error": str(exc)}

        return {
            "kb": {
                "conditions": len(self.kb.conditions),
                "findings": len(self.kb.findings),
            },
            "ollama": ollama,
            "model": self.model,
            "sensors": sensors.status(),
        }


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    kb_path=None,
    model: str = DEFAULT_MODEL,
    open_browser: bool = False,
) -> None:
    Handler.kb = load_knowledge_base(kb_path)
    Handler.model = model
    Handler.desk = LoginDesk(load_accounts())

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"

    print("\n  VITALS interface running")
    print(f"  {url}")
    print(f"  model: {model}   |   sensors: {sensors.status()}")
    from .accounts import ACCOUNTS_FILE, accounts_path
    if accounts_path() != ACCOUNTS_FILE:
        print("  accounts: DEMO accounts (accounts.example.json) - add real ones with")
        print("            python -m vitals add-account")
    print("  Ctrl-C to stop\n")

    if open_browser:
        import webbrowser
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped\n")
    finally:
        httpd.server_close()
