"""The ollama reasoning path.

No network here on purpose. We fake the HTTP layer so we can test the CONTRACT -
what happens when the model behaves, and more importantly what happens when it
does not. The model itself is not under test; our handling of it is.
"""

import json
import os

import pytest

from mdx import load_kb
from mdx.llm import KeywordExtractor
from mdx.reason import OllamaUnavailable, ask
from mdx.retrieval import retrieve, as_context


@pytest.fixture(scope="module")
def kb():
    return load_kb()


@pytest.fixture
def renal_setup(kb):
    text = ("flight day 63, bad pain in my right side, 8 out of 10, comes in waves "
            "and shoots toward my groin, blood in my urine")
    obs = KeywordExtractor().extract(text, kb)
    return text, retrieve(kb, text, obs)


def fake_ollama(monkeypatch, response_obj):
    """Make urlopen return whatever we want the model to have said."""
    payload = json.dumps({"response": json.dumps(response_obj)}).encode()

    class _Resp:
        def read(self): return payload
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())


# --- retrieval -------------------------------------------------------------

def test_retrieval_finds_the_right_condition(kb, renal_setup):
    _, retrieved = renal_setup
    assert "renal_stone" in {r.id for r in retrieved}


def test_emergencies_are_always_retrieved(kb):
    """A clot must never fall off the list just because the words did not match."""
    retrieved = retrieve(kb, "my shoulder hurts after EVA", {"shoulder_pain": 7})
    assert "jugular_vte" in {r.id for r in retrieved}


def test_retrieval_never_returns_empty(kb):
    """An empty context means the model answers from generic Earth medicine."""
    assert retrieve(kb, "asdfgh qwerty zxcvbn", {})


def test_context_does_not_leak_the_invented_numbers(kb, renal_setup):
    """Priors and weights were made up. Feeding them to a model just launders
    invented numbers into confident prose."""
    _, retrieved = renal_setup
    ctx = as_context(retrieved)
    assert "prior" not in ctx.lower()
    assert "weight" not in ctx.lower()
    for tok in ("0.04", "2.4", "+2.0", "-2.0"):
        assert tok not in ctx


# --- the model's answer is constrained -------------------------------------

def test_model_cannot_name_a_condition_it_was_not_given(kb, renal_setup, monkeypatch):
    text, retrieved = renal_setup
    fake_ollama(monkeypatch, {
        "differential": [
            {"condition_id": "space_flu", "confidence": "high", "reasoning": "made up"},
            {"condition_id": "renal_stone", "confidence": "high", "reasoning": "colicky flank pain"},
        ],
        "escalate": True, "escalation_reason": "urgent",
        "next_questions": [], "uncertainty": "",
    })
    ans = ask(kb, text, retrieved)
    assert [c.condition_id for c in ans.differential] == ["renal_stone"]
    assert ans.dropped == ["space_flu"]


def test_citations_come_from_the_kb_not_the_model(kb, renal_setup, monkeypatch):
    """The model is never asked for a URL, so it cannot fabricate one."""
    text, retrieved = renal_setup
    fake_ollama(monkeypatch, {
        "differential": [{
            "condition_id": "renal_stone", "confidence": "high", "reasoning": "x",
            "sources": [{"title": "Journal of Fake Medicine", "url": "http://not-real.example"}],
        }],
        "escalate": True, "escalation_reason": "urgent",
        "next_questions": [], "uncertainty": "",
    })
    ans = ask(kb, text, retrieved)
    urls = [s["url"] for s in ans.top.sources]
    assert "http://not-real.example" not in urls
    assert urls == [s["url"] for s in kb.condition("renal_stone").sources]


def test_escalation_is_added_when_the_model_forgets(kb, renal_setup, monkeypatch):
    """A model that forgets to escalate is not a reason a crewmember goes without help."""
    text, retrieved = renal_setup
    fake_ollama(monkeypatch, {
        "differential": [{"condition_id": "renal_stone", "confidence": "high",
                          "reasoning": "classic colic"}],
        "escalate": False, "escalation_reason": "",
        "next_questions": [], "uncertainty": "",
    })
    ans = ask(kb, text, retrieved)
    assert ans.escalate is True
    assert "automatically" in ans.escalation_reason


def test_empty_differential_is_an_acceptable_answer(kb, renal_setup, monkeypatch):
    """"Nothing here fits" beats a confident guess."""
    text, retrieved = renal_setup
    fake_ollama(monkeypatch, {"differential": [], "escalate": False,
                              "escalation_reason": "", "next_questions": ["..."],
                              "uncertainty": "no match"})
    ans = ask(kb, text, retrieved)
    assert ans.differential == []
    assert ans.top is None


def test_garbage_json_does_not_crash(kb, renal_setup, monkeypatch):
    text, retrieved = renal_setup
    payload = json.dumps({"response": "I'm sorry, as an AI language model..."}).encode()

    class _Resp:
        def read(self): return payload
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    ans = ask(kb, text, retrieved)
    assert ans.differential == []
    assert "JSON" in ans.uncertainty


def test_bad_confidence_value_is_clamped(kb, renal_setup, monkeypatch):
    text, retrieved = renal_setup
    fake_ollama(monkeypatch, {
        "differential": [{"condition_id": "renal_stone", "confidence": "ABSOLUTELY CERTAIN",
                          "reasoning": "x"}],
        "escalate": True, "escalation_reason": "y", "next_questions": [], "uncertainty": "",
    })
    assert ask(kb, text, retrieved).top.confidence == "low"


def test_clear_error_when_ollama_is_not_running(kb, renal_setup):
    text, retrieved = renal_setup
    with pytest.raises(OllamaUnavailable, match="ollama serve"):
        ask(kb, text, retrieved, host="http://127.0.0.1:1", timeout=1.0)


# --- pulling a model without the CLI ---------------------------------------

def test_pull_reports_progress_and_finishes(monkeypatch):
    """`mdx pull` exists so a broken Windows PATH cannot block the project."""
    from mdx.reason import pull_model
    lines = [
        b'{"status":"pulling manifest"}\n',
        b'{"status":"downloading","total":100,"completed":50}\n',
        b'{"status":"downloading","total":100,"completed":100}\n',
        b'{"status":"success"}\n',
    ]

    class _Resp:
        def __iter__(self): return iter(lines)
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    seen = []
    pull_model("llama3.2", progress=seen.append)
    assert seen[0]["status"] == "pulling manifest"
    assert seen[-1]["status"] == "success"


def test_pull_surfaces_a_server_side_error(monkeypatch):
    from mdx.reason import OllamaUnavailable, pull_model

    class _Resp:
        def __iter__(self): return iter([b'{"error":"model not found"}\n'])
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    with pytest.raises(OllamaUnavailable, match="model not found"):
        pull_model("nope")


def test_error_messages_point_at_the_server_not_the_PATH(kb, renal_setup):
    """The `ollama` command being missing is a Windows PATH quirk, not a
    blocker. Every message must send you to the app, not to PATH debugging."""
    from mdx.reason import OllamaUnavailable, ask
    text, retrieved = renal_setup
    with pytest.raises(OllamaUnavailable) as e:
        ask(kb, text, retrieved, host="http://127.0.0.1:1", timeout=1.0)
    msg = str(e.value)
    assert "Ollama app" in msg or "system tray" in msg
    assert "mdx pull" in msg


def test_progress_only_redraws_when_something_changed(monkeypatch, capsys):
    """Regression from a real run: ollama emits progress events many times a
    second. Redrawing on every one, in a narrow terminal where the bar wrapped,
    turned a single progress bar into ~600 lines of garbage."""
    import sys as _sys
    from mdx.cli import cmd_pull

    events = []
    # same percentage reported 50 times, then a new one
    for _ in range(50):
        events.append(b'{"status":"downloading","total":100,"completed":40}\n')
    events.append(b'{"status":"downloading","total":100,"completed":41}\n')
    events.append(b'{"status":"success"}\n')

    class _Resp:
        """Answers both /api/pull (iterated) and the /api/tags call that
        cmd_pull makes afterwards (read())."""
        def __iter__(self): return iter(events)
        def read(self): return json.dumps({"models": [{"name": "llama3.2:latest"}]}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    monkeypatch.setattr(_sys.stdout, "isatty", lambda: False, raising=False)

    class Args:
        model = "llama3.2"
    cmd_pull(Args())

    out = capsys.readouterr().out
    # 40% is emitted 50 times; it must appear at most once in the output
    assert out.count("] 40%") <= 1, "progress bar redrew on unchanged percentage"


def test_progress_line_fits_a_narrow_terminal(monkeypatch, capsys):
    """A 40-char bar in a 45-column window wraps, and then \\r returns to the
    start of the wrapped line instead of the original one."""
    import shutil
    import sys as _sys
    from mdx.cli import cmd_pull

    monkeypatch.setattr(shutil, "get_terminal_size", lambda *a: os.terminal_size((45, 20)))
    events = [b'{"status":"downloading","total":100,"completed":50}\n', b'{"status":"success"}\n']

    class _Resp:
        def __iter__(self): return iter(events)
        def read(self): return json.dumps({"models": [{"name": "llama3.2:latest"}]}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    monkeypatch.setattr(_sys.stdout, "isatty", lambda: False, raising=False)

    class Args:
        model = "llama3.2"
    cmd_pull(Args())

    # Only the REDRAWN lines matter. A static line that wraps is harmless; a
    # \r-redrawn line that wraps is what turned one bar into 600 lines.
    redrawn = [l for l in capsys.readouterr().out.splitlines() if "[" in l and "%" in l]
    assert redrawn, "no progress line was produced"
    for line in redrawn:
        assert len(line) <= 45, f"progress line overflows 45 cols: {len(line)}: {line!r}"


# --- questions must not re-ask what the crewmember already said -------------

def test_never_asks_about_something_already_known(kb, renal_setup, monkeypatch):
    """Regression from a real llama3.2 run.

    The crewmember said "comes in waves". The model read that sentence and then
    asked: "Is the pain constant or does it come and go?"

    Fix is the same trick as the citations - the model picks a finding id from a
    closed list of what is STILL UNKNOWN, and we supply the wording.
    """
    text, retrieved = renal_setup
    known = {"pain_colicky": True, "hematuria": True, "flank_pain": 8}

    fake_ollama(monkeypatch, {
        "differential": [{"condition_id": "renal_stone", "confidence": "high", "reasoning": "x"}],
        "escalate": True, "escalation_reason": "urgent",
        "next_findings": ["pain_colicky", "fever", "urine_output_low"],
        "uncertainty": "",
    })
    ans = ask(kb, text, retrieved, observations=known)

    joined = " ".join(ans.next_questions)
    assert "pain_colicky" not in joined, "asked about a finding it was already told"
    assert any("fever" in q or "urine_output_low" in q for q in ans.next_questions)


def test_invented_finding_ids_are_dropped_from_questions(kb, renal_setup, monkeypatch):
    text, retrieved = renal_setup
    fake_ollama(monkeypatch, {
        "differential": [], "escalate": False, "escalation_reason": "",
        "next_findings": ["do_you_feel_spacey", "fever"], "uncertainty": "",
    })
    ans = ask(kb, text, retrieved, observations={})
    assert not any("do_you_feel_spacey" in q for q in ans.next_questions)


def test_questions_come_from_the_kb_wording(kb, renal_setup, monkeypatch):
    """We supply the phrasing, so it matches the structured interview exactly."""
    text, retrieved = renal_setup
    fake_ollama(monkeypatch, {
        "differential": [], "escalate": False, "escalation_reason": "",
        "next_findings": ["hematuria"], "uncertainty": "",
    })
    ans = ask(kb, text, retrieved, observations={})
    assert kb.findings["hematuria"].ask in ans.next_questions[0]


def test_prompt_tells_the_model_what_is_already_known(kb, renal_setup, monkeypatch):
    """The known/unknown blocks have to actually reach the model."""
    captured = {}

    def _capture(*args, **kwargs):
        captured["payload"] = args[0].data.decode()

        class _Resp:
            def read(self):
                return json.dumps({"response": json.dumps(
                    {"differential": [], "escalate": False, "escalation_reason": "",
                     "next_findings": [], "uncertainty": ""})}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _capture)
    text, retrieved = renal_setup
    ask(kb, text, retrieved, observations={"hematuria": True})

    payload = captured["payload"]
    assert "ALREADY KNOWN" in payload
    assert "STILL UNKNOWN" in payload
    assert "hematuria" in payload


def test_system_prompt_demands_more_than_one_candidate(kb):
    """A differential with one entry is not a differential. Real run gave 1 of 7."""
    from mdx.reason import SYSTEM
    assert "is not a differential" in SYSTEM
    assert "2 to 4" in SYSTEM


def test_error_advice_matches_where_the_user_actually_is(kb, renal_setup):
    """Telling someone inside a Docker container to open the Start menu is
    worse than saying nothing - it sends them hunting for a tray icon that
    cannot exist. Found by running the container build."""
    from mdx.reason import OllamaUnavailable, ask
    text, retrieved = renal_setup

    with pytest.raises(OllamaUnavailable) as local:
        ask(kb, text, retrieved, host="http://127.0.0.1:1", timeout=1.0)
    assert "tray" in str(local.value) or "ollama serve" in str(local.value)
    assert "docker" not in str(local.value).lower()

    with pytest.raises(OllamaUnavailable) as remote:
        ask(kb, text, retrieved, host="http://ollama:11434", timeout=1.0)
    msg = str(remote.value)
    assert "docker compose" in msg
    assert "Start menu" not in msg
