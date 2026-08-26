"""The arithmetic behind the deterministic cross-check engine.

One paragraph you can put on a slide:

    Every condition starts at its base rate, written as log-odds. Every
    observed finding adds or subtracts a weight from that running total.
    Adding log-odds is the same as multiplying probabilities, so this is
    naive Bayes written out longhand - and because it is written out
    longhand, it can show its work.

This module does the sums. engine.py decides what to do with them.

WHY NOT A NEURAL NET
    A dozen conditions and no in-flight training data. NASA's own modelling
    papers say the medical event data is severely limited. A learned model
    would be fitting noise, and could not explain itself to a flight surgeon.
    The LLM sits in FRONT of this (see reason.py), turning English into
    findings. It never overrides the medical logic.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from .knowledge_base import KnowledgeBase
from .models import Condition, Contribution, FindingDef

# An observation value may be True/False, a number, None (explicitly unknown),
# or simply missing from the dict (also unknown).
Observations = dict[str, Any]

# The log-odds we assign to a condition that has been ruled out. Any number far
# below every real score works; this one is obvious in a debug print.
RULED_OUT_SCORE = -999.0


def to_log_odds(probability: float) -> float:
    """Probability -> log-odds, clamped so 0 and 1 do not become infinities."""
    probability = min(max(probability, 1e-6), 1 - 1e-6)
    return math.log(probability / (1 - probability))


def to_probability(log_odds: float) -> float:
    """Log-odds -> probability. Saturates instead of overflowing exp()."""
    if log_odds < -60:
        return 0.0
    if log_odds > 60:
        return 1.0
    return 1 / (1 + math.exp(-log_odds))


def support_for(definition: FindingDef, value: Any) -> Optional[float]:
    """Turn one raw observation into a -1..+1 support value.

    Returns None for "we do not know", and unknown must never move a score.
    That is the whole difference between a diagnostic aid and a guessing
    machine: silence is not evidence.
    """
    if value is None:
        return None

    if definition.type == "bool":
        return _support_from_boolean(value)

    if definition.type == "enum":
        return 1.0 if str(value) in definition.values else -1.0

    return _support_from_number(definition, value)


def _support_from_boolean(value: Any) -> Optional[float]:
    """Yes/no, however it was written down."""
    if not isinstance(value, str):
        return 1.0 if value else -1.0

    text = value.strip().lower()
    if text in ("yes", "y", "true", "present", "1"):
        return 1.0
    if text in ("no", "n", "false", "absent", "0"):
        return -1.0
    return None      # "unsure", "?", "" and anything unrecognised stay unknown


def _support_from_number(definition: FindingDef, value: Any) -> Optional[float]:
    """Measured value -> support, using the finding's ScoringCurve."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    curve = definition.scoring
    if curve is None:
        # No curve configured: treat any non-zero reading as present.
        return 1.0 if number else -1.0

    span = curve.span or 1.0
    support = (number - curve.threshold) / span
    if curve.direction == "low":
        support = -support
    return max(-1.0, min(1.0, support))


def contributions_for(
    condition: Condition,
    knowledge_base: KnowledgeBase,
    observations: Observations,
) -> tuple[list[Contribution], list[Contribution], str]:
    """Weigh every rule in one condition against what we observed.

    Returns (all contributions, the required-but-unknown subset, ruled-out reason).
    An empty reason means the condition is still in play.

    THE ASYMMETRY, AND WHY IT IS NOT A BUG
    We got this wrong twice in one afternoon and the comments are here so
    nobody "fixes" it back:

      1. The first version treated a low measurement as plain "absent" and gave
         it absent_weight 0, so "flight day 2" contributed NOTHING - throwing
         away the single best piece of evidence for space motion sickness.

      2. So we made measurements symmetric: delta = weight * support. That was
         worse. Fluid-shift congestion carries fever at -2.0 ("a fever argues
         against me"), so a NORMAL temperature scored -2.0 * -1.0 = +2.00 and
         shoved a stuffy nose to 86% in a crewmember with a kidney stone.

    The lesson: "a fever would argue against this" and "no fever is evidence
    for this" are different claims, and only the rule author knows which one
    they mean. So they write it down. Anything genuinely two-sided - mission
    day, hours of sleep - sets absent_weight explicitly in the KB.
    """
    contributions: list[Contribution] = []
    required_unknown: list[Contribution] = []
    ruled_out_reason = ""

    for evidence in condition.findings:
        definition = knowledge_base.findings.get(evidence.finding)
        if definition is None:
            continue        # _cross_check should have caught this at load time

        observed = observations.get(evidence.finding)
        support = support_for(definition, observed)

        if support is None:
            unknown = Contribution(
                finding=evidence.finding,
                label=definition.label,
                observed=None,
                support=0.0,
                weight=evidence.weight,
                delta=0.0,
                state="unknown",
            )
            contributions.append(unknown)
            if evidence.required:
                required_unknown.append(unknown)
            continue

        if support > 0:
            delta = evidence.weight * support
            state = "present"
        else:
            delta = evidence.absent_weight * abs(support)
            state = "absent"
            if evidence.required:
                ruled_out_reason = (
                    f"{definition.label} is required for this diagnosis "
                    f"and was ruled out by the observation"
                )

        contributions.append(
            Contribution(
                finding=evidence.finding,
                label=definition.label,
                observed=observed,
                support=support,
                weight=evidence.weight,
                delta=delta,
                state=state,
            )
        )

    return contributions, required_unknown, ruled_out_reason


def red_flags_present(
    condition: Condition,
    knowledge_base: KnowledgeBase,
    observations: Observations,
) -> list[str]:
    """Which of this condition's red-flag findings were actually observed."""
    present: list[str] = []
    for finding_id in condition.red_flags:
        definition = knowledge_base.findings.get(finding_id)
        if definition is None:
            continue
        support = support_for(definition, observations.get(finding_id))
        if support is not None and support > 0:
            present.append(finding_id)
    return present
