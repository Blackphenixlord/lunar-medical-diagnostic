# Where this stands and what to do next

Updated 26 Sep 2026. Everything marked **verified** below was actually run,
not assumed.

14 conditions, 72 findings. `pytest tests -q` collects **111 tests and all
pass** (104 test functions; the demo-case test runs once per file in `cases/`).

## Architecture (current)

**Ollama is the reasoner. The knowledge base grounds it.**

```
complaint -> extract.py (findings) -> retrieval.py (select KB conditions)
          -> sensors.py (measured vitals - none yet) -> reason.py (ollama answers)
          -> citations looked up from the KB, never written by the model
```

- `python -m vitals ask "..."` is the main path. `python -m vitals serve` is the
  same pipeline behind the browser UI (`src/vitals/ui/index.html`, owned by Cruz -
  see `UI_ACCEPTANCE_CRITERIA.md` in the project docs).
- The deterministic engine (`engine.py` + `scoring.py`) is a **cross-check**
  (`--crosscheck`), not the answer. Its weights were invented and the model
  never sees them - a test fails if a number leaks into the model's context.
- `sensors.py` defines the contract and implements nothing: no hardware is
  attached. It reports "no sensors connected" and never fabricates a vital sign.

## Running it

```bash
pip install -e .                          # once; after this no PYTHONPATH needed
python -m vitals validate                 # KB VALID, 14 conditions, 72 findings
pytest tests -q                           # 111 passed
python -m vitals ask "..." --crosscheck
```

### Docker - verified offline, 26 Sep

```bash
docker compose build       # once, WITH a network: bakes the model into an image
docker compose up          # any time after -> http://localhost:8000, NO internet needed
```

Tested with both containers on a Docker network with no internet route at all:
the app found the baked model, and `vitals ask` answered the renal colic demo
correctly with the default `llama3.2`, cross-check agreeing. About 2.5 minutes
per answer on a laptop CPU - the Jetson GPU should be much faster, but that is
not measured yet.

One variable picks the model for both containers:
`VITALS_OLLAMA_MODEL=llama3.2:1b docker compose build`.

**Warning about `llama3.2:1b`.** On the same renal colic complaint the 1B model
ranked routine back pain first and invented a symptom ("worsens with head
movement") the crewmember never said. The code still escalated - it caught the
urgent condition in the list - but the reasoning shown was wrong. Do not demo
on 1B without running `python -m vitals bench` on it first.

Changed the model and it seems missing? The named volume only seeds from the
image the first time: `docker compose down -v`, then `up` again.

Jetson: build ON the Jetson (arm64). The GPU overlay now merges correctly
(`docker compose -f docker-compose.yml -f docker-compose.jetson.yml config`
shows two services, not three), but GPU passthrough on the actual board is
**not verified** - nobody has run it on the Jetson yet.

## Immediate

1. **Joaquin** reviews every weight and red flag in `kb/conditions/`. No Python
   needed - checklist at the end of `KNOWLEDGE_BASE_FORMAT.md`.
2. **Cruz** runs `python -m vitals ask "..."` with the way real people actually
   describe symptoms. Every missed phrasing goes to Joshua for `patterns.py`.
   That is genuine user-testing data for PDR, not busywork.
3. Run `python -m vitals bench` against the model you will actually demo on,
   and keep the dated result.

## Still blocked on a human

- **A real medical source** (nurse / EMT / doctor) to sanity-check the rules.
  The biggest credibility risk at review. Rules written from literature by
  three students are a starting point, not a validated knowledge base - say so
  at PDR before a judge does.
- **The requirements doc from Hayes** - the interface and output format may
  have to change. Do not gold-plate the CLI or UI until it arrives.
- Team number, Space Act Agreement, parts order.

## Design decisions to have memorized before PDR

1. *Why not train a machine-learning model?* No training data. NASA's own
   papers say in-flight medical event data is severely limited, and several of
   our conditions have zero recorded in-flight cases. A model trained on that
   would fit noise and could not explain itself. So we use a pretrained local
   language model to reason, and ground it in a cited knowledge base.

2. *What happens when the AI hallucinates?* The code limits what the model can
   do, and checks what it says:
   - it can only name conditions that retrieval handed it - an invented
     condition is dropped and reported;
   - it never writes a citation - it returns an id, and we look up the source
     in the knowledge base;
   - temperature 0, so the same complaint gives the same answer and tests exist;
   - if it names an urgent or emergency condition and forgets to escalate, the
     code escalates anyway;
   - `--crosscheck` runs a fully deterministic engine on the same findings and
     shows where the two disagree.
   Be honest that it can still write wrong *reasoning* - the 1B test above is
   the example. That is why a human decides and the tool escalates.

3. *Why no percentages on screen?* The prior and weight numbers were invented
   by us, not taken from a source. Showing "99%" would claim a precision we do
   not have. The model reports high / moderate / low confidence instead, and
   the UI criteria forbid percentages.

4. *Why not float urgent conditions to the top of the list?* We tried. It put a
   9% renal stone above a 99% head cold because both rules mention fever. A
   ranking you cannot trust is worse than none. Safety is a separate channel:
   escalation prints above the list.

## Known gaps

- No radiation, behavioral health, or trauma-beyond-laceration rules.
  Behavioral health is excluded on purpose - be ready to defend that as a
  choice, not an omission.
- The keyword extractor is regex. It will miss phrasings. That is the offline
  floor, not the ceiling.
- No sensor hardware wired in yet - see the hardware notes in the project docs.
