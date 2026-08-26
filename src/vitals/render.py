"""Everything that prints to a terminal.

Kept in one file so that cli.py can be about arguments and this can be about
words. It also means the wording a crewmember reads is reviewable in one place
- which matters, because half of these lines are safety messages.

TWO RULES FOR EVERY SCREEN IN HERE
    1. Say it is decision support, not a diagnosis. Every time. No exceptions.
    2. Never print a number without saying where it came from.
"""

from __future__ import annotations

import sys
from typing import Iterable

from .engine import ConditionScore, Result, next_best_questions
from .knowledge_base import KnowledgeBase
from .models import URGENCY_TAG
from .reason import Answer

RULE = "=" * 66

DISCLAIMER = "decision support only, not a diagnosis"

NOTHING_MATCHED = """
  Nothing in the knowledge base fits this.

  That is a real answer, not a failure: it means we have no rule for this yet.
  Log the case and take it to the flight surgeon.
"""


def banner(title: str, subtitle: str = "") -> None:
    print()
    print(RULE)
    print(f"  {title}")
    if subtitle:
        print(f"  {subtitle}")
    print(RULE)


def error(message: str) -> None:
    print(f"\n{message}\n", file=sys.stderr)


def sources(entries: Iterable[dict], *, note: str = "") -> None:
    print(f"\n  Sources{note}:")
    for entry in entries:
        print(f"    - {entry['title']}\n      {entry['url']}")


# --- the model's answer (`vitals ask`) -------------------------------------


def model_answer(answer: Answer, elapsed_seconds: float) -> None:
    """The main output of the whole system."""
    banner(f"VITALS  -  {DISCLAIMER}",
           f"[model: {answer.model}  |  {elapsed_seconds:.0f}s]")

    if answer.sensor_status == "no sensors connected":
        print("\n  NOTE: no instruments attached. Everything below is from what the")
        print("        crewmember said. No vital sign has been measured.")

    if answer.dropped:
        print(f"\n  [dropped {len(answer.dropped)} condition(s) the model invented: "
              f"{', '.join(answer.dropped)}]")

    if answer.escalate:
        print("\n  *** ESCALATE TO FLIGHT SURGEON ***")
        print(f"      {answer.escalation_reason}")

    if not answer.differential:
        print(NOTHING_MATCHED)
        return

    for position, candidate in enumerate(answer.differential, 1):
        tag = URGENCY_TAG.get(candidate.urgency, "")
        print(f"\n  {position}. {tag} {candidate.name}   [{candidate.confidence} confidence]")
        if candidate.reasoning:
            print(f"      {candidate.reasoning}")
        for phrase in candidate.supporting:
            print(f"        + {phrase}")
        for phrase in candidate.against:
            print(f"        - {phrase}")

    top = answer.differential[0]
    print(f"\n  ---- Recommended next steps for: {top.name} ----")
    for action in top.recommend:
        print(f"    * {action}")

    if answer.next_questions:
        print("\n  ---- Ask these next ----")
        for question in answer.next_questions:
            print(f"    ? {question}")

    if answer.uncertainty:
        print(f"\n  Least certain about: {answer.uncertainty}")

    sources(top.sources, note=f" for {top.condition_id} (from the knowledge base, not the model)")


def crosscheck(model_top_id: str | None, engine_top_id: str | None) -> None:
    """How the deterministic engine voted, next to the model.

    They see different things - the engine only reads findings the extractor
    caught, the model reads the whole sentence - so a disagreement is
    information, not a bug.
    """
    print("\n  ---- cross-check: deterministic engine ----")

    if engine_top_id is None:
        print("    engine had too little to go on (it only sees extracted findings)")
    elif engine_top_id == model_top_id:
        print(f"    agrees: {engine_top_id}")
    else:
        print(f"    DISAGREES: engine says {engine_top_id}, model says {model_top_id}")
        print("    Worth a look. They see different things - the engine only reads")
        print("    findings the extractor caught, the model reads your whole sentence.")


def retrieval_trace(retrieved, observations: dict, sensor_status: str) -> None:
    """`--verbose`: exactly what the model was allowed to see, and why."""
    print(f"\n[retrieved {len(retrieved)} conditions for grounding]")
    for item in retrieved:
        print(f"    {item.score:6.1f}  {item.id:<28} {item.why}")
    print(f"[sensors: {sensor_status}]")
    print(f"[findings extracted: {', '.join(sorted(observations)) or 'none'}]")


# --- the deterministic engine (`vitals describe`, `case`, `interview`) ------


def engine_result(
    knowledge_base: KnowledgeBase,
    result: Result,
    *,
    show_all: bool = False,
) -> None:
    banner(f"VITALS DIFFERENTIAL  -  {DISCLAIMER}")

    if not result.ranked:
        print(NOTHING_MATCHED)
        return

    if result.escalate:
        print("\n  *** ESCALATE TO FLIGHT SURGEON ***")
        for reason in result.escalation_reasons:
            print(f"      - {reason}")

    shown = result.ranked if show_all else result.ranked[:4]
    for position, score in enumerate(shown, 1):
        _one_scored_condition(knowledge_base, score, position)

    top = result.ranked[0]
    print(f"\n  ---- Recommended next steps for: {top.name} ----")
    for action in top.condition.recommend:
        print(f"    * {action}")
    if top.condition.differential:
        print(f"\n  Must also rule out: {', '.join(top.condition.differential)}")

    questions = next_best_questions(knowledge_base, result, 3)
    if questions:
        print("\n  ---- Ask these next (highest discrimination) ----")
        for finding_id, question in questions:
            print(f"    ? {question}   [{finding_id}]")

    sources(top.condition.sources, note=f" for {top.condition.id}")
    print(f"\n{RULE}\n")


def _one_scored_condition(
    knowledge_base: KnowledgeBase,
    score: ConditionScore,
    position: int,
) -> None:
    tag = URGENCY_TAG.get(score.urgency, "")
    print(f"\n  {position}. {tag} {score.name}   {score.probability:>5.0%}"
          f"   [evidence {score.net_evidence:+.1f}]")

    if score.red_flags_hit:
        labels = ", ".join(
            knowledge_base.label_for(finding_id) for finding_id in score.red_flags_hit
        )
        print(f"      RED FLAG: {labels}")

    print("      why:")
    for contribution in score.top_contributions(4):
        if contribution.state == "unknown" or abs(contribution.delta) < 0.05:
            continue
        sign = "+" if contribution.delta > 0 else "-"
        value = contribution.observed
        if isinstance(value, bool):
            value = "yes" if value else "no"
        print(f"        {sign} {contribution.label} = {value}   ({contribution.delta:+.2f})")


def extracted_findings(backend_name: str, observations: dict) -> None:
    print(f"\n[intake: {backend_name} backend]")
    if not observations:
        print("  extracted nothing - try the structured interview: python -m vitals interview")
        return
    print("  extracted findings:")
    for finding_id, value in sorted(observations.items()):
        print(f"    {finding_id:<30} = {value}")


# --- `vitals explain` ------------------------------------------------------


def condition_detail(knowledge_base: KnowledgeBase, condition) -> None:
    banner(f"{condition.name}  ({condition.id})")
    print(f"  category : {condition.category}")
    print(f"  urgency  : {condition.urgency}")
    print(f"  base rate: {condition.prior:.1%}")
    print(f"\n  {condition.description}")

    if condition.microgravity_note:
        print(f"\n  WHY MICROGRAVITY CHANGES THIS:\n  {condition.microgravity_note}")

    print("\n  Evidence weights:")
    for evidence in sorted(condition.findings, key=lambda e: -abs(e.weight)):
        label = knowledge_base.label_for(evidence.finding)
        print(f"    {evidence.weight:+5.1f}  {label:<42} (absent {evidence.absent_weight:+.1f})")
        if evidence.note:
            print(f"           -> {evidence.note}")

    sources(condition.sources)
    print()


# --- `vitals bench` --------------------------------------------------------


def bench_header(prompt_count: int, model: str) -> None:
    banner(f"VITALS BENCHMARK  -  {prompt_count} prompts  |  model: {model}")
    print("  Each one is a fresh model call. This takes a while.\n")


def bench_outcome(position: int, total: int, outcome) -> bool:
    """Print one prompt's result. Returns True if the run should stop."""
    print(f"  {position:>2}/{total}  {outcome.id:<22} ", end="", flush=True)

    if outcome.error:
        print("ERROR")
        print(f"        {outcome.error.splitlines()[0]}")
        return "could not reach" in outcome.error

    print(f"{'PASS' if outcome.hit else 'FAIL'}  got {outcome.got:<26} {outcome.elapsed:>5.1f}s")
    if not outcome.hit:
        print(f"        expected {outcome.expect}")
    if outcome.missed_escalation:
        print("        *** MISSED ESCALATION ***")
    return False


def bench_report(report) -> None:
    """The two headline numbers, then everything that went wrong."""
    banner("RESULTS")

    named, refused = report.naming, report.refusing
    print(f"\n  hit rate      {report.hit_rate:6.0%}   "
          f"({sum(o.hit for o in named)}/{len(named)} named correctly)")
    print(f"  refusal rate  {report.refusal_rate:6.0%}   "
          f"({sum(o.hit for o in refused)}/{len(refused)} correctly returned nothing)")

    print("\n  These two are NOT interchangeable. A system that always names")
    print("  something scores well on hits and 0% on refusals - and would tell")
    print("  a crewmember with a cracked filling they have a kidney stone.")

    if report.missed_escalations:
        print(f"\n  *** {len(report.missed_escalations)} MISSED ESCALATION(S) "
              f"- this is the number that matters ***")
        for outcome in report.missed_escalations:
            print(f"      {outcome.id}: expected escalation, got none")

    if report.failures:
        print(f"\n  failures ({len(report.failures)}):")
        for outcome in report.failures:
            print(f"      {outcome.id:<22} expected {outcome.expect:<26} got {outcome.got}")
            if outcome.why:
                print(f"        testing: {outcome.why.splitlines()[0]}")

    print("\n  by category:")
    for category, outcomes in sorted(report.by_category().items()):
        print(f"      {category:<14} {sum(o.hit for o in outcomes)}/{len(outcomes)}")

    print(f"\n{RULE}\n")
