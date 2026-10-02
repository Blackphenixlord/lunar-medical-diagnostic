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
    # Pretend ollama is down. Without this the test passed or failed depending
    # on whether ollama happened to be running on the machine running pytest.
    from vitals.extract import OllamaExtractor
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VITALS_BACKEND", raising=False)
    monkeypatch.setattr(OllamaExtractor, "is_available", staticmethod(lambda *a, **k: False))
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
    monkeypatch.delenv("VITALS_BACKEND", raising=False)
    monkeypatch.setattr(OllamaExtractor, "is_available", staticmethod(lambda *a, **k: False))
    assert get_extractor("auto").name == "keyword"


def test_auto_prefers_local_ollama_over_cloud(monkeypatch):
    """Local model beats the API. The offline path is the one that has to work."""
    from vitals.extract import OllamaExtractor
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-not-a-real-key")
    monkeypatch.delenv("VITALS_BACKEND", raising=False)
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


# --- phrasings added 26 Sep ---------------------------------------------------
# DCS, dental and wounds had NO phrasebook entries at all, so the extractor
# found nothing in "came in off the EVA" or "tooth has been killing me". These
# use everyday wording on purpose - not the benchmark sentences.

@pytest.mark.parametrize("text, finding, expected", [
    ("back from the spacewalk and my knee aches", "recent_decompression", True),
    ("post-EVA and feeling off", "recent_decompression", True),
    ("the EVA is scheduled for next week", "recent_decompression", None),
    ("weird marbled rash on my shoulder", "skin_mottling", True),
    ("I feel confused and my balance is off", "confusion", True),
    ("I feel confused and my balance is off", "balance_impaired", True),
    ("my molar hurts when I chew", "tooth_pain", True),
    ("my molar hurts when I chew", "pain_on_biting", True),
    ("my gum is swollen on the left", "jaw_or_face_swelling", True),
    ("a filling fell out yesterday", "lost_filling_or_crown", True),
    ("got a deep cut on my palm", "open_wound", True),
    ("it won't stop bleeding even with pressure", "bleeding_uncontrolled", True),
    ("there's blood when I pee", "hematuria", True),
    ("I get out of breath climbing the node", "shortness_of_breath", True),
    ("my arm feels weak", "numbness_or_weakness", True),
])
def test_everyday_phrasings(kb, ex, text, finding, expected):
    assert ex.extract(text, kb).get(finding) is expected


def test_spoken_pain_scores_attach_to_the_pain(kb, ex):
    assert ex.extract("my tooth is killing me, maybe a 9", kb).get("tooth_pain") == 9.0
    assert ex.extract("my back hurts, about a 6 today", kb).get("back_pain") == 6.0


def test_a_duration_is_not_a_pain_score(kb, ex):
    obs = ex.extract("my back hurts, it's been a 2 hour thing", kb)
    assert obs.get("back_pain") is True


# --- general conditions (added 2 Oct 2026): the overlaps that bit us ---------

def test_days_are_not_diopters(kb, ex):
    """"rash for 3 days" was read as a 3-diopter eye shift and pulled SANS in."""
    obs = ex.extract("itchy rash under my straps for 3 days", kb)
    assert obs.get("hyperopic_shift") is None
    assert obs.get("rash") is True


def test_burning_urine_is_not_a_burn(kb, ex):
    obs = ex.extract("it burns when I pee", kb)
    assert obs.get("dysuria") is True
    assert obs.get("burn_injury") is None


def test_burning_throat_is_not_a_burn(kb, ex):
    obs = ex.extract("there was an ammonia smell and now my throat burns", kb)
    assert obs.get("chemical_exposure") is True
    assert obs.get("throat_burning") is True
    assert obs.get("burn_injury") is None


def test_debris_in_the_eye(kb, ex):
    obs = ex.extract("Something flew into my eye in the rack and it's watering and stinging", kb)
    assert obs.get("eye_foreign_body_sensation") is True
    assert obs.get("eye_watering") is True
    assert obs.get("eye_pain") is True


def test_lower_right_of_my_belly(kb, ex):
    obs = ex.extract("pain moved to the lower right of my belly", kb)
    assert obs.get("abdominal_pain_rlq") is True
