"""The command line. Argument parsing and orchestration only.

Anything that prints lives in render.py; anything that decides lives in the
engine, reason or knowledge_base modules. A command function here should read
like a recipe - load, extract, retrieve, ask, print - and if one ever grows
past about thirty lines, the logic belongs somewhere else.

    python -m vitals ask "flight day 63, right side pain in waves, blood in urine"
    python -m vitals doctor          what is and is not working
    python -m vitals describe "..."  deterministic engine only, no model needed
    python -m vitals serve           the browser interface
    python -m vitals explain sans    one condition's rules and sources
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from . import render
from .engine import diagnose, next_best_questions
from .extract import get_extractor
from .knowledge_base import KnowledgeBaseError, load_knowledge_base

BACKEND_CHOICES = ["auto", "keyword", "ollama", "claude"]

# Findings the structured interview always opens with: the commonest complaints
# plus the two context questions that colour everything else.
INTERVIEW_SEED_FINDINGS = [
    "headache", "nausea", "flank_pain", "back_pain", "nasal_congestion",
    "shoulder_pain", "presyncope", "fever", "mission_elapsed_days",
]

INTERVIEW_FOLLOW_UP_LIMIT = 6


# --- the main path ---------------------------------------------------------


def cmd_ask(args) -> int:
    """Ollama answers; the knowledge base grounds it. This is the demo."""
    from . import sensors
    from .reason import OllamaUnavailable, ask
    from .retrieval import retrieve

    knowledge_base = load_knowledge_base(args.kb)

    observations = get_extractor("keyword").extract(args.text, knowledge_base)
    observations.update(sensors.as_observations(sensors.read_all()))

    retrieved = retrieve(knowledge_base, args.text, observations, limit=args.retrieve)

    if args.verbose:
        render.retrieval_trace(retrieved, observations, sensors.status())

    print(f"\n  asking {args.model} ...", end="", flush=True)
    print("\n  (first run loads the model into RAM - this can take a minute)",
          end="", flush=True)

    started = time.time()
    try:
        answer = ask(knowledge_base, args.text, retrieved,
                     observations=observations, model=args.model)
    except OllamaUnavailable as exc:
        render.error(str(exc))
        return 2
    finally:
        print(f"\r{' ' * 70}\r", end="")     # wipe the "asking ..." line

    render.model_answer(answer, time.time() - started)

    if args.crosscheck:
        engine_result = diagnose(knowledge_base, observations)
        render.crosscheck(
            model_top_id=answer.top.condition_id if answer.top else None,
            engine_top_id=engine_result.top.id if engine_result.top else None,
        )

    print(f"\n{render.RULE}\n")
    return 0


# --- setup and self-check --------------------------------------------------


def cmd_doctor(args) -> int:
    """One command that says exactly what is and is not working.

    Written for the moment someone else clones this an hour before a review and
    nothing runs. Every failure line must name the fix.
    """
    from . import sensors
    from .ollama_client import DEFAULT_MODEL, OLLAMA_HOST, OllamaUnavailable, list_models

    render.banner("VITALS SELF-CHECK")
    everything_ok = True

    import vitals
    print("\n  [1] code")
    print(f"      version {vitals.__version__}")

    print("\n  [2] knowledge base")
    try:
        knowledge_base = load_knowledge_base(args.kb)
    except KnowledgeBaseError as exc:
        print(f"      FAILED - {exc}")
        return 1
    print(f"      OK - {len(knowledge_base.conditions)} conditions, "
          f"{len(knowledge_base.findings)} findings")

    print("\n  [3] ollama  (the reasoner - this is the important one)")
    try:
        models = list_models(OLLAMA_HOST)
        everything_ok &= _report_models(models, DEFAULT_MODEL, OLLAMA_HOST)
    except OllamaUnavailable as exc:
        everything_ok = False
        _report_ollama_missing(exc)

    print("\n  [4] sensors")
    print(f"      {sensors.status()}")
    print("      (nothing is implemented yet - by design, no hardware attached)")

    print(f"\n{render.RULE}")
    if everything_ok:
        print('  READY. Try:  python -m vitals ask "flight day 2, nausea worse when I turn my head"')
    else:
        print("  NOT READY - fix the items marked above.")
        print('  The engine still works without ollama:  python -m vitals describe "..."')
    print(f"{render.RULE}\n")

    return 0 if everything_ok else 1


def _report_models(models: list[str], default_model: str, host: str) -> bool:
    if not models:
        print(f"      running at {host}, but NO MODELS are pulled")
        print(f"        fix:  python -m vitals pull {default_model}")
        print("        (this uses the HTTP API - you do NOT need `ollama` on your PATH)")
        return False

    print(f"      running at {host}")
    print(f"      models pulled: {', '.join(models)}")

    have_default = any(name.split(":")[0] == default_model.split(":")[0] for name in models)
    if have_default:
        print(f"      default model '{default_model}' is available")
        return True

    print(f"      default model '{default_model}' is NOT pulled")
    print(f"        fix:  ollama pull {default_model}")
    print(f'        or:   $env:VITALS_OLLAMA_MODEL="{models[0]}"')
    return False


def _report_ollama_missing(exc: Exception) -> None:
    print("      NOT AVAILABLE")
    for line in str(exc).splitlines():
        print(f"      {line}")
    print("\n      If you already installed it, the SERVER just is not running.")
    print("      Open the Ollama app from the Start menu - it sits in the system tray.")
    print("      You do NOT need the `ollama` command to work; this tool talks HTTP.")
    print("\n      Not installed at all:")
    print("        winget install -e --id Ollama.Ollama")


def cmd_pull(args) -> int:
    """Download a model WITHOUT needing the `ollama` command on your PATH."""
    from .ollama_client import DEFAULT_MODEL, OLLAMA_HOST, OllamaUnavailable, list_models, pull_model

    name = args.model or DEFAULT_MODEL
    print(f"\n  pulling '{name}'")
    print(f"  from {OLLAMA_HOST}")
    print("  (a few GB - leave it running)\n")

    try:
        pull_model(name, OLLAMA_HOST, progress=_ProgressBar())
    except OllamaUnavailable as exc:
        render.error(f"  {exc}")
        return 2

    print()
    try:
        print("\n  done. models available:")
        for model in list_models(OLLAMA_HOST):
            print(f"    {model}")
    except OllamaUnavailable:
        pass

    print('\n  now try:  python -m vitals ask "flight day 2, nausea worse when I turn my head"\n')
    return 0


class _ProgressBar:
    """Draws the download bar, and knows the two ways that went wrong.

    1. Ollama emits progress events many times a second. Redrawing on every one
       printed the same percentage fifty times, so we only redraw when the
       percentage or the status actually changed.

    2. A 40-character bar in a 45-column window WRAPS, and then \\r returns to
       the start of the wrapped line instead of the original one. That is how
       one progress bar became roughly 600 lines of garbage. So the bar is
       sized to the real terminal, and when stdout is not a tty we print plain
       lines every 10% instead of trying to redraw at all.
    """

    def __init__(self) -> None:
        self.columns = shutil.get_terminal_size((60, 20)).columns
        self.width = max(8, min(24, self.columns - 20))
        self.interactive = sys.stdout.isatty()
        self.last_percent = -1
        self.last_status = ""

    def __call__(self, event: dict) -> None:
        status = str(event.get("status", ""))[:18]
        total, completed = event.get("total"), event.get("completed")

        if total and completed:
            self._draw(int(100.0 * completed / total), status)
        elif status and status != self.last_status:
            self.last_status = status
            self._write_status(status)

    def _draw(self, percent: int, status: str) -> None:
        if percent == self.last_percent and status == self.last_status:
            return
        self.last_percent, self.last_status = percent, status

        filled = int(self.width * percent / 100)
        bar = "#" * filled + "." * (self.width - filled)
        line = f"  [{bar}] {percent:3d}%"

        if self.interactive:
            print(f"\r{line}", end="", flush=True)
        elif percent % 10 == 0:
            print(line, flush=True)

    def _write_status(self, status: str) -> None:
        if self.interactive:
            print(f"\r  {status:<{max(10, self.columns - 4)}}")
        else:
            print(f"  {status}", flush=True)


# --- the deterministic engine ----------------------------------------------


def cmd_describe(args) -> int:
    """Free-text intake straight into the engine. Works with no model at all."""
    knowledge_base = load_knowledge_base(args.kb)
    extractor = get_extractor(args.backend)
    observations = extractor.extract(args.text, knowledge_base)

    render.extracted_findings(extractor.name, observations)
    if not observations:
        return 0

    render.engine_result(knowledge_base, diagnose(knowledge_base, observations),
                         show_all=args.all)
    return 0


def cmd_case(args) -> int:
    """Run a saved case file. These double as regression tests."""
    knowledge_base = load_knowledge_base(args.kb)
    case = yaml.safe_load(Path(args.path).read_text(encoding="utf-8")) or {}

    observations: dict[str, Any] = case.get("observations") or {}
    if case.get("narrative") and not observations:
        observations = get_extractor(args.backend).extract(case["narrative"], knowledge_base)

    print(f"\nCASE: {case.get('title', args.path)}")
    if case.get("narrative"):
        print(f'  "{case["narrative"].strip()}"')

    result = diagnose(knowledge_base, observations)
    render.engine_result(knowledge_base, result, show_all=args.all)

    if case.get("expect_top"):
        _report_case_expectation(case["expect_top"], result)
    return 0


def _report_case_expectation(expected_id: str, result) -> None:
    actual = result.top.id if result.top else "nothing"
    verdict = "PASS" if actual == expected_id else f"FAIL (got {actual})"
    print(f"  expected top = {expected_id}  ->  {verdict}\n")


def cmd_interview(args) -> int:
    """Guided intake: fixed opening questions, then whatever discriminates most."""
    knowledge_base = load_knowledge_base(args.kb)
    observations: dict[str, Any] = {}

    print("\nVITALS structured interview. Enter = skip (unknown). Ctrl-C to stop.\n")

    try:
        for finding_id in INTERVIEW_SEED_FINDINGS:
            answer = input(f"  {knowledge_base.question_for(finding_id)} ").strip()
            if answer:
                observations[finding_id] = _coerce_answer(knowledge_base, finding_id, answer)

        for _ in range(INTERVIEW_FOLLOW_UP_LIMIT):
            questions = next_best_questions(knowledge_base, diagnose(knowledge_base, observations), 1)
            if not questions:
                break
            finding_id, question = questions[0]
            answer = input(f"  {question} ").strip()
            observations[finding_id] = (
                _coerce_answer(knowledge_base, finding_id, answer) if answer else None
            )
    except (KeyboardInterrupt, EOFError):
        print("\n  (stopped early - scoring what we have)")

    render.engine_result(knowledge_base, diagnose(knowledge_base, observations),
                         show_all=args.all)
    return 0


def _coerce_answer(knowledge_base, finding_id: str, answer: str):
    """Typed answers stay text; measured ones become numbers."""
    if knowledge_base.findings[finding_id].type == "bool":
        return answer
    return float(answer)


# --- knowledge base tools --------------------------------------------------


def cmd_validate(args) -> int:
    """Load the whole knowledge base and report anything wrong with it."""
    try:
        knowledge_base = load_knowledge_base(args.kb)
    except KnowledgeBaseError as exc:
        print(f"KB INVALID\n{exc}", file=sys.stderr)
        return 1

    print("KB VALID")
    print(knowledge_base.summary())

    used = {
        evidence.finding
        for condition in knowledge_base.conditions.values()
        for evidence in condition.findings
    }
    unused = set(knowledge_base.findings) - used
    if unused:
        print(f"\nnote: {len(unused)} findings defined but not used by any rule yet:")
        print("      " + ", ".join(sorted(unused)))
    return 0


def cmd_explain(args) -> int:
    """Print one condition's rules, weights and sources. Joaquin's review view."""
    knowledge_base = load_knowledge_base(args.kb)
    render.condition_detail(knowledge_base, knowledge_base.condition(args.condition_id))
    return 0


# --- benchmark and server --------------------------------------------------


def cmd_bench(args) -> int:
    """Run the prompt bank and score it. See bench.py for what the numbers mean."""
    from .bench import Report, run_one

    knowledge_base = load_knowledge_base(args.kb)
    prompts = _select_prompts(args)
    if not prompts:
        print("no prompts matched", file=sys.stderr)
        return 1

    render.bench_header(len(prompts), args.model)

    report = Report(model=args.model)
    for position, prompt in enumerate(prompts, 1):
        outcome = run_one(knowledge_base, prompt, model=args.model)
        report.outcomes.append(outcome)

        if render.bench_outcome(position, len(prompts), outcome):
            render.error("  Stopping - ollama is not running.")
            return 2

    render.bench_report(report)
    return 0 if not report.missed_escalations else 1


def _select_prompts(args) -> list[dict]:
    from .bench import load_prompts

    prompts = load_prompts(args.prompts)
    if args.category:
        prompts = [p for p in prompts if p.get("category") == args.category]
    if args.id:
        prompts = [p for p in prompts if p["id"] == args.id]
    if args.limit:
        prompts = prompts[: args.limit]
    return prompts


def cmd_serve(args) -> int:
    """Run the local web interface."""
    from .server import serve

    serve(host=args.host, port=args.port, kb_path=args.kb,
          model=args.model, open_browser=not args.no_open)
    return 0


# --- argument parsing ------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vitals",
        description="VITALS - spaceflight medical decision support (Team TETHER)",
    )
    parser.add_argument("--kb", default=None, help="path to the kb/ directory")
    subcommands = parser.add_subparsers(dest="command", required=True)

    ask = subcommands.add_parser(
        "ask", help="MAIN PATH: ollama answers, grounded in the knowledge base")
    ask.add_argument("text")
    ask.add_argument("--model", default=None,
                     help="ollama model (default: llama3.2 or $VITALS_OLLAMA_MODEL)")
    ask.add_argument("--retrieve", type=int, default=6,
                     help="how many conditions to ground with")
    ask.add_argument("--crosscheck", action="store_true",
                     help="also run the deterministic engine and compare")
    ask.add_argument("--verbose", action="store_true",
                     help="show what was retrieved and why")
    ask.set_defaults(func=cmd_ask)

    doctor = subcommands.add_parser("doctor", help="check what is and is not working")
    doctor.set_defaults(func=cmd_doctor)

    pull = subcommands.add_parser("pull", help="download a model (no `ollama` command needed)")
    pull.add_argument("model", nargs="?", default=None)
    pull.set_defaults(func=cmd_pull)

    describe = subcommands.add_parser("describe", help="free-text intake, deterministic engine")
    describe.add_argument("text")
    describe.add_argument("--backend", default="auto", choices=BACKEND_CHOICES)
    describe.add_argument("--all", action="store_true")
    describe.set_defaults(func=cmd_describe)

    case = subcommands.add_parser("case", help="run a saved case file")
    case.add_argument("path")
    case.add_argument("--backend", default="auto", choices=BACKEND_CHOICES)
    case.add_argument("--all", action="store_true")
    case.set_defaults(func=cmd_case)

    interview = subcommands.add_parser("interview", help="guided question-by-question intake")
    interview.add_argument("--all", action="store_true")
    interview.set_defaults(func=cmd_interview)

    explain = subcommands.add_parser("explain", help="print a condition's rules and sources")
    explain.add_argument("condition_id")
    explain.set_defaults(func=cmd_explain)

    validate = subcommands.add_parser("validate", help="load and check the knowledge base")
    validate.set_defaults(func=cmd_validate)

    bench = subcommands.add_parser("bench", help="run the prompt bank and score it")
    bench.add_argument("--prompts", default=None, help="path to a prompts yaml")
    bench.add_argument("--category", default=None,
                       choices=["classic", "mimic", "phrasing", "nothing_fits"])
    bench.add_argument("--id", default=None, help="run a single prompt by id")
    bench.add_argument("--limit", type=int, default=None)
    bench.add_argument("--model", default=None)
    bench.set_defaults(func=cmd_bench)

    serve = subcommands.add_parser("serve", help="run the web interface")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--model", default=None)
    serve.add_argument("--no-open", action="store_true", help="do not open a browser")
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Commands that take --model share one default, resolved here so the
    # environment variable is read once and reported consistently.
    if hasattr(args, "model") and args.model is None:
        from .ollama_client import DEFAULT_MODEL
        args.model = DEFAULT_MODEL

    try:
        return args.func(args)
    except KnowledgeBaseError as exc:
        print(f"knowledge base error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
