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
from vitals.accounts import Account, LoginDesk, hash_pin
from vitals.server import Handler, UI_DIR, run_pipeline

ASTRONAUT_PIN = "4321"
DOCTOR_PIN = "8765"


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def server(kb):
    Handler.kb = kb
    Handler.desk = LoginDesk([
        Account("astro-test", "Test Astronaut", "astronaut", hash_pin(ASTRONAUT_PIN),
                {"Height": "178 cm"}),
        Account("doctor-test", "Test Doctor", "doctor", hash_pin(DOCTOR_PIN)),
    ])
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


# --- helpers ---------------------------------------------------------------

def post(server, path, body, cookie=None):
    """POST JSON; return (status, payload, set-cookie header)."""
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    req = Request(server + path, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urlopen(req) as resp:
            return resp.status, json.loads(resp.read()), resp.headers.get("Set-Cookie")
    except HTTPError as exc:
        return exc.code, json.loads(exc.read()), exc.headers.get("Set-Cookie")


def log_in(server, pin):
    status, body, set_cookie = post(server, "/api/login", {"pin": pin})
    assert status == 200, body
    return set_cookie.split(";")[0]          # "vitals_session=<token>"


# --- the pages -------------------------------------------------------------

def test_login_page_is_served_at_root(server):
    body = urlopen(server + "/").read().decode()
    assert "<title>VITALS" in body
    assert "/api/login" in body


def test_every_page_says_it_is_not_a_diagnosis(server):
    """This framing is not decoration. It must survive any restyle."""
    for page in ("/", "/astronaut", "/dev"):
        body = urlopen(server + page).read().decode().lower()
        assert "not a diagnosis" in body, page


def test_pages_say_that_nothing_has_been_measured(server):
    dev = urlopen(server + "/dev").read().decode().lower()
    assert "no instruments attached" in dev
    assert "no vital sign has been measured" in dev

    astronaut = urlopen(server + "/astronaut").read().decode().lower()
    assert "no sensor connected" in astronaut
    assert "not connected" in astronaut


def test_every_ui_file_is_self_contained():
    """No CDN, no npm, no build step - it has to run on a Jetson with no internet."""
    for page in UI_DIR.glob("*.html"):
        html = page.read_text(encoding="utf-8")
        for bad in ("http://cdn", "https://cdn", "unpkg.com", "jsdelivr", "googleapis.com",
                    "<script src=", "<link rel=\"stylesheet\""):
            assert bad not in html, f"external dependency in {page.name}: {bad}"


def test_astronaut_page_shows_no_numeric_confidence():
    """Acceptance criteria 3.1: no percentages or scores on the crew screen."""
    html = (UI_DIR / "astronaut.html").read_text(encoding="utf-8")
    assert "toFixed" not in html
    assert "score" not in html.split("<script>")[1]


# --- login -----------------------------------------------------------------

def test_right_pin_logs_in_and_sets_an_httponly_cookie(server):
    status, body, set_cookie = post(server, "/api/login", {"pin": ASTRONAUT_PIN})
    assert status == 200
    assert body["role"] == "astronaut"
    assert body["page"] == "/astronaut"
    assert "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie


def test_wrong_pin_is_refused(server):
    status, body, set_cookie = post(server, "/api/login", {"pin": "0000"})
    assert status == 401
    assert body["ok"] is False
    assert set_cookie is None


def test_me_needs_a_session(server):
    with pytest.raises(HTTPError) as e:
        urlopen(server + "/api/me")
    assert e.value.code == 401


def test_me_returns_the_profile_after_login(server):
    cookie = log_in(server, ASTRONAUT_PIN)
    body = json.loads(urlopen(Request(server + "/api/me", headers={"Cookie": cookie})).read())
    assert body["name"] == "Test Astronaut"
    assert body["profile"] == {"Height": "178 cm"}
    assert "pin_hash" not in json.dumps(body)


def test_logout_ends_the_session(server):
    cookie = log_in(server, ASTRONAUT_PIN)
    post(server, "/api/logout", {}, cookie)
    status, _, _ = post(server, "/api/ask", {"complaint": "my head hurts"}, cookie)
    assert status == 401


def test_emergency_access_opens_the_astronaut_screen_without_a_profile(server):
    status, body, set_cookie = post(server, "/api/emergency", {})
    assert status == 200
    assert body["emergency"] is True
    assert body["page"] == "/astronaut"
    assert body["profile"] == {}


def test_a_doctor_cannot_ask_vitals(server):
    """Roles are enforced by the server, not by which buttons a page shows."""
    cookie = log_in(server, DOCTOR_PIN)
    status, body, _ = post(server, "/api/ask", {"complaint": "my head hurts"}, cookie)
    assert status == 403


def test_ask_without_logging_in_is_refused(server):
    status, body, _ = post(server, "/api/ask", {"complaint": "my head hurts"})
    assert status == 401
    assert body["kind"] == "auth"


# --- api -------------------------------------------------------------------

def test_health_reports_kb_and_sensors(server):
    h = json.loads(urlopen(server + "/api/health").read())
    assert h["kb"]["conditions"] >= 10
    assert h["sensors"] == "no sensors connected"
    assert "ollama" in h


def test_ask_rejects_an_empty_complaint(server):
    cookie = log_in(server, ASTRONAUT_PIN)
    status, _, _ = post(server, "/api/ask", {"complaint": "  "}, cookie)
    assert status == 400


def test_ask_reports_ollama_being_down_as_503(server, monkeypatch):
    """The UI must show a real explanation, not a stack trace."""
    cookie = log_in(server, ASTRONAUT_PIN)
    status, payload, _ = post(server, "/api/ask", {"complaint": "my head hurts"}, cookie)
    if status == 200:
        assert payload["ok"] is True   # ollama actually was running - fine too
        return
    assert status == 503
    assert payload["ok"] is False
    assert payload["kind"] == "ollama"


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

    d = run_pipeline(kb, "flight day 63, pain in my right side in waves, blood in my urine", "llama3.2")

    for key in ("ok", "elapsed", "model", "sensor_status", "escalate", "escalation_reason",
                "uncertainty", "next_questions", "dropped", "known", "differential", "trace"):
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


def _fake_model(monkeypatch):
    fake = {"differential": [], "escalate": False, "escalation_reason": "",
            "next_findings": [], "uncertainty": ""}
    payload = json.dumps({"response": json.dumps(fake)}).encode()

    class _Resp:
        def read(self): return payload
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())


def test_known_findings_use_human_labels(kb, monkeypatch):
    """The crew screen shows labels, never raw finding ids."""
    _fake_model(monkeypatch)
    d = run_pipeline(kb, "flight day 63, blood in my urine", "llama3.2")
    hematuria = next(f for f in d["known"] if f["id"] == "hematuria")
    assert hematuria["label"] == kb.findings["hematuria"].label
    assert hematuria["value"] == "yes"
    assert hematuria["correctable"] is True


def test_a_correction_overrides_what_the_extractor_read(kb, monkeypatch):
    """Acceptance criteria 5.3: 'no back pain' read as back pain must be fixable."""
    _fake_model(monkeypatch)
    before = run_pipeline(kb, "my back hurts and my right side hurts", "llama3.2")
    assert before["trace"]["findings"]["back_pain"] is True

    after = run_pipeline(kb, "my back hurts and my right side hurts", "llama3.2",
                         corrections={"back_pain": False})
    assert after["trace"]["findings"]["back_pain"] is False


def test_corrections_ignore_unknown_ids_and_non_yes_no_values(kb, monkeypatch):
    _fake_model(monkeypatch)
    d = run_pipeline(kb, "my back hurts", "llama3.2",
                     corrections={"made_up_finding": True, "back_pain": "maybe"})
    assert "made_up_finding" not in d["trace"]["findings"]
    assert d["trace"]["findings"]["back_pain"] is True


# --- the alarm drives the screen (27 Sep: DCS alarm showed URGENT, a "91%",
# and shoulder advice, because the model ranked shoulder strain first) -------

BENDS = ("Came in off the EVA about two hours ago. My left shoulder has this deep "
         "boring ache, maybe a 7, and there's a weird blotchy marbled rash on my forearm.")


def _fake_reply(monkeypatch, reply):
    payload = json.dumps({"response": json.dumps(reply)}).encode()

    class _Resp:
        def read(self): return payload
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())


def test_engine_alarm_sets_level_to_emergency_and_names_the_condition(kb, monkeypatch):
    _fake_reply(monkeypatch, {
        "differential": [
            {"condition_id": "msk_shoulder_overuse", "confidence": "high",
             "reasoning": "consistent with msk_shoulder_overuse"},
            {"condition_id": "decompression_sickness", "confidence": "low", "reasoning": "unlikely"}],
        "escalate": False, "escalation_reason": "", "next_findings": [], "uncertainty": ""})
    d = run_pipeline(kb, BENDS, "llama3.2")

    assert d["escalate"] is True
    assert d["escalation"]["level"] == "emergency"
    assert d["escalation"]["conditions"][0]["id"] == "decompression_sickness"
    assert d["escalation"]["conditions"][0]["recommend"] == kb.condition("decompression_sickness").recommend


def test_no_percentages_reach_the_screen(kb, monkeypatch):
    """Acceptance criteria 3.1. The priors behind those numbers have no source."""
    _fake_reply(monkeypatch, {
        "differential": [{"condition_id": "msk_shoulder_overuse", "confidence": "high", "reasoning": "x"}],
        "escalate": False, "escalation_reason": "", "next_findings": [], "uncertainty": ""})
    d = run_pipeline(kb, BENDS, "llama3.2")
    assert "%" not in d["escalation_reason"]


def test_raw_condition_ids_in_model_text_become_names(kb, monkeypatch):
    """Acceptance criteria 2.1: the crew never sees a KB id."""
    _fake_reply(monkeypatch, {
        "differential": [{"condition_id": "msk_shoulder_overuse", "confidence": "high",
                          "reasoning": "consistent with msk_shoulder_overuse"}],
        "escalate": False, "escalation_reason": "", "next_findings": [],
        "uncertainty": "could be msk_shoulder_overuse or decompression_sickness"})
    d = run_pipeline(kb, BENDS, "llama3.2")
    shoulder = kb.condition("msk_shoulder_overuse").name
    assert d["differential"][0]["reasoning"] == f"consistent with {shoulder}"
    assert "msk_shoulder_overuse" not in d["uncertainty"]
    assert "decompression_sickness" not in d["uncertainty"]


def test_no_escalation_means_level_none(kb, monkeypatch):
    _fake_reply(monkeypatch, {
        "differential": [], "escalate": False, "escalation_reason": "",
        "next_findings": [], "uncertainty": ""})
    d = run_pipeline(kb, "blorp zzz qwerty", "llama3.2")
    assert d["escalation"] == {"level": "none", "conditions": []}
