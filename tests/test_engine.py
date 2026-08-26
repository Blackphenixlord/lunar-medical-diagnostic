"""Engine behaviour. Every test here encodes a decision we made on purpose."""

import glob
import os

import pytest
import yaml

from mdx import load_kb, diagnose
from mdx.engine import support_for, next_best_questions


@pytest.fixture(scope="module")
def kb():
    return load_kb()


# --- the core safety property ---------------------------------------------

def test_unknown_findings_do_not_move_the_score(kb):
    """An unanswered question must be worth exactly zero. If silence nudged the
    score, the tool would invent confidence it has not earned."""
    empty = diagnose(kb, {})
    explicit_unknown = diagnose(kb, {"headache": None, "flank_pain": None, "fever": None})
    a = {f.id: round(f.probability, 9) for f in empty.ranked}
    b = {f.id: round(f.probability, 9) for f in explicit_unknown.ranked}
    assert a == b


def test_no_observations_returns_base_rates_only(kb):
    r = diagnose(kb, {})
    for f in r.ranked:
        assert abs(f.probability - f.condition.prior) < 1e-6


# --- discrimination: the cases that actually matter -----------------------

def test_renal_colic_beats_motion_sickness_when_flank_pain_present(kb):
    obs = {"flank_pain": 8, "pain_colicky": True, "pain_radiates_groin": True,
           "hematuria": True, "nausea": 6, "mission_elapsed_days": 63,
           "symptoms_on_head_movement": False}
    r = diagnose(kb, obs)
    assert r.top.id == "renal_stone"
    sms = r.get("space_motion_sickness")
    assert sms is None or sms.probability < r.top.probability


def test_motion_sickness_wins_early_with_head_movement_trigger(kb):
    obs = {"nausea": 8, "vomiting": True, "symptoms_on_head_movement": True,
           "cold_sweat": True, "flank_pain": 0, "hematuria": False,
           "mission_elapsed_days": 2, "recent_gravity_transition": True}
    r = diagnose(kb, obs)
    assert r.top.id == "space_motion_sickness"


def test_same_symptoms_late_in_mission_stop_being_motion_sickness(kb):
    """Identical presentation, day 2 vs day 90. Mission elapsed time has to matter."""
    base = {"nausea": 8, "vomiting": True, "symptoms_on_head_movement": True, "cold_sweat": True}
    early = diagnose(kb, {**base, "mission_elapsed_days": 2}).get("space_motion_sickness")
    late = diagnose(kb, {**base, "mission_elapsed_days": 90}).get("space_motion_sickness")
    assert late is None or late.probability < early.probability


def test_congestion_since_arrival_reads_as_fluid_shift_not_infection(kb):
    obs = {"nasal_congestion": True, "congestion_since_arrival": True,
           "facial_fullness": True, "fever": 36.7, "sore_throat": False,
           "purulent_discharge": False}
    r = diagnose(kb, obs)
    assert r.top.id == "sinonasal_congestion"
    urti = r.get("urti")
    assert urti is None or urti.probability < 0.20, "must not burn antibiotics on physics"


def test_fever_and_sore_throat_flip_it_to_infection(kb):
    obs = {"nasal_congestion": True, "congestion_since_arrival": False,
           "sore_throat": True, "fever": 38.6, "cough": True, "malaise": True}
    r = diagnose(kb, obs)
    assert r.top.id == "urti"


def test_sans_needs_ocular_findings_not_just_a_headache(kb):
    just_headache = diagnose(kb, {"headache": True, "mission_elapsed_days": 100,
                                  "blurred_near_vision": False, "optic_disc_edema": False})
    sans = just_headache.get("sans")
    assert sans is None or sans.probability < 0.35


def test_sans_fires_on_the_case_definition(kb):
    obs = {"blurred_near_vision": True, "hyperopic_shift": 1.0, "optic_disc_edema": True,
           "choroidal_folds": True, "diplopia": False, "pulsatile_tinnitus": False,
           "mission_elapsed_days": 118}
    assert diagnose(kb, obs).top.id == "sans"


# --- safety: rare-but-lethal must outrank common-but-harmless -------------

def test_red_flag_floats_a_rare_emergency_above_a_common_nuisance(kb):
    """0.5% base rate vs a 45% base rate. The clot still has to be at the top."""
    obs = {"neck_swelling": True, "jugular_distension": True, "shortness_of_breath": True,
           "chest_pain": True, "facial_fullness": True, "nasal_congestion": True,
           "hr_elevated": 104}
    r = diagnose(kb, obs)
    assert r.escalate
    assert r.top.id == "jugular_vte"


def test_escalation_fires_on_infected_obstruction_pattern(kb):
    obs = {"flank_pain": 9, "pain_colicky": True, "hematuria": True,
           "fever": 38.9, "urine_output_low": True}
    r = diagnose(kb, obs)
    assert r.escalate
    assert any("Renal" in x for x in r.escalation_reasons)


def test_orthostatic_intolerance_requires_a_gravity_transition(kb):
    with_t = diagnose(kb, {"presyncope": True, "hr_elevated": 118, "recent_gravity_transition": True})
    without = diagnose(kb, {"presyncope": True, "hr_elevated": 118, "recent_gravity_transition": False})
    a = with_t.get("orthostatic_intolerance")
    b = without.get("orthostatic_intolerance")
    assert a is not None
    assert b is None or b.probability < a.probability


def test_back_pain_with_hematuria_does_not_stay_benign(kb):
    benign = diagnose(kb, {"back_pain": 5, "height_increase": True, "mission_elapsed_days": 10,
                           "pain_colicky": False, "hematuria": False})
    assert benign.top.id == "msk_back_pain_adaptation"
    worrying = diagnose(kb, {"back_pain": 5, "pain_colicky": True, "hematuria": True,
                             "pain_radiates_groin": True, "mission_elapsed_days": 10})
    assert worrying.top.id == "renal_stone"


# --- mechanics -------------------------------------------------------------

def test_support_saturates_and_respects_direction(kb):
    fever = kb.finding("fever")
    assert support_for(fever, 41.0) == pytest.approx(1.0)
    assert support_for(fever, 36.5) == pytest.approx(-1.0)
    assert support_for(fever, None) is None

    sleep = kb.finding("sleep_hours")   # direction: low
    assert support_for(sleep, 3.0) > 0, "3 hours of sleep must SUPPORT sleep disruption"
    assert support_for(sleep, 9.0) < 0


def test_next_best_question_picks_a_discriminator(kb):
    r = diagnose(kb, {"nausea": 7})
    qs = next_best_questions(kb, r, 3)
    assert qs
    assert all(fid in kb.findings for fid, _ in qs)


def test_probabilities_are_bounded(kb):
    obs = {f: True for f in kb.findings if kb.findings[f].type == "bool"}
    for f in diagnose(kb, obs).ranked:
        assert 0.0 <= f.probability <= 1.0


def test_every_result_can_explain_itself(kb):
    """No unexplained numbers. This is the whole design constraint."""
    r = diagnose(kb, {"flank_pain": 8, "hematuria": True, "pain_colicky": True})
    for f in r.ranked:
        assert f.contributions
        moved = [c for c in f.contributions if abs(c.delta) > 0]
        assert moved, f"{f.id} scored but has nothing to show for it"


# --- the saved demo cases must keep passing -------------------------------

CASE_DIR = os.path.join(os.path.dirname(__file__), "..", "cases")


@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(CASE_DIR, "*.yaml"))))
def test_demo_cases(path, kb):
    raw = yaml.safe_load(open(path, encoding="utf-8"))
    if not raw.get("expect_top"):
        pytest.skip("no expectation recorded")
    r = diagnose(kb, raw["observations"])
    assert r.ranked, f"{os.path.basename(path)} produced no differential"
    assert r.top.id == raw["expect_top"], (
        f"{os.path.basename(path)}: expected {raw['expect_top']}, got {r.top.id}"
    )


def test_low_measurement_still_carries_weight(kb):
    """Regression 1, found by running it.

    On flight day 2, mission_elapsed_days contributed NOTHING: its support was
    negative, so it took the absent branch and picked up the default
    absent_weight of 0. "Flight day 2" and "no idea what day it is" scored
    identically, throwing away the best evidence for space motion sickness.

    Fix is in the KB, not the engine: anything genuinely two-sided states its
    other side with an explicit absent_weight.
    """
    known = diagnose(kb, {"nausea": 8, "vomiting": True,
                          "symptoms_on_head_movement": True,
                          "mission_elapsed_days": 2})
    unknown = diagnose(kb, {"nausea": 8, "vomiting": True,
                            "symptoms_on_head_movement": True})
    early = known.get("space_motion_sickness")
    assert early.probability > unknown.get("space_motion_sickness").probability

    contrib = next(c for c in early.contributions if c.finding == "mission_elapsed_days")
    assert contrib.delta > 1.5, "day 2 is strong evidence for SMS, not zero"


def test_a_normal_temperature_does_not_diagnose_a_stuffy_nose(kb):
    """Regression 2, found by running it, and worse than regression 1.

    Making measurements symmetric meant fluid-shift congestion's `fever: -2.0`
    scored -2.0 * -1.0 = +2.00 on a NORMAL temperature. Real output was:

        1. Renal Stone with Renal Colic          99%
        2. Fluid-Shift Sinonasal Congestion      86%   <- from 36.9 C alone

    "A fever would argue against me" is not "no fever is evidence for me".
    """
    r = diagnose(kb, {"flank_pain": 8, "pain_colicky": True, "hematuria": True,
                      "pain_radiates_groin": True, "nausea": 6, "fever": 36.9,
                      "mission_elapsed_days": 63, "headache": False})
    assert r.top.id == "renal_stone"

    sino = r.get("sinonasal_congestion")
    assert sino is None or sino.probability < 0.55, (
        "a normal temperature must not carry congestion on its own"
    )

    for f in r.ranked:
        fever_c = next((c for c in f.contributions if c.finding == "fever"), None)
        if fever_c and fever_c.state == "absent":
            assert abs(fever_c.delta) <= 1.0, (
                f"{f.id}: a normal temperature is weak evidence at most, got {fever_c.delta:+.2f}"
            )


def test_context_alone_cannot_put_a_condition_on_screen(kb):
    """Regression 3, same run. "Flight day 2" with no back complaint at all was
    floating adaptation back pain to 69%. Mission day is context, not a symptom."""
    r = diagnose(kb, {"mission_elapsed_days": 2, "symptoms_on_head_movement": True})
    assert r.top.id == "space_motion_sickness"
    assert r.get("msk_back_pain_adaptation") is None, (
        "no back complaint was made - the mission day alone must not summon it"
    )


def test_contextual_findings_still_modulate_a_real_candidate(kb):
    """Context is not ignored - it just cannot stand alone."""
    day2 = diagnose(kb, {"symptoms_on_head_movement": True, "vomiting": True,
                         "mission_elapsed_days": 2}).get("space_motion_sickness")
    day90 = diagnose(kb, {"symptoms_on_head_movement": True, "vomiting": True,
                          "mission_elapsed_days": 90}).get("space_motion_sickness")
    assert day2.probability > day90.probability


def test_a_high_base_rate_alone_does_not_earn_a_place_on_screen(kb):
    """Regression 4, same run as the others.

    Fluid-shift congestion has a 45% base rate. With +0.50 of evidence it was
    printing at 57%, directly under a kidney stone, telling the crew nothing
    about the crewmember. Probability answers "how likely"; net evidence
    answers "did we learn anything". Both have to clear the bar.
    """
    r = diagnose(kb, {"flank_pain": 8, "pain_colicky": True, "hematuria": True,
                      "pain_radiates_groin": True, "nausea": 6, "fever": 36.9,
                      "mission_elapsed_days": 63, "headache": False})
    assert r.top.id == "renal_stone"
    for f in r.ranked:
        assert f.net_evidence >= 1.0, (
            f"{f.id} shown at {f.probability:.0%} on only {f.net_evidence:+.2f} of evidence"
        )


def test_net_evidence_is_independent_of_the_prior(kb):
    """Two conditions can sit at similar probabilities for completely different
    reasons. The evidence number is what separates them."""
    r = diagnose(kb, {"sore_throat": True, "fever": 38.6, "cough": True, "malaise": True})
    urti = r.get("urti")
    assert urti is not None
    assert urti.net_evidence > 4.0, "four converging findings is strong evidence"
    assert abs(urti.net_evidence - sum(c.delta for c in urti.contributions)) < 1e-9


def test_a_required_unknown_finding_becomes_the_first_question(kb):
    """If a condition cannot be called without finding X, then X is the fastest
    question available - it confirms the candidate or removes it outright.

    Real case that motivated this: a post-EVA crewmember with confusion and
    weakness scored "laceration 24%", because weakness appears in that rule,
    while nobody had asked the one question that settles it - is there a wound?
    """
    obs = {"recent_decompression": True, "prebreathe_shortened": True,
           "confusion": True, "balance_impaired": True, "numbness_or_weakness": True}
    r = diagnose(kb, obs)
    qs = next_best_questions(kb, r, 3)
    asked = [fid for fid, _ in qs]

    wound = r.get("wound_laceration")
    if wound is not None:
        assert "open_wound" in asked, (
            "laceration is on screen but nobody asked whether there is a wound"
        )


def test_required_findings_still_rule_a_condition_out_when_denied(kb):
    """The other half of the same mechanism."""
    ruled_in = diagnose(kb, {"open_wound": True, "wound_gaping": True})
    assert ruled_in.top.id == "wound_laceration"

    ruled_out = diagnose(kb, {"open_wound": False, "wound_gaping": True})
    assert ruled_out.get("wound_laceration") is None


def test_decompression_sickness_requires_a_decompression(kb):
    """The one place physics lets us rule something out outright."""
    after_eva = diagnose(kb, {"recent_decompression": True, "joint_pain": 7,
                              "skin_mottling": True})
    assert after_eva.top.id == "decompression_sickness"

    no_eva = diagnose(kb, {"recent_decompression": False, "joint_pain": 7,
                           "skin_mottling": True})
    assert no_eva.get("decompression_sickness") is None


def test_eva_shoulder_pain_days_later_is_not_the_bends(kb):
    """Crying wolf on the commonest EVA complaint would make the tool useless."""
    r = diagnose(kb, {"recent_decompression": False, "shoulder_pain": 6,
                      "pain_after_eva_training": True, "skin_mottling": False,
                      "numbness_or_weakness": False, "range_of_motion_limited": True})
    assert r.top.id == "msk_shoulder_overuse"


def test_dental_abscess_escalates_but_a_sensitive_tooth_is_still_urgent(kb):
    swollen = diagnose(kb, {"tooth_pain": 9, "jaw_or_face_swelling": True, "fever": 38.7})
    assert swollen.top.id == "dental_emergency"
    assert swollen.escalate


# --- alarm discipline ------------------------------------------------------
# An alarm that fires for a condition nobody is seriously considering is not
# caution, it is noise - and noise is how real alarms get ignored.

def test_a_sensitive_tooth_does_not_page_the_flight_surgeon(kb):
    r = diagnose(kb, {"tooth_pain": 5, "pain_on_cold": True,
                      "jaw_or_face_swelling": False, "fever": 36.8})
    assert r.top.id == "dental_emergency"
    assert not r.escalate, "a mild toothache must not raise an alarm"


def test_a_dental_abscess_raises_exactly_one_alarm(kb):
    """Regression from a real run.

    `fever` is a red flag in the dental, wound, renal and infection rules. A
    crewmember with a dental abscess was told to escalate for a laceration they
    did not have, a kidney stone they did not have, and a chest infection they
    did not have. Four alarms, one problem.
    """
    r = diagnose(kb, {"tooth_pain": 9, "jaw_or_face_swelling": True, "fever": 38.7})
    assert r.escalate
    assert len(r.escalation_reasons) == 1, f"expected one alarm, got: {r.escalation_reasons}"
    assert "Dental" in r.escalation_reasons[0]


def test_a_condition_awaiting_a_required_finding_cannot_alarm(kb):
    """You do not page the ground about a laceration when nobody has
    established there is a wound."""
    r = diagnose(kb, {"tooth_pain": 9, "jaw_or_face_swelling": True, "fever": 38.7})
    wound = r.get("wound_laceration")
    if wound is not None:
        assert wound.awaiting_required, "open_wound is unknown here"
        assert not any("Laceration" in x for x in r.escalation_reasons)


def test_a_small_closed_cut_does_not_alarm_but_a_gaping_one_does(kb):
    small = diagnose(kb, {"open_wound": True, "wound_gaping": False,
                          "bleeding_uncontrolled": False, "wound_spreading_redness": False})
    assert small.top.id == "wound_laceration"
    assert not small.escalate

    gaping = diagnose(kb, {"open_wound": True, "wound_gaping": True})
    assert gaping.escalate, "a wound that needs closing is a flight-surgeon call"


def test_the_leading_candidate_can_always_alarm(kb):
    """Gate 2 exempts rank 1 - if it is what we think is going on, we say so."""
    r = diagnose(kb, {"neck_swelling": True, "jugular_distension": True,
                      "shortness_of_breath": True, "chest_pain": True})
    assert r.top.id == "jugular_vte"
    assert r.escalate
