# VITALS

**Team TETHER · NASA HUNCH 2026–27 · Software & Technology**
*Medical Diagnostic System with Machine Learning & Artificial Intelligence*

| Who | Role |
|---|---|
| Joshua | Team lead, diagnostic engine |
| Joaquin | Medical research, diagnostic rules |
| Cruz | Interface, user testing |

---

## What it does

A crewmember describes how they feel. VITALS returns a **ranked differential** —
what it might be, how likely, **why**, what to do next, and the source for
every rule.

```
$ python -m vitals describe "Flight day 63. Bad pain in my right side, 8 out of 10,
                          comes in waves and shoots toward my groin. Blood in my urine."

  *** ESCALATE TO FLIGHT SURGEON ***
      - Renal Stone with Renal Colic: urgent condition at 99%

  1. [URGENT]    Renal Stone with Renal Colic     99%
      why:
        + Flank pain = 8.0              (+2.40)
        + Pain comes in waves = yes     (+2.00)
        + Blood in urine = yes          (+2.00)
        + Pain radiating to groin = yes (+1.80)
```

It is **decision support, not a diagnosis.** Every screen says so, and the
engine escalates to the flight surgeon rather than pretending to be one.

---

## Quick start

```bash
pip install -r requirements.txt

# one-time: get a local model
ollama pull llama3.2
# ...or skip this entirely and use Docker, which ships the model in the image

# THE MAIN PATH - ollama answers, grounded in the knowledge base
python -m vitals ask "flight day 63, bad pain in my right side, comes in waves, blood in my urine"
python -m vitals ask "..." --verbose      # show what was retrieved and why
python -m vitals ask "..." --crosscheck   # also run the engine and compare

# THE UI - opens in your browser
python -m vitals serve

# score it against the whole prompt bank
python -m vitals bench
python -m vitals bench --category mimic

# supporting commands
python -m vitals validate                 # check the knowledge base
python -m vitals explain sans             # show a condition and its sources
pytest tests -q                        # 111 tests
```

If `python -m vitals` cannot find the package, set `PYTHONPATH=src` first
(Windows PowerShell: `$env:PYTHONPATH="src"`).

---

## How it works

**Ollama answers. The knowledge base keeps it honest.**

```
  crewmember describes how they feel
            |
            v
   [ extract.py ]    pull findings out of the sentence     (fast, structural)
            |
            v
   [ retrieval.py ]  select the relevant KB conditions     (GROUNDING)
            |
            v
   [ sensors.py ]    attach any measured vitals            (none yet - see below)
            |
            v
   [ reason.py ]     >>> OLLAMA reads the research and answers <<<
            |
            v
   answer + real citations + optional cross-check
```

A raw LLM asked *"what's wrong with this astronaut?"* answers from generic Earth
medicine, because that is what the internet is made of. Handing it the actual
spaceflight literature first is what makes the answer about **space**. That is
the entire job of `retrieval.py`.

### Three constraints, enforced in code — not asked for politely in the prompt

**1. It can only name conditions we gave it.** The response is validated against
the retrieved ids. Invent `space_flu` and that entry is dropped, and the CLI
tells you it was dropped.

**2. It never writes a citation.** It returns a condition id; *we* look the
sources up from the KB. A model cannot hallucinate a URL it was never asked to
produce.

**3. Temperature 0.** Same complaint, same answer. Anything else is untestable,
and untestable means unprovable at a design review.

Plus a backstop: if the model names an urgent or emergency condition and forgets
to escalate, **we escalate anyway**. A model that forgets is not a reason a
crewmember goes without help.

### About the numbers in `kb/conditions/`

The `prior` and `weight` values were **invented**. The citations support that the
conditions exist and how they behave in microgravity; they do not support those
specific numbers. So the model never sees them — `as_context()` sends the
research prose and nothing we made up. There is a test that fails the build if
a number leaks into the model's context.

The deterministic engine still exists and still uses those weights, but it is a
**cross-check** now (`--crosscheck`), not the answer. When it disagrees with the
model, the CLI says so and tells you why they might differ.

### Sensors and cameras

`sensors.py` defines the slot. **Nothing is implemented, because nothing is
plugged in.** It reports `no sensors connected` and returns no readings — it
does not return a plausible-looking 37.0 °C. A fake vital is worse than a
missing one: a missing one makes the model ask, a fake one makes it conclude.

The prompt says so explicitly, so the model cannot quietly assume normal vitals.
When hardware arrives, write a class with `available()` and `read()`, register
it, and nothing else changes. Planned mapping is documented at the top of the file.

## Docker — the easy way to run it

```bash
docker compose build     # once, on a network. Downloads and BAKES IN the model.
docker compose up        # -> http://localhost:8000
```

That is the whole system — engine, knowledge base, web UI **and the language
model** — on any machine with Docker. No Python install, no ollama install, no
PATH problems.

### The model is inside the image

The stock `ollama/ollama` image ships with **no models**. It downloads one the
first time you ask a question, which means the first demo of the day is three
gigabytes of waiting — and on a locked-down network, or in a review room with
no wifi, that is not a wait, it is a failure.

So `docker/ollama.Dockerfile` starts a temporary ollama server *during the
build*, pulls the model, and shuts it down again. The model becomes a layer in
the image. After `docker compose build`, **`docker compose up` needs no
internet at all.**

The image is 2–3 GB bigger. That is the correct trade for a demo that has to
work in a building you have never been in.

### Two containers on purpose

| | what | why separate |
|---|---|---|
| `ollama` | the language model | gigabytes, changes almost never |
| `vitals` | engine, KB, UI | small, changes constantly |

Editing a diagnostic rule rebuilds a ~200 MB image in seconds instead of
re-baking a 3 GB model. And `kb/`, `prompts/` and `cases/` are **live-mounted
read-only** — Joaquin can edit a rule and just refresh the browser. No rebuild,
no Python, no Docker knowledge required of him.

### On the Jetson

```bash
# ON THE JETSON ITSELF — a Jetson is arm64, an image built on your laptop will not run
docker compose -f docker-compose.yml -f docker-compose.jetson.yml build
docker compose -f docker-compose.yml -f docker-compose.jetson.yml up
```

The overlay hands the GPU to ollama and sets `OLLAMA_KEEP_ALIVE=24h` so the
model stays resident — reloading it is the slow part, and a demo where the
second question takes 40 seconds looks broken. It needs the NVIDIA Container
Toolkit on the host, which is part of the *"Flash Ubuntu on the Jetson"* board
item, not something Docker installs.

`llama3.2` is the 3B model and fits comfortably in Orin Nano memory. Tight on
memory? `docker compose build --build-arg MODEL=llama3.2:1b`. Orin NX or
better? `llama3.1:8b` reasons noticeably better on the harder complaints. Set
it in **both** places in `docker-compose.jetson.yml` so the app asks for the
model that was actually baked in.

Anywhere else, pick a model with
`VITALS_OLLAMA_MODEL=phi3:mini docker compose build`.

The build runs `python -m vitals validate` and **fails if the knowledge base is
broken** — a container that starts with an invalid KB is worse than one that
refuses to build.

## The interface

```bash
python -m vitals serve            # http://127.0.0.1:8000, opens automatically
python -m vitals serve --port 9000 --no-open
```

Stdlib `http.server` only - no Flask, no npm, no build step. That is a
requirement, not laziness: it has to run on a Jetson and two Raspberry Pis that
may have no working internet, and every dependency is one more thing that can
fail on the vehicle. The whole UI is one self-contained HTML file with inlined
CSS and JS, and a test fails the build if a CDN link ever creeps in.

**The server owns no medical logic.** It is a thin shell around exactly the same
pipeline `vitals ask` uses, so the UI can never drift from the CLI. If they ever
disagree, that is a bug in `server.py`.

What it shows:

- the escalation banner first, before anything else
- the full differential, including what was considered and **ruled down**
- supporting vs contradicting evidence per condition
- next questions as clickable chips that append to the complaint
- a "what the system saw" panel: extracted findings, what was retrieved and why,
  and the deterministic engine's independent cross-check
- a standing warning that no vital sign has been measured

Two bits of framing are load-bearing and have their own tests: **"decision
support - not a diagnosis"** in the header, and **"no instruments attached"**
above the input. Restyle freely; do not delete those.

> Note for Cruz: this is a working shell to react to, not the final design.
> The board item says paper sketches first, and that is still the right order -
> it is much easier to argue with something that exists.

## Proving it works

```bash
python -m vitals bench                  # all 33 prompts
python -m vitals bench --category mimic # just the look-alikes
python -m vitals bench --id renal_classic
```

`prompts/complaints.yaml` holds 33 crewmember complaints written the way people
actually talk - terse, rambling, hedged, full of denials, with typos. Every
condition in the knowledge base has at least one, and a test fails the build if
a condition has none (untested end to end = untested).

**Two numbers, and they are not interchangeable:**

| | what it means |
|---|---|
| **hit rate** | of the prompts that should name a condition, how many got the right one |
| **refusal rate** | of the prompts where the right answer is *"nothing here fits"*, how many correctly returned nothing |

A system that scores 100% hits and 0% refusals is **worse than useless** - it
means it always names something, so a cracked filling comes back as a kidney
stone. Five prompts in the bank exist purely to catch that: dental, behavioural
health, trauma, and outright nonsense. Never quote one number without the other.

Tracked separately again: **missed escalations.** Naming the wrong condition is
bad; failing to escalate is the one that hurts someone. `vitals bench` exits
non-zero if any escalation was missed, even at a 100% hit rate.

The prompt bank feeds the UI too - the example chips are pulled from it, so what
you click is exactly what gets scored.

> These prompts are test INPUTS, not evidence. Nothing in the bank is presented
> as a fact about a real person and none of it justifies a rule. The rules are
> justified by the sources in `kb/conditions/*.yaml`.

## Layout

```
kb/
  findings.yaml              controlled vocabulary — 53 observable findings
  conditions/*.yaml          one file per condition — 11 rules
  schema/condition.schema.json   JSON Schema that validates every rule
src/vitals/
  models.py           the nouns — Condition, FindingDef, Evidence, Contribution
  knowledge_base.py   load + validate + cross-check kb/
  patterns.py         the phrasebook: English -> finding ids  (Cruz edits this)
  extract.py          complaint text -> observed findings
  retrieval.py        observed findings -> the KB pages worth reading
  ollama_client.py    HTTP plumbing for the local model, and its error messages
  reason.py           the model reads those pages and answers   <- THE LLM
  scoring.py          the evidence arithmetic
  engine.py           the deterministic cross-check: rank, escalate, ask next
  sensors.py          where hardware readings will plug in (nothing yet)
  render.py           everything that prints to a terminal
  cli.py              argument parsing and nothing else
  server.py           stdlib web server — a shell around the same pipeline
  bench.py            runs the prompt bank, scores hits vs refusals
  ui/index.html       the whole interface, one self-contained file
Dockerfile / docker-compose.yml    one-command run
docker/ollama.Dockerfile           bakes the language model into its image
prompts/complaints.yaml   33 test complaints, one per condition plus mimics
cases/         saved demo cases with expected answers — these are regression tests
tests/         111 tests
docs/          knowledge base format, research notes
```

---

## Where to add work

- **Joaquin:** new conditions go in `kb/conditions/`. Copy an existing file, keep
  the citations. See `docs/KNOWLEDGE_BASE_FORMAT.md`. You do not need to touch Python.
- **Cruz:** every phrasing that `describe` fails to understand is a test case.
  Add the phrasing to `src/vitals/patterns.py` and a test to `tests/test_extract.py`.
  That is real data, not busywork — and `patterns.py` is pure data, no Python to learn.
- **Joshua:** engine, CLI, and keeping `pytest` green.

## Status

14 conditions · 72 findings · 111 tests passing · 8 demo cases passing.
Ollama is the reasoner; the KB grounds it; sensors are stubbed, not faked.
Model baked into the Docker image, so a demo never waits on a download.
