"""The prompt bank and the benchmark.

The bank is a test asset, so it needs tests of its own - a benchmark with a
broken scoring rule is worse than no benchmark, because it produces a number
people believe.
"""

import pytest
import yaml

from mdx import load_kb
from mdx.bench import Report, load_prompts, prompts_path, run_one


@pytest.fixture(scope="module")
def kb():
    return load_kb()


@pytest.fixture(scope="module")
def prompts():
    return load_prompts()


# --- the bank itself -------------------------------------------------------

def test_bank_exists_and_is_substantial(prompts):
    assert len(prompts) >= 20


def test_every_prompt_says_what_it_tests(prompts):
    """If you cannot say why a prompt is in the bank, it is noise."""
    for p in prompts:
        assert p.get("why", "").strip(), f"{p['id']} has no `why`"


def test_ids_are_unique(prompts):
    ids = [p["id"] for p in prompts]
    assert len(ids) == len(set(ids))


def test_every_expect_is_a_real_condition_or_none(kb, prompts):
    for p in prompts:
        assert p["expect"] == "none" or p["expect"] in kb.conditions, \
            f"{p['id']} expects unknown condition {p['expect']}"


def test_bank_covers_every_condition_in_the_kb(kb, prompts):
    """A condition with no prompt has never been tested end to end."""
    covered = {p["expect"] for p in prompts if p["expect"] != "none"}
    missing = set(kb.conditions) - covered
    assert not missing, f"conditions with no prompt: {sorted(missing)}"


def test_bank_has_prompts_where_the_answer_is_nothing(prompts):
    """Without these, the benchmark rewards a system that always guesses."""
    nones = [p for p in prompts if p["expect"] == "none"]
    assert len(nones) >= 3


def test_bank_has_mimics(prompts):
    """Look-alikes are where a diagnostic tool actually earns its keep."""
    assert len([p for p in prompts if p.get("category") == "mimic"]) >= 3


def test_every_dangerous_prompt_expects_escalation(kb, prompts):
    urgent = {c.id for c in kb.conditions.values() if c.urgency in ("urgent", "emergency")}
    for p in prompts:
        if p["expect"] in urgent:
            assert p.get("escalate") is True, \
                f"{p['id']} points at an {kb.conditions[p['expect']].urgency} condition but does not expect escalation"


def test_prompts_are_written_like_people_talk(prompts):
    """Not a style rule - phrasing variety is the point of the bank."""
    texts = [p["text"] for p in prompts]
    assert any(t.islower() for t in texts), "no informal all-lowercase prompt"
    assert any(len(t) < 60 for t in texts), "no terse prompt"
    assert any(len(t) > 200 for t in texts), "no rambling prompt"


# --- the scoring ----------------------------------------------------------

def test_hit_and_refusal_are_scored_separately():
    """The whole point. A system that always names something must score 100%
    hits and 0% refusals, and the report has to show that plainly."""
    from mdx.bench import Outcome
    r = Report()
    r.outcomes = [
        Outcome("a", "classic", "renal_stone", "renal_stone", True, True, True, 1.0),
        Outcome("b", "classic", "sans", "sans", True, False, False, 1.0),
        Outcome("c", "nothing_fits", "none", "renal_stone", False, False, False, 1.0),
        Outcome("d", "nothing_fits", "none", "sans", False, False, False, 1.0),
    ]
    assert r.hit_rate == 1.0
    assert r.refusal_rate == 0.0
    assert len(r.failures) == 2


def test_missed_escalation_is_tracked_separately_from_a_wrong_answer():
    """Naming the wrong condition is bad. Failing to escalate is the one that
    hurts someone, so it gets its own counter."""
    from mdx.bench import Outcome
    o = Outcome("x", "classic", "renal_stone", "renal_stone", True, True, False, 1.0)
    assert o.hit is True
    assert o.missed_escalation is True

    r = Report(); r.outcomes = [o]
    assert len(r.missed_escalations) == 1


def test_escalating_unnecessarily_is_not_counted_as_a_failure():
    from mdx.bench import Outcome
    o = Outcome("x", "classic", "sans", "sans", True, False, True, 1.0)
    assert o.escalation_ok is True
    assert o.missed_escalation is False


def test_run_one_reports_ollama_being_down_as_an_error_not_a_failure(kb, prompts):
    """A benchmark that scores 0% because the server is off is a lie."""
    o = run_one(kb, prompts[0], model="llama3.2", host="http://127.0.0.1:1")
    assert o.error
    assert o.hit is False
    r = Report(); r.outcomes = [o]
    assert r.naming == [] and r.errors == [o]


def test_bank_file_parses_as_yaml():
    yaml.safe_load(prompts_path().read_text(encoding="utf-8"))
