"""The intake layer. Keyword backend only - no network in CI, ever."""

import pytest
from vitals import load_knowledge_base
from vitals.extract import KeywordExtractor, get_extractor


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def ex():
    return KeywordExtractor()


def test_extracts_basic_symptoms(kb, ex):
    obs = ex.extract("My head is killing me and I can't concentrate", kb)
    assert obs.get("headache") is True
    assert obs.get("cognitive_slowing") is True


def test_handles_negation(kb, ex):
    obs = ex.extract("Bad flank pain but no blood in my urine and no fever", kb)
    assert obs.get("flank_pain") is True
    assert obs.get("hematuria") is False


def test_extracts_numbers(kb, ex):
    obs = ex.extract("Flight day 63, temperature 38.4, heart rate 112", kb)
    assert obs.get("mission_elapsed_days") == 63
    assert obs.get("fever") == pytest.approx(38.4)
    assert obs.get("hr_elevated") == 112


def test_scale_attaches_to_the_pain_it_follows(kb, ex):
    obs = ex.extract("Pain in my side, about 8 out of 10, comes in waves", kb)
    assert obs.get("flank_pain") == 8
    assert obs.get("pain_colicky") is True


def test_never_invents_a_finding_outside_the_vocabulary(kb, ex):
    obs = ex.extract("I feel like my quantum flux capacitor is misaligned", kb)
    assert all(k in kb.findings for k in obs)


def test_extractor_falls_back_to_keyword_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert get_extractor("auto").name == "keyword"


def test_end_to_end_free_text_to_differential(kb, ex):
    from vitals import diagnose
    text = ("Flight day 63. Really bad pain in my right side, 8 out of 10, comes in waves "
            "and shoots toward my groin. There is blood in my urine.")
    r = diagnose(kb, ex.extract(text, kb))
    assert r.top.id == "renal_stone"


def test_negation_does_not_leak_across_sentences(kb, ex):
    """Regression: "never really cleared. My face feels full" used to read the
    "never" from the previous sentence and record facial fullness as ABSENT.
    Silently inverting a finding is the worst thing this layer can do."""
    obs = ex.extract("Stuffed up since I got here, never really cleared. "
                     "My face feels full. No fever, no sore throat.", kb)
    assert obs.get("facial_fullness") is True
    assert obs.get("nasal_congestion") is True
    assert obs.get("congestion_since_arrival") is True
    assert obs.get("sore_throat") is False


def test_stuffed_up_is_congestion(kb, ex):
    assert ex.extract("I have been stuffed up for days", kb).get("nasal_congestion") is True


# --- ollama backend --------------------------------------------------------
# No network in CI, so we test the contract, not the model.

def test_auto_falls_back_to_keyword_when_nothing_local_is_running(monkeypatch):
    from vitals.extract import OllamaExtractor
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MDX_BACKEND", raising=False)
    monkeypatch.setattr(OllamaExtractor, "is_available", staticmethod(lambda *a, **k: False))
    assert get_extractor("auto").name == "keyword"


def test_auto_prefers_local_ollama_over_cloud(monkeypatch):
    """Local model beats the API. The offline path is the one that has to work."""
    from vitals.extract import OllamaExtractor
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-not-a-real-key")
    monkeypatch.delenv("MDX_BACKEND", raising=False)
    monkeypatch.setattr(OllamaExtractor, "is_available", staticmethod(lambda *a, **k: True))
    assert get_extractor("auto").name == "ollama"


def test_ollama_gives_a_useful_error_when_not_running(kb, monkeypatch):
    from vitals.extract import OllamaExtractor
    ex = OllamaExtractor(host="http://127.0.0.1:1")   # nothing listens here
    with pytest.raises(RuntimeError, match="ollama serve"):
        ex.extract("my head hurts", kb)


def test_ollama_output_is_scrubbed_against_the_vocabulary(kb, monkeypatch):
    """A model WILL eventually invent a finding id. It must never reach the engine."""
    from vitals.extract import OllamaExtractor
    import json as _json

    ex = OllamaExtractor()
    fake = _json.dumps({
        "headache": True,
        "fever": "38.4",
        "made_up_finding": True,      # not in the vocabulary -> dropped
        "flank_pain": "not a number", # unparseable -> dropped
        "nausea": None,               # null -> dropped
    })

    class _Resp:
        def read(self): return _json.dumps({"response": fake}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())

    obs = ex.extract("whatever", kb)
    assert obs == {"headache": True, "fever": 38.4}
    assert all(k in kb.findings for k in obs)
