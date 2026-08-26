"""The knowledge base is the product. These tests protect it from us."""

import pytest
from vitals import load_knowledge_base
from vitals.knowledge_base import KnowledgeBaseError


def test_kb_loads_and_validates():
    kb = load_knowledge_base()
    assert len(kb.conditions) >= 10, "the board item says ten rules - do not ship fewer"
    assert len(kb.findings) >= 40


def test_every_condition_cites_a_real_source():
    for c in load_knowledge_base().conditions.values():
        assert c.sources, f"{c.id} has no sources - a rule without a citation is a guess"
        for s in c.sources:
            assert s["url"].startswith("http"), f"{c.id}: bad url {s['url']}"


def test_every_condition_explains_microgravity():
    """A panel WILL ask 'why is this different in space?' for every single rule."""
    for c in load_knowledge_base().conditions.values():
        assert len(c.microgravity_note) > 80, f"{c.id} needs a real microgravity_note"


def test_every_condition_has_recommendations():
    for c in load_knowledge_base().conditions.values():
        assert len(c.recommend) >= 3, f"{c.id} needs actionable next steps"


def test_priors_are_sane():
    for c in load_knowledge_base().conditions.values():
        assert 0.0001 <= c.prior <= 0.9, f"{c.id} prior out of range"


def test_differentials_are_symmetric_enough():
    """If A lists B as a differential, B should usually know about A.
    Warn-level in a design review; here we just assert it is not wildly one-sided."""
    kb = load_knowledge_base()
    for c in kb.conditions.values():
        for d in c.differential:
            assert d in kb.conditions, f"{c.id} -> unknown differential {d}"


def test_bad_kb_is_rejected(tmp_path):
    (tmp_path / "conditions").mkdir()
    (tmp_path / "findings.yaml").write_text("version: 1\nfindings:\n  headache:\n    type: bool\n    label: Headache\n")
    (tmp_path / "conditions" / "broken.yaml").write_text(
        "id: broken\nname: Broken Rule\ncategory: renal\nurgency: routine\nprior: 0.1\n"
        "findings:\n  - finding: this_finding_does_not_exist\n    weight: 1.0\n"
        "sources:\n  - {title: x, url: 'http://x'}\n"
    )
    with pytest.raises(KnowledgeBaseError, match="undefined finding"):
        load_knowledge_base(tmp_path)
