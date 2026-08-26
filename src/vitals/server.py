"""The browser interface.

Stdlib only - http.server, no Flask, no npm, no build step. That is a
requirement, not laziness: this has to run on a Jetson and two Raspberry Pis
that may have no working internet, and every dependency is one more thing that
can fail on the vehicle.

    python -m vitals serve      ->  http://127.0.0.1:8000

ROUTES
    GET  /              the interface
    GET  /api/health    is the KB loaded, is ollama up, what models exist
    GET  /api/examples  the prompt bank, so the UI can offer real complaints
    POST /api/ask       {"complaint": "...", "model": "..."} -> the full answer

THE SERVER OWNS NO MEDICAL LOGIC WHATSOEVER. It is a thin shell around exactly
the same pipeline the CLI uses, so the UI can never drift from what
`vitals ask` does. If they ever disagree, that is a bug in this file.
"""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import sensors
from .engine import diagnose
from .extract import KeywordExtractor
from .knowledge_base import KnowledgeBaseError, load_knowledge_base
from .ollama_client import DEFAULT_MODEL, OLLAMA_HOST, OllamaUnavailable, list_models
from .reason import ask
from .retrieval import retrieve

UI_DIR = Path(__file__).parent / "ui"

RETRIEVAL_LIMIT = 6


def run_pipeline(knowledge_base, complaint: str, model: str) -> dict[str, Any]:
    """The exact same sequence as `cmd_ask`. One pipeline, two front ends."""
    started = time.time()

    observations = KeywordExtractor().extract(complaint, knowledge_base)
    observations.update(sensors.as_observations(sensors.read_all()))

    retrieved = retrieve(knowledge_base, complaint, observations, limit=RETRIEVAL_LIMIT)
    answer = ask(knowledge_base, complaint, retrieved, observations=observations, model=model)

    return {
        "ok": True,
        "elapsed": round(time.time() - started, 1),
        "model": answer.model,
        "sensor_status": answer.sensor_status,
        "escalate": answer.escalate,
        "escalation_reason": answer.escalation_reason,
        "uncertainty": answer.uncertainty,
        "next_questions": answer.next_questions,
        "dropped": answer.dropped,
        "differential": [
            {
                "id": candidate.condition_id,
                "name": candidate.name,
                "urgency": candidate.urgency,
                "confidence": candidate.confidence,
                "reasoning": candidate.reasoning,
                "supporting": candidate.supporting,
                "against": candidate.against,
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


# Kept under the old private name because tests import it directly.
_run_pipeline = run_pipeline


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

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    # --- responses ---

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"),
                   "application/json; charset=utf-8")

    # --- routes ---

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, (UI_DIR / "index.html").read_bytes(),
                              "text/html; charset=utf-8")
        if self.path == "/api/examples":
            return self._json(200, {"prompts": self._example_prompts()})
        if self.path == "/api/health":
            return self._json(200, self._health())
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/ask":
            return self._json(404, {"error": "not found"})

        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"ok": False, "error": "bad JSON"})

        complaint = str(payload.get("complaint", "")).strip()
        if not complaint:
            return self._json(400, {"ok": False, "error": "no complaint given"})

        model = str(payload.get("model") or self.model)
        try:
            return self._json(200, run_pipeline(self.kb, complaint, model))
        except OllamaUnavailable as exc:
            return self._json(503, {"ok": False, "error": str(exc), "kind": "ollama"})
        except KnowledgeBaseError as exc:
            return self._json(500, {"ok": False, "error": str(exc), "kind": "kb"})

    # --- route bodies ---

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

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"

    print("\n  VITALS interface running")
    print(f"  {url}")
    print(f"  model: {model}   |   sensors: {sensors.status()}")
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
