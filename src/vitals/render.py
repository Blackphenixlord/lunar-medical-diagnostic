"""Everything that prints to a terminal.

Kept in one file so that cli.py can be about arguments and this can be about
words. It also means the wording a crewmember reads is reviewable in one place
- which matters, because half of these lines are safety messages.

TWO RULES FOR EVERY SCREEN IN HERE
    1. Say it is decision support, not a diagnosis. Every time. No exceptions.
    2. Never print a number without saying where it came from.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap
from typing import Iterable

from .engine import ConditionScore, Result, next_best_questions
from .knowledge_base import KnowledgeBase
from .models import URGENCY_TAG
from .reason import Answer

RULE = "=" * 66


# --- readability: width, wrapping, colour ----------------------------------
# The answer used to be one wall of text that ran off the side of the window.
# Everything below exists so a tired crewmember can read it at a glance.

MAX_WIDTH = 100     # past this, lines get hard to follow even on a wide screen


def _enable_windows_colour() -> bool:
    """Old Windows consoles print ANSI codes as garbage unless VT mode is on."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)          # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def _colour_wanted() -> bool:
    if os.environ.get("NO_COLOR"):                   # https://no-color.org
        return False
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False                                 # piped or saved: plain text
    return _enable_windows_colour()


_COLOUR = _colour_wanted()

_CODES = {
    "bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33",
    "blue": "34", "magenta": "35", "cyan": "36", "white": "37",
}

URGENCY_STYLE = {
    "emergency": ("EMERGENCY", ("bold", "red")),
    "urgent":    ("URGENT",    ("bold", "yellow")),
    "monitor":   ("MONITOR",   ("cyan",)),
    "routine":   ("ROUTINE",   ("green",)),
}


def paint(text: str, *styles: str) -> str:
    if not _COLOUR or not styles:
        return text
    codes = ";".join(_CODES[name] for name in styles)
    return f"\033[{codes}m{text}\033[0m"


def _width() -> int:
    return max(50, min(shutil.get_terminal_size((MAX_WIDTH, 24)).columns - 1, MAX_WIDTH))


def say(text: str, indent: int = 5, first: str | None = None) -> None:
    """Print a paragraph wrapped to the window, with a hanging indent.

    `first` replaces the indent on the first line only - used for bullets.
    """
    pad = " " * indent
    lead = pad if first is None else first.rjust(indent)
    wrapped = textwrap.fill(
        " ".join(str(text).split()),
        width=_width(),
        initial_indent=lead,
        subsequent_indent=pad,
        break_long_words=False,
        break_on_hyphens=False,
    )
    print(wrapped)


def heading(title: str, note: str = "") -> None:
    extra = f"  {paint(note, 'dim')}" if note else ""
    print(f"\n  {paint(title, 'bold', 'cyan')}{extra}")


def _strip_finding_id(question: str) -> str:
    """reason.py tags each question with its finding id for the UI and tests.
    A person reading the terminal does not need `[back_pain]`."""
    return re.sub(r"\s*\[[a-z0-9_]+\]\s*$", "", question)


def _thin_rule() -> str:
    return paint("-" * _width(), "dim")

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


def model_answer(
    answer: Answer,
    elapsed_seconds: float,
    crosscheck_result: tuple[str | None, str | None] | None = None,
) -> None:
    """The main output of the whole system.

    Order is deliberate: the one-line verdict first, then detail. Someone
    glancing at the screen should get "what is it, how bad, do I call the
    ground" from the first four lines without reading anything else.

    `crosscheck_result` is (engine_top_name, model_top_name) when `--crosscheck`
    was asked for, so the agreement can sit in the summary instead of the end.
    """
    width = _width()
    print()
    print(paint("=" * width, "dim"))
    print(f"  {paint('VITALS', 'bold')}  -  {DISCLAIMER}")
    print(paint(f"  model {answer.model}  |  {elapsed_seconds:.0f}s  |  {answer.sensor_status}", "dim"))
    print(paint("=" * width, "dim"))

    if answer.sensor_status == "no sensors connected":
        say(paint("No instruments attached. Everything below comes from what the "
                  "crewmember said - no vital sign has been measured.", "dim"), indent=2)

    # --- the verdict ---------------------------------------------------------
    if answer.escalate:
        print()
        print("  " + paint(" ESCALATE TO FLIGHT SURGEON ", "bold", "red"))
        if answer.escalation_reason:
            say(answer.escalation_reason, indent=4)

    if not answer.differential:
        print(NOTHING_MATCHED)
        return

    top = answer.differential[0]
    label, colours = URGENCY_STYLE.get(top.urgency, (top.urgency.upper(), ()))
    print()
    print(f"  {paint('MOST LIKELY', 'bold')}   {paint(top.name, 'bold')}")
    status = f"{paint(label, *colours)}  |  {top.confidence} confidence"
    status += "  |  " + ("escalate" if answer.escalate else "no escalation")
    print(f"                {status}")
    if crosscheck_result is not None:
        engine_name, model_name = crosscheck_result
        if engine_name is None:
            check = paint("backup engine: too little to go on", "dim")
        elif engine_name == model_name:
            check = paint("backup engine agrees", "green")
        else:
            check = paint(f"backup engine DISAGREES - it says {engine_name}", "bold", "yellow")
        print(f"                {check}")

    if answer.dropped:
        say(paint(f"[dropped {len(answer.dropped)} condition(s) the model made up: "
                  f"{', '.join(answer.dropped)}]", "yellow"), indent=2)

    # --- the differential ----------------------------------------------------
    heading("WHAT IT COULD BE", "(most likely first)")
    for position, candidate in enumerate(answer.differential, 1):
        label, colours = URGENCY_STYLE.get(candidate.urgency, (candidate.urgency.upper(), ()))
        print()
        print(f"  {position}. {paint(candidate.name, 'bold')}   "
              f"{paint(label, *colours)}  |  {candidate.confidence} confidence")
        if candidate.reasoning:
            say(candidate.reasoning, indent=5)
        for phrase in candidate.supporting:
            say(phrase, indent=7, first="  + ")
        for phrase in candidate.against:
            say(phrase, indent=7, first="  - ")

    # --- what to do ----------------------------------------------------------
    if top.recommend:
        heading("WHAT TO DO", f"(for {top.name}, from the knowledge base)")
        for action in top.recommend:
            say(action, indent=7, first="  * ")

    if answer.next_questions:
        heading("ASK NEXT")
        for question in answer.next_questions:
            say(_strip_finding_id(question), indent=7, first="  ? ")

    if answer.uncertainty:
        heading("LEAST SURE ABOUT")
        say(answer.uncertainty, indent=5)

    if crosscheck_result is not None:
        engine_name, model_name = crosscheck_result
        if engine_name is not None and engine_name != model_name:
            heading("CROSS-CHECK")
            say(f"The model says {model_name}; the backup scoring engine says "
                f"{engine_name}. Worth a look: the engine only reads the findings "
                f"the extractor caught, the model reads the whole sentence.", indent=5)

    heading("SOURCES", "(from the knowledge base, not the model)")
    for entry in top.sources:
        say(entry["title"], indent=5)
        print(paint(f"     {entry['url']}", "dim"))

    print()
    print(paint("=" * width, "dim"))
    print()


def crosscheck(model_top_id: str | None, engine_top_id: str | None) -> None:
    """Old standalone cross-check line. `vitals ask` now shows the cross-check
    inside `model_answer`; kept for anything else that still calls it."""
    heading("CROSS-CHECK")
    if engine_top_id is None:
        say("backup engine had too little to go on (it only sees extracted findings)")
    elif engine_top_id == model_top_id:
        say(f"backup engine agrees: {engine_top_id}")
    else:
        say(f"DISAGREES: engine says {engine_top_id}, model says {model_top_id}. "
            "They see different things - the engine only reads findings the "
            "extractor caught, the model reads the whole sentence.")


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
