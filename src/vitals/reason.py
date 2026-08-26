"""THE MAIN PATH. The local model reads the knowledge base and answers.

    complaint
        |
        v
  [ extract.py ]    pull out findings              fast, structural
        |
        v
  [ retrieval.py ]  select the relevant KB pages   grounding
        |
        v
  [ reason.py ]     ollama reads them and answers  <-- THE MODEL
        |
        v
  answer + real citations + a deterministic cross-check

THREE CONSTRAINTS ON THE MODEL, ALL ENFORCED IN CODE
Not asked for politely in the prompt - checked afterwards, in Python, where a
model cannot talk its way past them:

 1. IT CAN ONLY NAME CONDITIONS WE GAVE IT. Every condition_id in the reply is
    checked against the retrieved set. If it invents `space_flu`, that entry is
    dropped and the drop is reported on screen.

 2. IT NEVER WRITES A CITATION. It returns an id; we look the sources up from
    the knowledge base. A model cannot hallucinate a URL it was never asked to
    produce.

 3. TEMPERATURE 0. The same complaint gives the same answer. Anything else is
    untestable, and untestable means unprovable at a design review.

A fourth constraint lives in `_next_questions`: the model picks what to ask
next from a closed list of finding ids, and WE supply the wording.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from . import sensors
from .knowledge_base import KnowledgeBase
from .ollama_client import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    OLLAMA_HOST,
    OllamaUnavailable,
    generate,
    list_models,
    pull_model,
)
from .retrieval import Retrieved, as_context

CONFIDENCE_LEVELS = ("high", "moderate", "low")

# How many supporting/contradicting phrases we keep per candidate. A model that
# lists twelve is padding, and padding reads as certainty it has not earned.
MAX_EVIDENCE_PHRASES = 6

MAX_NEXT_QUESTIONS = 4

SYSTEM_PROMPT = """You are a medical decision-support assistant for a spacecraft crew medical officer (CMO).
The CMO is a trained crewmember, not a physician. A flight surgeon is available on the ground but with delay.

You will be given REFERENCE MATERIAL about spaceflight medical conditions, and a crewmember's complaint.

Absolute rules:
- Answer ONLY using conditions present in the reference material. Use their exact `id` values.
- If the complaint does not match anything in the reference material, say so by returning an empty differential. That is a correct and useful answer. Do not reach.
- Never state a diagnosis as fact. You produce a ranked differential for a human to act on.
- Never invent citations, study names, statistics, or numbers. If you did not read it in the reference material, do not write it.
- Reason about MICROGRAVITY. The reference material explains how each condition differs in space. A terrestrial answer is a wrong answer here.
- If anything suggests a time-critical problem, set escalate=true and say why in plain language.

About the differential:
- A differential with ONE entry is not a differential. Where the reference material supports it, give 2 to 4 entries: the most likely, plus the serious alternatives you considered and rejected.
- For entries you are rejecting, say so plainly with confidence "low" and put the reason in `against`. Showing what you ruled out and why is as useful as the top answer.
- `against` must contain actual contradicting evidence from the complaint. If nothing contradicts, leave it empty. Do not pad it with non-points like "this can happen on either side".

About questions:
- You will be given a list of findings that are ALREADY KNOWN, and a list that are STILL UNKNOWN.
- NEVER ask about something in the already-known list. The crewmember has already told you.
- Choose what to ask next from the STILL UNKNOWN list, by id, in `next_findings`.

Return ONLY a JSON object with this exact shape:
{
  "differential": [
    {
      "condition_id": "<id from the reference material>",
      "confidence": "high" | "moderate" | "low",
      "reasoning": "<2-3 sentences. What in the complaint points here, and what argues against.>",
      "supporting": ["<short phrase quoted or paraphrased from the complaint>"],
      "against": ["<actual contradicting evidence, or empty>"]
    }
  ],
  "escalate": true | false,
  "escalation_reason": "<empty string if escalate is false>",
  "next_findings": ["<finding id from the STILL UNKNOWN list>"],
  "uncertainty": "<what you are least sure about, in one sentence>"
}
No prose outside the JSON. No markdown fences."""


@dataclass
class Candidate:
    """One entry in the differential, after validation.

    `sources` and `recommend` come from the knowledge base, never from the
    model. See constraint 2 at the top of this file.
    """

    condition_id: str
    name: str
    urgency: str
    confidence: str
    reasoning: str
    supporting: list[str] = field(default_factory=list)
    against: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    recommend: list[str] = field(default_factory=list)


@dataclass
class Answer:
    """Everything one model call produced, after the constraints were applied."""

    differential: list[Candidate]
    escalate: bool
    escalation_reason: str
    next_questions: list[str]
    uncertainty: str
    model: str
    retrieved: list[str]
    sensor_status: str = "no sensors connected"
    dropped: list[str] = field(default_factory=list)   # ids the model invented
    raw: str = ""                                      # the unparsed reply, for debugging

    @property
    def top(self) -> Optional[Candidate]:
        return self.differential[0] if self.differential else None


def ask(
    knowledge_base: KnowledgeBase,
    complaint: str,
    retrieved: list[Retrieved],
    *,
    observations: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
    host: str = OLLAMA_HOST,
    timeout: float = DEFAULT_TIMEOUT,
) -> Answer:
    """Ask the local model, then hold its answer to the three constraints."""
    observations = observations or {}
    allowed_ids = {item.id for item in retrieved}

    known = {
        finding_id: value
        for finding_id, value in observations.items()
        if value is not None
    }
    unknown = _relevant_unknown_findings(retrieved, known)

    prompt = _build_prompt(knowledge_base, complaint, retrieved, known, unknown)
    raw = generate(
        prompt=prompt,
        system=SYSTEM_PROMPT,
        model=model,
        host=host,
        timeout=timeout,
    )

    reply = _parse_reply(raw)
    if reply is None:
        return Answer(
            differential=[],
            escalate=False,
            escalation_reason="",
            next_questions=[],
            uncertainty="model did not return valid JSON",
            model=model,
            retrieved=sorted(allowed_ids),
            raw=raw,
        )

    differential, dropped = _validated_differential(reply, knowledge_base, allowed_ids)
    escalate, escalation_reason = _escalation(reply, differential)

    return Answer(
        differential=differential,
        escalate=escalate,
        escalation_reason=escalation_reason,
        next_questions=_next_questions(knowledge_base, reply, known, set(unknown)),
        uncertainty=str(reply.get("uncertainty", "")).strip(),
        model=model,
        retrieved=sorted(allowed_ids),
        dropped=dropped,
        sensor_status=sensors.status(),
        raw=raw,
    )


# --- building the prompt ---------------------------------------------------


def _relevant_unknown_findings(
    retrieved: list[Retrieved],
    known: dict[str, Any],
) -> list[str]:
    """Findings the retrieved conditions care about that nobody has answered."""
    relevant = {
        evidence.finding
        for item in retrieved
        for evidence in item.condition.findings
    }
    return sorted(finding_id for finding_id in relevant if finding_id not in known)


def _build_prompt(
    knowledge_base: KnowledgeBase,
    complaint: str,
    retrieved: list[Retrieved],
    known: dict[str, Any],
    unknown: list[str],
) -> str:
    return (
        "REFERENCE MATERIAL (the only conditions you may name):\n\n"
        + as_context(retrieved)
        + "\n\n---\n\n"
        + sensors.as_context(sensors.read_all())
        + "\n\n---\n\n"
        + _known_block(knowledge_base, known)
        + "\n\n"
        + _unknown_block(knowledge_base, unknown)
        + '\n\n---\n\nCREWMEMBER COMPLAINT:\n"""\n'
        + complaint.strip()
        + '\n"""\n\nJSON:'
    )


def _known_block(knowledge_base: KnowledgeBase, known: dict[str, Any]) -> str:
    """What the crewmember has already told us. The model must not re-ask these."""
    if not known:
        return "ALREADY KNOWN: nothing yet."

    lines = [
        f"  - {finding_id} ({knowledge_base.label_for(finding_id)}) = {value}"
        for finding_id, value in sorted(known.items())
        if finding_id in knowledge_base.findings
    ]
    return "ALREADY KNOWN (do NOT ask about any of these again):\n" + "\n".join(lines)


def _unknown_block(knowledge_base: KnowledgeBase, unknown: list[str]) -> str:
    """The closed list the model must choose its next questions from."""
    if not unknown:
        return "STILL UNKNOWN: nothing left to ask."

    lines = [
        f"  - {finding_id}: {knowledge_base.question_for(finding_id)}"
        for finding_id in unknown
    ]
    return (
        "STILL UNKNOWN (choose next_findings from these ids only):\n"
        + "\n".join(lines)
    )


# --- holding the reply to the constraints ----------------------------------


def _parse_reply(raw: str) -> Optional[dict]:
    """The model's JSON, or None if it returned something unusable."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _validated_differential(
    reply: dict,
    knowledge_base: KnowledgeBase,
    allowed_ids: set[str],
) -> tuple[list[Candidate], list[str]]:
    """Constraints 1 and 2: only allowed ids, and citations come from the KB.

    Returns (candidates, ids that were dropped).
    """
    candidates: list[Candidate] = []
    dropped: list[str] = []

    for entry in reply.get("differential") or []:
        if not isinstance(entry, dict):
            continue

        condition_id = str(entry.get("condition_id", "")).strip()
        if condition_id not in allowed_ids:
            dropped.append(condition_id or "<blank>")
            continue

        condition = knowledge_base.conditions[condition_id]
        candidates.append(
            Candidate(
                condition_id=condition_id,
                name=condition.name,
                urgency=condition.urgency,
                confidence=_clean_confidence(entry.get("confidence")),
                reasoning=str(entry.get("reasoning", "")).strip(),
                supporting=_clean_phrases(entry.get("supporting")),
                against=_clean_phrases(entry.get("against")),
                sources=condition.sources,        # from the KB, never the model
                recommend=condition.recommend,
            )
        )

    return candidates, dropped


def _clean_confidence(value: Any) -> str:
    """Anything we do not recognise becomes "low". Never round uncertainty up."""
    confidence = str(value or "").lower()
    return confidence if confidence in CONFIDENCE_LEVELS else "low"


def _clean_phrases(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value][:MAX_EVIDENCE_PHRASES]


def _escalation(reply: dict, differential: list[Candidate]) -> tuple[bool, str]:
    """Whether to escalate, with a backstop under the model.

    If it named an urgent or emergency condition with real confidence and did
    not escalate, we escalate anyway. A model that forgets is not a reason for
    a crewmember to not get help.
    """
    escalate = bool(reply.get("escalate", False))
    reason = str(reply.get("escalation_reason", "")).strip()

    if escalate:
        return True, reason

    for candidate in differential:
        serious = candidate.urgency in ("urgent", "emergency")
        confident = candidate.confidence in ("high", "moderate")
        if serious and confident:
            return True, (
                f"{candidate.name} is a {candidate.urgency} condition and the model "
                f"rated it {candidate.confidence} confidence. Escalation added automatically."
            )

    return False, reason


def _next_questions(
    knowledge_base: KnowledgeBase,
    reply: dict,
    known: dict[str, Any],
    unknown: set[str],
) -> list[str]:
    """Turn the model's requested finding ids into real questions.

    Same trick as the citations: the model picks from a closed list, WE supply
    the wording. That kills a failure we saw in a real run, where the
    crewmember said "comes in waves" and the model came back asking "is the
    pain constant or does it come and go?" - a question already answered in the
    sentence it had just read.
    """
    questions: list[str] = []

    for value in reply.get("next_findings") or []:
        finding_id = str(value).strip()
        if finding_id in known or finding_id not in unknown:
            continue        # already answered, or not a real finding
        question = f"{knowledge_base.question_for(finding_id)}   [{finding_id}]"
        if question not in questions:
            questions.append(question)

    if not questions:
        questions = _free_text_fallback(knowledge_base, reply, known)

    return questions[:MAX_NEXT_QUESTIONS]


def _free_text_fallback(
    knowledge_base: KnowledgeBase,
    reply: dict,
    known: dict[str, Any],
) -> list[str]:
    """Used only when the model gave us no usable finding ids at all.

    Still refuses anything that names a finding the crewmember already answered.
    """
    known_labels = [
        knowledge_base.findings[finding_id].label.lower()
        for finding_id in known
        if finding_id in knowledge_base.findings
    ]

    questions = []
    for value in reply.get("next_questions") or []:
        question = str(value).strip()
        if not question:
            continue
        if any(label in question.lower() for label in known_labels):
            continue
        questions.append(question)
    return questions


__all__ = [
    "Answer",
    "Candidate",
    "OllamaUnavailable",
    "SYSTEM_PROMPT",
    "DEFAULT_MODEL",
    "OLLAMA_HOST",
    "ask",
    "list_models",
    "pull_model",
]
