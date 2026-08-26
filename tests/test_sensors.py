"""Sensors: the slot exists, and it is honestly empty.

The single most important property of this module today is that it invents
NOTHING. A fabricated vital sign is worse than a missing one - a missing one
makes the model ask, a fake one makes it conclude.
"""

from mdx import sensors


def test_nothing_is_registered_because_nothing_is_plugged_in():
    assert sensors.REGISTERED == []
    assert sensors.read_all() == []
    assert sensors.status() == "no sensors connected"


def test_no_sensors_produces_no_observations():
    assert sensors.as_observations(sensors.read_all()) == {}


def test_the_prompt_tells_the_model_there_are_no_vitals():
    ctx = sensors.as_context([])
    assert "none" in ctx.lower()
    assert "do not assume" in ctx.lower()


def test_a_broken_sensor_cannot_take_the_tool_down(monkeypatch):
    class Exploding:
        name = "exploding"
        def available(self): raise RuntimeError("hardware on fire")
        def read(self): return []

    monkeypatch.setattr(sensors, "REGISTERED", [Exploding()])
    assert sensors.read_all() == []


def test_readings_map_onto_real_finding_ids():
    """When hardware does arrive, its output has to be a finding the KB knows."""
    from mdx import load_kb
    kb = load_kb()
    r = sensors.Reading(finding="fever", value=38.4, unit="C", source="test")
    assert r.finding in kb.findings
    assert sensors.as_observations([r]) == {"fever": 38.4}
