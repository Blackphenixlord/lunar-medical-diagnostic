# Lunar Medical Diagnostic System

NASA HUNCH 2026–27 · Software and Technology Hardware Engineering plus Robotics
**SFT 2025-26-27 — Medical Diagnostic System with Machine Learning & Artificial Intelligence**
*(From a non-Medical Person's Perspective)* · Requested by NASA Human Research Program

---

## What this is

Astronauts on Moon and Mars missions face communication delays of 4 to 40 minutes plus total blackout periods. Real-time medical support from Earth is impossible. Crews have limited medical training and no on-site physician.

This system is the first line of medical diagnosis and guidance when Earth cannot answer.

**The user is not a doctor.** That is the central design constraint.

## Team

| Name | Role |
|---|---|
| Joshua Collado | Project Lead & Main Coder |
| Joaquin | Medical Research & Co-Coder |
| Cruz | UI Design & User Testing |

## Scope

Rule-based narrow AI. **Not** generative AI, **not** LLMs, **not** image analysis.

NASA's requirements allow diagnostic modules that are rule-based or machine-learned. We chose rule-based because it is auditable, runs offline, and is deliverable by three students in one school year.

## Architecture

```
CREW TERMINAL  (Raspberry Pi 5 + screen)
   Symptom entry, results display, plain language
        |
        |  local network — NO INTERNET
        v
DIAGNOSTIC SERVER  (Jetson + screen)
   Rule engine, confidence, escalation, session logs
        |
        v
KNOWLEDGE BASE  (YAML on SSD)
   Rules, procedures, SOURCES, limitations
```

## Repo layout

```
engine/            rule engine — the core logic
knowledge_base/    medical rules in YAML (Joaquin owns this)
terminal/          crew-facing interface (Cruz owns this)
tests/             test cases with known correct answers
docs/              limitations, sources, install instructions
logs/              session logs (gitignored — never commit real logs)
```

## Running it

```bash
python3 -m engine.cli
```

Requires Python 3.10+ and PyYAML. No internet connection needed — by design.

```bash
pip install pyyaml
```

## Rules for this repo

1. **Every medical rule cites a source.** A rule with an empty `source` field fails the test suite. This is not optional — a judge will ask where our rules came from.
2. **Never commit real patient data.** Ever.
3. **The escalation path is a feature, not an edge case.** "I don't know — wait for Earth" is a correct answer.
4. **Everything must run offline.** If it needs the internet, it does not ship.
5. **Commit often, write real commit messages.** The commit history is evidence of work for the design reviews.

## Not a medical device

This is a student prototype and a workforce development exercise. It must never be used to make real medical decisions.
