"""The nouns of the system. Data only - no behaviour, nothing clever.

Every other module reads or produces these. Keeping them in one short file
means a reviewer can learn the whole vocabulary in two minutes, which is the
entire point of putting them here instead of scattering them.

    FindingDef    one entry in the controlled vocabulary (kb/findings.yaml).
                  "fever", "flank_pain", "mission_elapsed_days".

    Evidence      one line inside a condition rule: this finding, this much
                  weight. The medical claim itself.

    Condition     one diagnosis we can name, with its rules and its citations.

    Contribution  the receipt: this finding, observed at this value, moved the
                  score by this much. Produced by scoring.py, printed by
                  render.py. It is what makes an answer defensible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ScoringCurve:
    """How a measured number becomes a -1..+1 support value.

    Example - fever, defined as direction "high", threshold 37.5, span 1.5:

        36.8 C  ->  (36.8 - 37.5) / 1.5  =  -0.47   argues against
        37.5 C  ->                           0.00   says nothing
        39.0 C  ->                          +1.00   fully supports (clamped)

    `direction: low` flips the sign, for findings where a SMALL number is the
    worrying one - hours of sleep, urine output.
    """

    direction: str = "high"     # "high": big values support. "low": small values support.
    threshold: float = 0.0      # the value at which support crosses zero
    span: float = 1.0           # how far past the threshold before support saturates at +/-1


@dataclass
class FindingDef:
    """One entry from kb/findings.yaml - the controlled vocabulary.

    Nothing anywhere in the system may name a finding that is not defined here.
    That is what stops the model, the extractor and Joaquin's rules from
    drifting apart into three different spellings of "stuffy nose".
    """

    id: str
    type: str                   # bool | scale | num | enum
    label: str                  # human wording, used in output
    ask: str = ""               # the question to put to a crewmember
    unit: str = ""              # "C", "days", "hours"
    values: list[str] = field(default_factory=list)   # for type "enum"
    scoring: Optional[ScoringCurve] = None
    contextual: bool = False
    """True for background facts rather than symptoms - mission day, recent EVA.

    Context modulates a diagnosis; it must not create one on its own. A rule
    supported ONLY by contextual findings never reaches the screen. See
    `engine.has_supporting_evidence` for the bug that put this flag here.
    """


@dataclass
class Evidence:
    """One `findings:` entry inside a condition file. The medical claim.

    weight          added to the running score when the finding is PRESENT.
    absent_weight   added when the finding is explicitly ABSENT. Defaults to 0,
                    which reads as "the absence tells us nothing" - the honest
                    default, and the reason a normal temperature no longer
                    argues FOR a head cold. See scoring.py.
    required        no this finding, no diagnosis. Absent rules the condition
                    out entirely; unknown means the condition is still an open
                    question and may not raise an alarm.
    note            free text: why this weight, in the rule author's words.
    """

    finding: str
    weight: float
    absent_weight: float = 0.0
    required: bool = False
    note: str = ""


@dataclass
class Condition:
    """One diagnosis, its rules, and its sources.

    `prior` is the base rate before anyone says anything. `sources` is what
    makes this defensible - see the caveat in README about which numbers are
    cited and which are ours.
    """

    id: str
    name: str
    category: str
    urgency: str                # routine | monitor | urgent | emergency
    prior: float
    findings: list[Evidence]
    description: str = ""
    microgravity_note: str = ""     # how this differs from the same thing on Earth
    aka: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    recommend: list[str] = field(default_factory=list)
    differential: list[str] = field(default_factory=list)   # commonly confused with
    sources: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Contribution:
    """Why the score moved. One line of the receipt.

    observed  what the crewmember said or an instrument measured
    support   that observation normalised to -1..+1
    weight    what the rule says this finding is worth
    delta     what actually got added to the running score
    state     present | absent | unknown
    """

    finding: str
    label: str
    observed: Any
    support: float
    weight: float
    delta: float
    state: str


URGENCY_ORDER = {"routine": 0, "monitor": 1, "urgent": 2, "emergency": 3}

URGENCY_TAG = {
    "emergency": "[EMERGENCY]",
    "urgent":    "[URGENT]   ",
    "monitor":   "[MONITOR]  ",
    "routine":   "[routine]  ",
}
