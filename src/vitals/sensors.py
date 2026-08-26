"""Where sensor and camera data will enter the pipeline.

NOTHING IS IMPLEMENTED HERE YET, AND THAT IS DELIBERATE.

There is no thermometer, no pulse oximeter and no camera plugged into this
laptop, so there is no reading to report. This module therefore reports exactly
that: *not connected*. It does not return a plausible-looking 37.0 C. A fake
vital sign is worse than a missing one - a missing one makes the model ask,
while a fake one makes it conclude.

What this file IS for right now:
  - it defines the CONTRACT, so the prompt, the CLI and the engine already have
    a place to put readings the day hardware arrives;
  - it makes "no sensors connected" an explicit, visible fact in the output and
    in the model's prompt, instead of a silent gap.

To add real hardware later, write a class with a `read()` method returning
`Reading` objects and register it. The rest of the system needs no changes.

Candidates, currently out to a team vote on the Monday board. Cost is the
~$250-300 parts budget. A sensor is only worth buying if it feeds a finding a
rule ACTUALLY READS - hardware producing data nothing consumes is wasted money.

  Dipstick + camera  ~$15  -> hematuria, dysuria
      Strongest case. Renal stone is the most mission-threatening condition we
      model and blood in the urine is its best discriminator. Turns a symptom
      the crewmember has to notice into a measured finding.

  MLX90614 IR temp   ~$15  -> fever
      Referenced by 8 of 11 rules. Flips congestion from fluid-shift to
      infection, and renal colic from urgent to emergency. Non-contact.

  MAX30102 pulse ox  ~$12  -> hr_elevated (+ SpO2, needs a new finding)
      Orthostatic intolerance and the clot rule. Finger readings are noisy.

  Pi Camera 3        ~$35  -> reads the dipstick; maybe pallor / cold_sweat
      NOT fundoscopy. Photographing an optic disc needs real ophthalmic optics,
      and that is exactly what SANS requires. Do not claim otherwise.

  SCD40/41 CO2       ~$30  -> NEW finding: cabin CO2
      Would make tension_headache_co2 objective. Right now that rule is
      diagnosed by asking whether ANYONE ELSE has a headache. The most original
      thing on the list.

  BP cuff, serial    ~$40  -> NEW finding: supine vs seated BP delta
      That delta is the orthostatic intolerance diagnosis. Only one rule uses
      it. First thing to cut.

RULED OUT:
  Ultrasound probe - two rules want it (jugular_distension, hydronephrosis) and
      the ISS has one, but a handheld probe is $2,000+. Out of budget. State
      this as a known limitation rather than pretending we have it.
  Body weight scale - meaningless in microgravity.
  Consumer wearables - closed data, no reliable raw readings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class Reading:
    """One measurement from real hardware.

    `finding` must be an id in kb/findings.yaml so a reading drops straight into
    the same observation dictionary a human answer would.
    """
    finding: str
    value: Any
    unit: str = ""
    source: str = ""        # which device produced it
    confidence: float = 1.0  # instruments are not infallible either


@runtime_checkable
class Sensor(Protocol):
    name: str

    def available(self) -> bool:
        """True only when the hardware is physically present and responding."""

    def read(self) -> list[Reading]:
        """Return real measurements. Return [] if unavailable. NEVER estimate."""


# Nothing is registered because nothing is plugged in.
REGISTERED: list[Sensor] = []


def read_all() -> list[Reading]:
    """Collect readings from every connected sensor. Currently always empty."""
    readings: list[Reading] = []
    for s in REGISTERED:
        try:
            if s.available():
                readings.extend(s.read())
        except Exception:
            # A broken sensor must never take the diagnostic tool down with it.
            continue
    return readings


def status() -> str:
    """One honest line about what hardware is attached."""
    if not REGISTERED:
        return "no sensors connected"
    live = [s.name for s in REGISTERED if s.available()]
    if not live:
        return f"{len(REGISTERED)} sensor(s) registered, none responding"
    return f"connected: {', '.join(live)}"


def as_observations(readings: list[Reading]) -> dict[str, Any]:
    """Turn readings into the observation dict the engine already understands."""
    return {r.finding: r.value for r in readings}


def as_context(readings: list[Reading]) -> str:
    """The SENSOR block in the model's prompt.

    When there is no hardware this says so in as many words, because a model
    handed no vitals will otherwise quietly assume normal ones.
    """
    if not readings:
        return ("SENSOR DATA: none. No instruments are connected to this unit.\n"
                "Do NOT assume any vital sign is normal. If a measurement would change "
                "your answer, ask for it in next_questions.")
    lines = [f"  - {r.finding}: {r.value}{(' ' + r.unit) if r.unit else ''}  (from {r.source})"
             for r in readings]
    return "SENSOR DATA (measured, not reported by the crewmember):\n" + "\n".join(lines)
