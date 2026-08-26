"""Run the whole prompt bank and score it.

This is how you find out whether the thing actually works, instead of trying
three prompts you already know the answer to and declaring victory.

TWO NUMBERS MATTER, AND THEY ARE NOT THE SAME

    hit rate      on prompts with a right answer, did the top entry match?
    refusal rate  on prompts where the correct answer is "nothing in the
                  knowledge base fits", did it correctly return nothing?

A system that scores 100% on hits and 0% on refusals is worse than useless: it
means it always names something, which means a dental abscess comes back as a
kidney stone. Track both, report both, never quote one without the other.

A THIRD NUMBER OVERRIDES BOTH
    Missed escalations. Escalating when you did not need to is a nuisance. NOT
    escalating when you needed to is the one that hurts someone, so any missed
    escalation fails the run regardless of the other two scores.

    python -m vitals bench
    python -m vitals bench --category mimic
    python -m vitals bench --limit 5
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from . import sensors
from .extract import KeywordExtractor
from .knowledge_base import KnowledgeBase
from .ollama_client import DEFAULT_MODEL, OLLAMA_HOST, OllamaUnavailable
from .reason import ask
from .retrieval import retrieve

RETRIEVAL_LIMIT = 6


def prompts_path() -> Path:
    return Path(__file__).resolve().parents[2] / "prompts" / "complaints.yaml"


def load_prompts(path: str | Path | None = None) -> list[dict[str, Any]]:
    source = Path(path) if path else prompts_path()
    document = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    return document.get("prompts") or []


@dataclass
class Outcome:
    """What happened on one prompt."""

    id: str
    category: str
    expect: str                 # the condition id we wanted, or "none"
    got: str                    # what came back, or "none"
    hit: bool
    expected_escalate: bool
    got_escalate: bool
    elapsed: float
    why: str = ""               # what this prompt is testing, from the yaml
    error: str = ""             # set when the call failed outright

    @property
    def escalation_ok(self) -> bool:
        return self.got_escalate or not self.expected_escalate

    @property
    def missed_escalation(self) -> bool:
        return self.expected_escalate and not self.got_escalate


@dataclass
class Report:
    """Every outcome from one run, with the scores derived on demand."""

    outcomes: list[Outcome] = field(default_factory=list)
    model: str = DEFAULT_MODEL

    @property
    def naming(self) -> list[Outcome]:
        """Prompts that had a right answer to name."""
        return [o for o in self.outcomes if o.expect != "none" and not o.error]

    @property
    def refusing(self) -> list[Outcome]:
        """Prompts where the right answer was to name nothing."""
        return [o for o in self.outcomes if o.expect == "none" and not o.error]

    @property
    def hit_rate(self) -> float:
        return _rate(self.naming)

    @property
    def refusal_rate(self) -> float:
        return _rate(self.refusing)

    @property
    def missed_escalations(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.missed_escalation]

    @property
    def failures(self) -> list[Outcome]:
        return [o for o in self.outcomes if not o.hit and not o.error]

    @property
    def errors(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.error]

    def by_category(self) -> dict[str, list[Outcome]]:
        grouped: dict[str, list[Outcome]] = {}
        for outcome in self.outcomes:
            if not outcome.error:
                grouped.setdefault(outcome.category, []).append(outcome)
        return grouped


def _rate(outcomes: list[Outcome]) -> float:
    return (sum(o.hit for o in outcomes) / len(outcomes)) if outcomes else 0.0


def run_one(
    knowledge_base: KnowledgeBase,
    prompt: dict,
    *,
    model: str,
    host: str = OLLAMA_HOST,
) -> Outcome:
    """One prompt, through the exact pipeline `vitals ask` uses."""
    started = time.time()

    observations = KeywordExtractor().extract(prompt["text"], knowledge_base)
    observations.update(sensors.as_observations(sensors.read_all()))
    retrieved = retrieve(knowledge_base, prompt["text"], observations, limit=RETRIEVAL_LIMIT)

    try:
        answer = ask(knowledge_base, prompt["text"], retrieved,
                     observations=observations, model=model, host=host)
    except OllamaUnavailable as exc:
        return Outcome(
            id=prompt["id"],
            category=prompt.get("category", ""),
            expect=prompt["expect"],
            got="",
            hit=False,
            expected_escalate=bool(prompt.get("escalate")),
            got_escalate=False,
            elapsed=time.time() - started,
            why=prompt.get("why", ""),
            error=str(exc),
        )

    got = answer.top.condition_id if answer.top else "none"
    return Outcome(
        id=prompt["id"],
        category=prompt.get("category", ""),
        expect=prompt["expect"],
        got=got,
        hit=(got == prompt["expect"]),
        expected_escalate=bool(prompt.get("escalate")),
        got_escalate=answer.escalate,
        elapsed=round(time.time() - started, 1),
        why=prompt.get("why", "").strip(),
    )


def run(
    knowledge_base: KnowledgeBase,
    prompts: list[dict],
    *,
    model: str = DEFAULT_MODEL,
    host: str = OLLAMA_HOST,
    on_result: Optional[Callable[[Outcome], None]] = None,
) -> Report:
    """Run every prompt. `on_result` fires after each, for live output."""
    report = Report(model=model)
    for prompt in prompts:
        outcome = run_one(knowledge_base, prompt, model=model, host=host)
        report.outcomes.append(outcome)
        if on_result:
            on_result(outcome)
    return report
