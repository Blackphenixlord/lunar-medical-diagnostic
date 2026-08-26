# Where this stands and what to do next

Built 21 Aug 2026. Rearchitected the same day: **ollama is the reasoner, the KB grounds it.**
14 conditions, 72 findings, 111 tests passing.

## Architecture (current)
`python -m mdx serve` opens the web UI. `python -m mdx ask "..."` is the same pipeline on the CLI. Pipeline: extract findings -> retrieve
relevant KB conditions -> attach sensor readings (none yet) -> ollama answers ->
citations looked up from the KB, never written by the model.

The deterministic engine is now a **cross-check** (`--crosscheck`), not the answer.
Its weights were invented and the model never sees them.

Sensors: `src/mdx/sensors.py` defines the contract and implements nothing, because
no hardware is attached. It reports "no sensors connected" and returns no readings.
It does NOT fabricate a plausible vital sign.

## Board items this closes

| Monday item | Due | Status |
|---|---|---|
| Define the knowledge base file format (JSON or YAML) | Sep 18 | **Done** — `docs/KNOWLEDGE_BASE_FORMAT.md`. YAML for rules, JSON Schema for validation. |
| Write the first 10 diagnostic rules together | Sep 25 | **Done, needs review** — 11 rules in `kb/conditions/`, all cited. Joaquin still has to check the medicine. |
| Research medical conditions specific to spaceflight | Sep 18 | **First pass done** — `docs/RESEARCH_spaceflight_conditions.md`, with a gaps list. |
| Set up GitHub repo + agree on file structure | Aug 28 | Structure exists here. Still needs `git init` and a remote. |

## FIRST THING: git

Git was first initialised over the Claude device bridge, which cannot delete
files. Git needs to delete its own lock files, so it left a stuck
`.git\index.lock` and git will refuse to run until it is cleared.

Fix, from the repo root on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\init_git.ps1
```

That wipes the half-made `.git`, makes a clean one locally, and commits
everything with a full first-commit message. It does not touch source files.
Then make an EMPTY repo at github.com/new and push. Add Cruz and Joaquin.

## Immediate

1. `git init`, first commit, push. Nothing here is backed up yet.
2. Joaquin reviews every weight in `kb/conditions/`. He does not need to touch
   Python — see the checklist at the end of `KNOWLEDGE_BASE_FORMAT.md`.
3. Cruz runs `python -m mdx describe "..."` with the way *real people* actually
   describe symptoms. Every phrase it misses is a test case. That is genuine
   user-testing data for the portfolio, not busywork.

## Still blocked on a human

- **A real medical source** (nurse / EMT / doctor) to sanity-check the weights.
  Open CRITICAL item on the board, and the biggest credibility risk at review.
  Rules written from literature by three students are a starting point, not a
  validated knowledge base — say that out loud at PDR before a judge says it for you.
- **The requirements doc from Hayes** — the interface and output format may have
  to change to match what HUNCH actually asks for. Do not gold-plate the CLI
  until that arrives.

## Design decisions to have memorized before PDR

Judges ask these. Answers are in the README, but know them cold:

1. *Why not machine learning?* No training data — NASA's own papers say
   in-flight medical event data is severely limited, and several of our
   conditions have zero recorded in-flight incidence. A learned model would fit
   noise and could not explain itself.
2. *What happens when the AI hallucinates?* The LLM only extracts findings; it
   never diagnoses. Worst case is a missed finding, not an invented diagnosis.
   The engine is deterministic and runs offline.
3. *Why does it say 99% instead of just naming the disease?* Because it is
   decision support. It shows the arithmetic and escalates to the flight surgeon.
   A tool that says "you have a kidney stone" is claiming an authority it has not got.
4. *Why is a 0.5% condition allowed to be at the top of the list?* It is not,
   automatically — ranking is by probability only. We tried floating urgent
   conditions and it put a 9% renal stone above a 99% head cold. Safety is a
   separate channel: escalation prints above the list.

## Known gaps

- No decompression sickness, radiation, dental, or trauma rules yet.
- Behavioral health deliberately excluded from v1 — a scoring engine is the
  wrong tool and a wrong answer there does real harm. Be ready to defend that
  as a choice, not an omission.
- The keyword extractor is regex. It will miss phrasings. That is fine and
  expected — it is the offline floor, not the ceiling.
- No UI yet. Cruz's paper sketches (board item, due Sep 11) come before any code.
