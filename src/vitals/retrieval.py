"""Choose which pages of the knowledge base the model is allowed to read.

This is the "R" in RAG, and it is the whole reason the model can be trusted
with this job. A raw LLM asked "what is wrong with this astronaut?" answers
from generic Earth medicine, because that is what the internet is made of.
Handing it the actual spaceflight literature first is what makes the answer
about SPACE.

TWO STAGES, AND STAGE ONE IS FREE
    1. Structural. The extractor already mapped the complaint onto finding ids.
       Any condition whose rules reference those findings is a candidate. No
       embeddings, no second model, instant.
    2. Lexical. A word-overlap pass over each condition's prose catches what
       the regexes missed - an unusual phrasing that still says "vertigo".

WE DELIBERATELY OVER-RETRIEVE
    Sending six conditions instead of three costs a few hundred tokens. Missing
    the one that was actually right costs the diagnosis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .knowledge_base import KnowledgeBase
from .models import Condition

# How much a single word-overlap hit is worth, relative to a finding match.
LEXICAL_HIT_SCORE = 0.6

STOPWORDS = {
    # ordinary English filler
    "the", "and", "for", "with", "was", "are", "have", "has", "had", "not",
    "but", "you", "your", "this", "that", "from", "there", "here", "been",
    "very", "just", "like", "really", "feel", "feels", "feeling", "get",
    "gets", "got", "day", "days", "about", "since", "when", "what", "some",
    "than", "then", "them", "they", "its", "it's", "i'm", "im", "does",
    # words in almost every condition file, so they match everything and
    # therefore discriminate nothing. Classic high-document-frequency noise.
    "flight", "space", "spaceflight", "crew", "crewmember", "orbit", "mission",
    "earth", "condition", "microgravity", "medical", "symptoms", "symptom",
}


@dataclass
class Retrieved:
    """One condition selected for the model, and the reason it was selected."""

    condition: Condition
    score: float
    why: str            # which route surfaced it - shown by `ask --verbose`

    @property
    def id(self) -> str:
        return self.condition.id


def retrieve(
    knowledge_base: KnowledgeBase,
    complaint: str,
    observations: dict[str, Any] | None = None,
    *,
    limit: int = 6,
    always_include_emergencies: bool = True,
) -> list[Retrieved]:
    """Return the conditions worth showing the model, best first."""
    observations = observations or {}
    known_findings = {
        finding_id for finding_id, value in observations.items() if value is not None
    }

    scored: dict[str, Retrieved] = {}
    _score_by_findings(knowledge_base, known_findings, scored)
    _score_by_words(knowledge_base, complaint, scored)

    ranked = sorted(scored.values(), key=lambda r: -r.score)[:limit]

    if not ranked:
        return _fallback_to_base_rates(knowledge_base, limit)

    if always_include_emergencies:
        ranked.extend(_missing_emergencies(knowledge_base, ranked))

    return ranked


def _score_by_findings(
    knowledge_base: KnowledgeBase,
    known_findings: set[str],
    scored: dict[str, Retrieved],
) -> None:
    """Stage 1: conditions whose rules mention findings we actually extracted.

    Weighted by how much the rule CARES about those findings, so a condition
    that merely mentions nausea in passing does not outrank one built around it.
    """
    for condition in knowledge_base.conditions.values():
        referenced = {evidence.finding for evidence in condition.findings}
        overlap = referenced & known_findings
        if not overlap:
            continue

        strength = sum(
            abs(evidence.weight) for evidence in condition.findings
            if evidence.finding in overlap
        )
        scored[condition.id] = Retrieved(
            condition=condition,
            score=strength,
            why=f"findings: {', '.join(sorted(overlap))}",
        )


def _score_by_words(
    knowledge_base: KnowledgeBase,
    complaint: str,
    scored: dict[str, Retrieved],
) -> None:
    """Stage 2: word overlap with each condition's prose. Catches regex misses."""
    complaint_terms = _content_words(complaint)

    for condition in knowledge_base.conditions.values():
        prose = " ".join([
            condition.name,
            " ".join(condition.aka),
            condition.description,
            condition.microgravity_note,
        ])
        hits = complaint_terms & _content_words(prose)
        if not hits:
            continue

        bump = LEXICAL_HIT_SCORE * len(hits)
        existing = scored.get(condition.id)
        if existing:
            existing.score += bump
            existing.why += f" + words: {', '.join(sorted(hits))}"
        else:
            scored[condition.id] = Retrieved(
                condition=condition,
                score=bump,
                why=f"words: {', '.join(sorted(hits))}",
            )


def _content_words(text: str) -> set[str]:
    """Lowercase words worth matching on: 3+ letters, not a stopword."""
    words = re.findall(r"[a-z']+", text.lower())
    return {word for word in words if len(word) > 2 and word not in STOPWORDS}


def _fallback_to_base_rates(knowledge_base: KnowledgeBase, limit: int) -> list[Retrieved]:
    """Nothing matched at all - hand over the commonest conditions anyway.

    An empty reference block would leave the model answering from its own
    priors with no spaceflight grounding, which is the exact failure this
    module exists to prevent.
    """
    commonest = sorted(knowledge_base.conditions.values(), key=lambda c: -c.prior)
    return [
        Retrieved(condition, 0.0, "fallback: nothing matched, showing highest base rates")
        for condition in commonest[:limit]
    ]


def _missing_emergencies(
    knowledge_base: KnowledgeBase,
    ranked: list[Retrieved],
) -> list[Retrieved]:
    """Never let a killer fall off the list on a scoring technicality."""
    already_included = {item.id for item in ranked}
    return [
        Retrieved(condition, 0.0, "always shown: emergency condition")
        for condition in knowledge_base.conditions.values()
        if condition.urgency == "emergency" and condition.id not in already_included
    ]


def as_context(retrieved: list[Retrieved]) -> str:
    """Render the retrieved conditions as the reference block the model reads.

    NOTE WHAT IS NOT IN HERE: priors and weights. Those numbers are ours, not
    the literature's, and feeding invented numbers to a model just launders
    them into confident prose. The model gets the research - descriptions, how
    microgravity changes things, what to do, what to rule out - and nothing we
    made up. tests/test_reason.py fails the build if a number leaks in.
    """
    blocks = []

    for item in retrieved:
        condition = item.condition
        lines = [
            f"### {condition.id}",
            f"name: {condition.name}",
            f"also known as: {', '.join(condition.aka)}" if condition.aka else "",
            f"urgency: {condition.urgency}",
            f"description: {condition.description}",
            f"how microgravity changes this: {condition.microgravity_note}",
        ]
        if condition.recommend:
            lines.append(
                "recommended actions:\n"
                + "\n".join(f"  - {action}" for action in condition.recommend)
            )
        if condition.differential:
            lines.append(f"commonly confused with: {', '.join(condition.differential)}")

        blocks.append("\n".join(line for line in lines if line))

    return "\n\n".join(blocks)
