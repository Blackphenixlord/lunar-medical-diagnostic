# Knowledge Base Format — decision and spec

*Monday board item: "Define the knowledge base file format (JSON or YAML)" — this is the answer.*

## Decision: **YAML for the data, JSON Schema for validation.**

### Why YAML for the rules

1. **Joaquin has to be able to edit rules without being a programmer.** He is doing
   the medical research. If editing a rule means counting braces and commas, he
   stops editing rules and the knowledge base stops growing.
2. **YAML has comments. JSON does not.** Every rule carries its citation and its
   reasoning inline, next to the number it justifies. In JSON that information
   has to live somewhere else, and information that lives somewhere else rots.
3. **Multi-line strings.** `microgravity_note` is a paragraph. In JSON it is one
   enormous line with `\n` escapes, which nobody proofreads.
4. **Diffs are readable.** When Joaquin changes one weight, the pull request shows
   one changed line, not a reformatted block.

### Why JSON Schema for validation

JSON Schema is the standard, has real tooling, and gives specific error messages
(`findings/3/weight: 9 is greater than the maximum of 5`) instead of a stack
trace. YAML parses to the same data model as JSON, so we validate the parsed
YAML against `kb/schema/condition.schema.json` and get both benefits.

### What we gave up

YAML has sharp edges: `no` used to parse as boolean false in older parsers, and
an unquoted string containing `: ` breaks the parse. We hit the second one
during the build. Guard rails: `python -m mdx validate` runs in CI, and
`tests/test_kb.py` fails the build on a malformed rule.

---

## Layout

```
kb/
  findings.yaml                    the controlled vocabulary
  conditions/<condition_id>.yaml   one file per condition
  schema/condition.schema.json     validates each condition file
```

**One file per condition, filename = `id`.** Loader enforces the match. Two
people can add two conditions with zero merge conflicts.

---

## `findings.yaml` — the controlled vocabulary

Every `finding:` a rule references must be defined here. This is the single
most important structural decision in the KB: it stops one person writing
`headache` and another writing `head_pain` and the engine silently treating
them as unrelated. The loader cross-checks and refuses to start if a rule
references a finding that does not exist.

```yaml
findings:
  flank_pain:
    type: scale                # bool | scale (0-10) | num | enum
    label: Flank pain          # shown in output
    ask: "Rate the pain in your side/back 0-10."   # used by the interview + UI
    scoring: { direction: high, threshold: 4, span: 3 }
```

### `scoring` — how a number becomes evidence

Non-boolean findings need to be turned into a support value in `-1 .. +1`:

```
support = clamp((value - threshold) / span, -1, +1)      # direction: high
support = -that                                          # direction: low
```

`direction: low` is why `sleep_hours: 3` **supports** sleep disruption while
`sleep_hours: 9` argues against it. `span` controls how fast support saturates —
`fever` uses `threshold 38.0, span 0.7`, so 38.7 °C is already full support.

### `contextual` — background facts that are not symptoms

```yaml
  mission_elapsed_days:
    type: num
    contextual: true
```

A contextual finding **modulates** a diagnosis but can never make one alone.
Mission day and "was there a decompression" are facts about the situation, not
about the person. Without this flag, "flight day 2" alone was floating
adaptation back pain onto the screen at 69% for a crewmember who never
mentioned their back. A condition needs at least one non-contextual observed
finding before it appears at all.

### `required` — the finding a diagnosis cannot exist without

```yaml
  - finding: open_wound
    weight: 3.0
    absent_weight: -3.0
    required: true
```

Use this only for physical preconditions, not for strong evidence. Three things
follow from it:

1. **Explicitly absent → the condition is ruled out entirely.** No wound, not a
   laceration. No decompression, not decompression sickness.
2. **Unknown → it becomes the engine's first question.** If a condition cannot
   be called without knowing X, X settles it faster than anything else.
3. **Unknown → the condition cannot raise an alarm.** You do not page the
   flight surgeon about a laceration when nobody has established there is a
   wound.

Only two rules use it today: `wound_laceration` (open_wound) and
`decompression_sickness` (recent_decompression). Both are physics, not judgement.

---

## Condition file

```yaml
id: renal_stone                  # must equal the filename
name: Renal Stone with Renal Colic
aka: [nephrolithiasis, kidney stone]
category: renal
urgency: urgent                  # routine | monitor | urgent | emergency
prior: 0.04                      # base rate before any finding

description: >
  One or two sentences a crewmember could read.

microgravity_note: >
  REQUIRED. Why this presents differently in space. A review panel will ask
  this about every single rule, and a test fails the build if it is missing.

findings:
  - finding: flank_pain          # must exist in findings.yaml
    weight: 2.4                  # log-odds added when PRESENT
    absent_weight: -2.0          # added when EXPLICITLY absent (default 0)
    required: false              # true = explicit absence rules the condition out
    note: Why this weight is what it is.

red_flags: [fever, urine_output_low]   # presence triggers escalation
recommend:                             # actions, not prescriptions
  - Urinalysis for blood.
differential: [space_motion_sickness]  # look-alikes that must be ruled out

sources:                               # REQUIRED. No source, no rule.
  - title: "..."
    url: "https://..."
```

### Choosing a weight

Weights are log-odds. Rough calibration we have been using:

| weight | means | example |
|---|---|---|
| ±2.5 | close to diagnostic on its own | non-compressible IJV on ultrasound |
| ±2.0 | strong | blood in urine for renal stone |
| ±1.5 | solid supporting evidence | vomiting in space motion sickness |
| ±1.0 | contributes | reduced urine output |
| ±0.5 | weak, non-specific | nausea in renal colic (everything causes nausea) |

### `urgency` is about the CONDITION, `red_flags` are about the INSTANCE

This trips people up. `urgency: urgent` means *every* instance of this condition
alarms — so a sensitive tooth would page the flight surgeon. That is wrong, and
we shipped it wrong once.

Set `urgency` by what the condition is at its worst *typical* presentation, and
put the dangerous branch in `red_flags`. Dental and laceration are both
`monitor`, because most instances are neither dangerous nor urgent; their
`red_flags` (facial swelling, fever, uncontrolled bleeding, a wound that will
not stay closed) are what actually raise the alarm.

Two guards exist in the engine so a red flag cannot cry wolf:

- A condition still **awaiting a required finding** cannot alarm.
- A **non-leading** candidate needs at least two findings pointing at it. A
  single finding that happens to be a red flag in five rules must not fire five
  alarms. `fever` appears in four rules — that bug was real.

Two rules of thumb that keep the KB honest:

- **If a finding is common in space, its weight must be small.** Facial fullness
  gets `0.8` in the clot rule, not `2.0`, because *every* crewmember has a puffy
  face from the fluid shift. A weight that ignores the base rate produces false
  alarms.
- **Negative weights matter as much as positive ones.** `congestion_since_arrival`
  scores `+2.3` for fluid-shift congestion and `-2.0` for infection. That single
  pair is what stops the tool burning the mission's antibiotics on physics.

### `absent_weight` defaults to 0 on purpose

"Not mentioned" and "explicitly denied" are different, and both are different
from "present". Absence only counts when *ruling it out actually tells you
something*. Set it when denial is informative; leave it at 0 otherwise.

---

## Adding a condition (Joaquin's checklist)

1. Copy the closest existing file in `kb/conditions/` to `<new_id>.yaml`.
2. Change `id` to match the filename.
3. Write `microgravity_note` **first** — if you cannot explain why space changes
   this condition, it probably does not belong in this knowledge base.
4. Add findings. Any new one goes into `findings.yaml` first.
5. Add at least one real source with a URL.
6. Run `python -m mdx validate`, then `pytest tests -q`.
7. Add a case in `cases/` with `expect_top:` set. It becomes a regression test
   automatically — `tests/test_engine.py` picks up every file in that folder.

## What the validator catches

- schema violations (unknown category, weight out of range, missing `sources`)
- `id` not matching the filename, duplicate ids
- a rule referencing a finding that does not exist  ← the typo we will actually make
- a `red_flag` or `differential` pointing at something undefined
- the same finding listed twice in one condition
