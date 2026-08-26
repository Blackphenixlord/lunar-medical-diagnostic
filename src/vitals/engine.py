"""The deterministic engine: score every condition, rank them, decide who may
raise an alarm.

Since the rewrite this is the CROSS-CHECK, not the answer. reason.py is the
main path - the local model reads the knowledge base and replies. This engine
runs the same observations through fixed arithmetic so the two can be compared.
When they disagree, that is worth a human's attention, and `vitals ask
--crosscheck` prints exactly that.

Keeping it is cheap and it earns its place three ways: it is fully explainable,
it needs no model at all (so `vitals describe` works on a machine with no
ollama), and it is a standing regression test on the knowledge base.

scoring.py does the arithmetic. This file holds the POLICY - which is where
the interesting decisions, and all the past mistakes, live.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .knowledge_base import KnowledgeBase
from .models import Condition, Contribution
from .scoring import (
    Observations,
    RULED_OUT_SCORE,
    contributions_for,
    red_flags_present,
    support_for,
    to_log_odds,
    to_probability,
)

# How far the observations must move a condition before it is worth showing, in
# log-odds. 1.0 is roughly "one solid finding pointed this way".
MIN_NET_EVIDENCE = 1.0

# Only the leading few candidates may raise an alarm. See `_may_raise_alarm`.
ESCALATION_CANDIDATES = 3

# A red flag on a condition nobody is seriously considering is noise, not caution.
RED_FLAG_ESCALATION_THRESHOLD = 0.20

# An urgent or emergency condition at or above this probability always escalates.
URGENT_ESCALATION_THRESHOLD = 0.20


@dataclass
class ConditionScore:
    """One condition's result, with the full receipt attached."""

    condition: Condition
    log_odds: float
    probability: float
    contributions: list[Contribution]
    red_flags_hit: list[str] = field(default_factory=list)
    ruled_out: bool = False
    ruled_out_reason: str = ""
    required_unknown: list[Contribution] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.condition.id

    @property
    def name(self) -> str:
        return self.condition.name

    @property
    def urgency(self) -> str:
        return self.condition.urgency

    @property
    def observed_contributions(self) -> list[Contribution]:
        """Only the findings somebody actually answered."""
        return [c for c in self.contributions if c.state != "unknown"]

    @property
    def positive_findings(self) -> int:
        """How many observed findings actually point AT this condition."""
        return sum(1 for c in self.observed_contributions if c.delta > 0)

    @property
    def awaiting_required(self) -> list[str]:
        """Required findings nobody has answered yet.

        A condition in this state is a QUESTION, not a conclusion. You cannot
        raise an alarm about a laceration when nobody has established that
        there is a wound.
        """
        return [c.finding for c in self.required_unknown]

    @property
    def net_evidence(self) -> float:
        """How far the OBSERVATIONS moved this condition from its base rate.

        This is the number that actually matters, and it is not the
        probability. Fluid-shift congestion has a 45% base rate, so it shows up
        at ~57% on +0.50 of evidence - a number that says almost nothing about
        the crewmember in front of you. Probability answers "how likely". Net
        evidence answers "did we learn anything".
        """
        return sum(c.delta for c in self.contributions)

    def top_contributions(self, count: int = 4) -> list[Contribution]:
        """The biggest movers, positive or negative, for the `why:` block."""
        return sorted(self.contributions, key=lambda c: -abs(c.delta))[:count]


@dataclass
class Result:
    """Everything the engine concluded from one set of observations."""

    ranked: list[ConditionScore]
    escalate: bool
    escalation_reasons: list[str]
    unknown_findings: list[str]
    observations: Observations

    @property
    def top(self) -> Optional[ConditionScore]:
        return self.ranked[0] if self.ranked else None

    def get(self, condition_id: str) -> Optional[ConditionScore]:
        return next((score for score in self.ranked if score.id == condition_id), None)


def score_condition(
    condition: Condition,
    knowledge_base: KnowledgeBase,
    observations: Observations,
) -> ConditionScore:
    """Run one condition's rules and return its score with the receipt."""
    contributions, required_unknown, ruled_out_reason = contributions_for(
        condition, knowledge_base, observations
    )

    if ruled_out_reason:
        return ConditionScore(
            condition=condition,
            log_odds=RULED_OUT_SCORE,
            probability=0.0,
            contributions=contributions,
            ruled_out=True,
            ruled_out_reason=ruled_out_reason,
            required_unknown=required_unknown,
        )

    log_odds = to_log_odds(condition.prior) + sum(c.delta for c in contributions)

    return ConditionScore(
        condition=condition,
        log_odds=log_odds,
        probability=to_probability(log_odds),
        contributions=contributions,
        red_flags_hit=red_flags_present(condition, knowledge_base, observations),
        required_unknown=required_unknown,
    )


def diagnose(
    knowledge_base: KnowledgeBase,
    observations: Observations,
    *,
    min_probability: float = 0.02,
) -> Result:
    """Score every condition and rank them.

    RANKING IS STRICTLY BY PROBABILITY. Urgency does not reorder the list, and
    that is deliberate: we tried floating red-flagged conditions to the top and
    it put a 9% renal stone above a 99% head cold because both rules mention
    "fever". A ranking you cannot trust is worse than no ranking.

    Safety lives in a SEPARATE channel instead - `escalate` and
    `escalation_reasons`, which render.py prints ABOVE the list. The honest
    message is "most likely X, but escalate anyway because Y is on the table",
    not a reshuffled list that hides how likely things really are.
    """
    scored = [
        score_condition(condition, knowledge_base, observations)
        for condition in knowledge_base.conditions.values()
    ]

    candidates = [
        score for score in scored
        if not score.ruled_out and score.probability >= min_probability
    ]

    # Only filter once we actually KNOW something. A dict full of explicit
    # Nones is still nothing known, so it must behave like an empty dict.
    if any(value is not None for value in observations.values()):
        candidates = [
            score for score in candidates
            if has_supporting_evidence(score, knowledge_base)
        ]

    candidates.sort(key=lambda score: -score.probability)

    escalation_reasons = _collect_escalations(candidates, knowledge_base)

    findings_any_rule_uses = {
        evidence.finding
        for condition in knowledge_base.conditions.values()
        for evidence in condition.findings
    }
    unknown_findings = sorted(
        finding_id for finding_id in findings_any_rule_uses
        if observations.get(finding_id) is None
    )

    return Result(
        ranked=candidates,
        escalate=bool(escalation_reasons),
        escalation_reasons=sorted(set(escalation_reasons)),
        unknown_findings=unknown_findings,
        observations=observations,
    )


def has_supporting_evidence(score: ConditionScore, knowledge_base: KnowledgeBase) -> bool:
    """Is there enough here for this condition to be worth showing at all?

    Three gates, each one added after a bad real output:

    1. SOMETHING must have been observed. Obvious, but it has to be first.

    2. At least one observed finding must be about the PERSON, not the
       context. "You have been on orbit 2 days" is not a symptom, and on its
       own it floated adaptation back pain to 69% for a crewmember who never
       mentioned their back. Hence the `contextual` flag in findings.yaml.

    3. The evidence has to actually point HERE. One weak non-specific hit is
       not evidence, and a condition whose score barely moved is just its base
       rate wearing a percentage sign - that is how a stuffy nose ended up on
       screen at 57% next to a kidney stone.
    """
    observed = score.observed_contributions
    if not observed:
        return False

    substantive = [
        c for c in observed
        if not knowledge_base.findings[c.finding].contextual
    ]
    if not substantive:
        return False

    only_one_weak_hit = (
        len(observed) < 2
        and max(abs(c.delta) for c in observed) < 1.0
    )
    if only_one_weak_hit:
        return False

    return score.net_evidence >= MIN_NET_EVIDENCE


def _collect_escalations(
    ranked: list[ConditionScore],
    knowledge_base: KnowledgeBase,
) -> list[str]:
    """Decide what, if anything, gets escalated to the flight surgeon.

    Only the leading few conditions are considered, not everything still
    standing. We shipped this wrong once: `fever` is a red flag in the dental,
    wound, renal and infection rules, so a crewmember with a dental abscess was
    told to escalate for a laceration they did not have, a kidney stone they
    did not have, and a chest infection they did not have. Four alarms, one
    problem, and a CMO who now trusts none of them.
    """
    reasons: list[str] = []

    for rank, score in enumerate(ranked[:ESCALATION_CANDIDATES]):
        if not _may_raise_alarm(score, rank):
            continue

        if score.red_flags_hit and score.probability >= RED_FLAG_ESCALATION_THRESHOLD:
            labels = ", ".join(
                knowledge_base.label_for(finding_id) for finding_id in score.red_flags_hit
            )
            reasons.append(f"{score.name}: red flag present ({labels})")

        if score.urgency in ("urgent", "emergency") and score.probability >= URGENT_ESCALATION_THRESHOLD:
            reasons.append(
                f"{score.name}: {score.urgency} condition at {score.probability:.0%}"
            )

    return reasons


def _may_raise_alarm(score: ConditionScore, rank: int) -> bool:
    """Who is allowed to sound an alarm. Two gates, both learned the hard way.

    1. A condition still waiting on a REQUIRED finding cannot alarm. Nobody had
       established there was a wound, yet the laceration rule was shouting
       because the crewmember had a fever.

    2. A single finding that happens to be a red flag in five different rules
       must not fire five alarms. So a non-leading candidate needs at least two
       findings actually pointing at it. The leading candidate is exempt - if
       it is what we think is going on, we say so.
    """
    if score.awaiting_required:
        return False
    return rank == 0 or score.positive_findings >= 2


def next_best_questions(
    knowledge_base: KnowledgeBase,
    result: Result,
    count: int = 3,
) -> list[tuple[str, str]]:
    """Which unanswered question would separate the candidates fastest?

    Returns (finding_id, question) pairs.

    Each unknown finding is scored by how far it would SPREAD the contenders
    apart - a cheap stand-in for information gain. It means the interview asks
    the useful question instead of question number one.
    """
    contenders = _question_pool(knowledge_base, result)
    if len(contenders) < 2:
        return []

    ordered = (
        _unknown_required_findings(contenders, result)
        + _best_discriminators(contenders, result)
    )

    picked: list[str] = []
    for finding_id in ordered:
        if finding_id not in picked:
            picked.append(finding_id)

    return [
        (finding_id, knowledge_base.question_for(finding_id))
        for finding_id in picked[:count]
    ]


def _question_pool(knowledge_base: KnowledgeBase, result: Result) -> list[Condition]:
    """The conditions a question should be trying to tell apart.

    When only one candidate survives we deliberately pad the pool with the
    highest-base-rate conditions in the whole KB rather than returning nothing.
    A single candidate is exactly when you most want a question that could
    bring a competitor back into play. That is how you avoid anchoring.
    """
    pool = [score.condition for score in result.ranked[:4]]
    if len(pool) >= 2:
        return pool

    already_in = {condition.id for condition in pool}
    fallback = sorted(
        (c for c in knowledge_base.conditions.values() if c.id not in already_in),
        key=lambda c: -c.prior,
    )
    pool.extend(fallback[: 4 - len(pool)])
    return pool


def _unknown_required_findings(pool: list[Condition], result: Result) -> list[str]:
    """Required findings nobody has answered. These beat everything else.

    If a condition cannot be called without knowing X, then X is the fastest
    question in the room - it either confirms the candidate or removes it.
    Without this, a post-EVA crewmember with confusion and weakness showed
    "laceration 24%" purely because weakness appears in that rule, while nobody
    had asked the one question that settles it: is there a wound?
    """
    unknown = set(result.unknown_findings)
    ordered: list[str] = []
    for condition in pool:
        for evidence in condition.findings:
            if evidence.required and evidence.finding in unknown:
                if evidence.finding not in ordered:
                    ordered.append(evidence.finding)
    return ordered


def _best_discriminators(pool: list[Condition], result: Result) -> list[str]:
    """Unknown findings ranked by how differently the contenders weigh them.

    A finding all four candidates weigh the same tells them apart by nothing.
    A finding one candidate weighs +3.0 and another -1.0 splits the field.
    """
    spread: dict[str, float] = {}

    for finding_id in result.unknown_findings:
        weights = []
        for condition in pool:
            evidence = next(
                (e for e in condition.findings if e.finding == finding_id), None
            )
            weights.append(evidence.weight if evidence else 0.0)
        if any(weights):
            spread[finding_id] = max(weights) - min(weights)

    return [
        finding_id
        for finding_id, _ in sorted(spread.items(), key=lambda item: -item[1])
    ]


__all__ = [
    "ConditionScore",
    "Result",
    "Observations",
    "diagnose",
    "score_condition",
    "next_best_questions",
    "has_supporting_evidence",
    "support_for",
]
