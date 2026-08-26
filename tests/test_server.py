"""The web UI.

The server owns NO medical logic - it is a shell around the same pipeline the
CLI uses. These tests exist to keep it that way, and to make sure the honest
bits (no-diagnosis framing, sensor warning, KB-sourced citations) survive
whatever anyone does to the styling later.
"""

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen, Request
from urllib.error import HTTPError

import pytest

from vitals import load_knowledge_base
from vitals.server import Handler, UI_DIR, _run_pipeline


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def server(kb):
    Handler.kb = kb
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


# --- the page itself -------------------------------------------------------

def test_index_is_served(server):
    body = urlopen(server + "/").read().decode()
    assert "<title>VITALS" in body


def test_page_says_it_is_not_a_diagnosis(server):
    """This framing is not decoration. It must survive any restyle."""
    body = urlopen(server + "/").read().decode().lower()
    assert "not a diagnosis" in body


def test_page_warns_that_nothing_has_been_measured(server):
    body = urlopen(server + "/").read().decode().lower()
    assert "no instruments attached" in body
    assert "no vital sign has been measured" in body


def test_ui_is_a_single_self_contained_file():
    """No CDN, no npm, no build step - it has to run on a Jetson with no internet."""
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    for bad in ("http://cdn", "https://cdn", "unpkg.com", "jsdelivr", "googleapis.com"):
        assert bad not in html, f"external dependency found: {bad}"


# --- api -------------------------------------------------------------------

def test_health_reports_kb_and_sensors(server):
    h = json.loads(urlopen(server + "/api/health").read())
    assert h["kb"]["conditions"] >= 10
    assert h["sensors"] == "no sensors connected"
    assert "ollama" in h


def test_ask_rejects_an_empty_complaint(server):
    req = Request(server + "/api/ask", data=b'{"complaint":"  "}',
                  headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(HTTPError) as e:
        urlopen(req)
    assert e.value.code == 400


def test_ask_reports_ollama_being_down_as_503(server, monkeypatch):
    """The UI must show a real explanation, not a stack trace."""
    req = Request(server + "/api/ask", data=b'{"complaint":"my head hurts"}',
                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        body = json.loads(urlopen(req).read())
    except HTTPError as exc:
        assert exc.code == 503
        payload = json.loads(exc.read())
        assert payload["ok"] is False
        assert payload["kind"] == "ollama"
        return
    assert body["ok"] is True   # ollama actually was running - fine too


def test_unknown_route_is_404(server):
    with pytest.raises(HTTPError) as e:
        urlopen(server + "/nope")
    assert e.value.code == 404


# --- the pipeline the server wraps ----------------------------------------

def test_pipeline_shape_matches_what_the_ui_expects(kb, monkeypatch):
    """If this drifts, the UI silently renders blanks."""
    fake = {
        "differential": [{"condition_id": "renal_stone", "confidence": "high",
                          "reasoning": "colicky flank pain with hematuria",
                          "supporting": ["blood in urine"], "against": []}],
        "escalate": True, "escalation_reason": "urgent condition",
        "next_findings": ["fever"], "uncertainty": "duration",
    }
    payload = json.dumps({"response": json.dumps(fake)}).encode()

    class _Resp:
        def read(self): return payload
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())

    d = _run_pipeline(kb, "flight day 63, pain in my right side in waves, blood in my urine", "llama3.2")

    for key in ("ok", "elapsed", "model", "sensor_status", "escalate", "escalation_reason",
                "uncertainty", "next_questions", "dropped", "differential", "trace"):
        assert key in d, f"UI expects '{key}'"
    for key in ("findings", "retrieved", "crosscheck"):
        assert key in d["trace"]

    top = d["differential"][0]
    for key in ("id", "name", "urgency", "confidence", "reasoning",
                "supporting", "against", "recommend", "sources"):
        assert key in top

    # citations must come from the KB
    assert top["sources"] == kb.condition("renal_stone").sources
    assert d["trace"]["crosscheck"]["state"] in ("agree", "disagree", "insufficient")
