"""The phrasebook: how crewmembers actually say things -> finding ids.

This file is pure data. It lives apart from extract.py so that adding a
phrasing is a one-line edit to an obvious table, and so seventy lines of regex
do not bury the twenty lines of logic that use them.

WHO EDITS THIS
    Cruz. Every phrasing user testing turns up that we did not anticipate goes
    in here. That IS the test data - `tests/test_llm.py` reads these tables.

HOW TO ADD ONE
    Find the finding id in kb/findings.yaml, add a lowercase regex to its list.
    Patterns are matched against lowercased text with a leading and trailing
    space, so \\b works at both ends. First match wins; order does not matter
    beyond that.
"""

from __future__ import annotations

# --- yes/no findings -------------------------------------------------------
# finding id -> surface forms that mean it is PRESENT.
# Negation ("no headache") is handled by extract.py, not by these patterns.

SYMPTOM_PATTERNS: dict[str, list[str]] = {
    "headache":                  [r"\bhead ?ache", r"\bmy head hurts",
                                  r"\bhead is (pounding|killing|splitting)",
                                  r"\bhead is killing me", r"\bmigraine"],
    "headache_worse_lying_flat": [r"worse (when|if) .*(head[- ]?down|lying|upside)",
                                  r"worse after (i )?sleep"],
    "nausea":                    [r"\bnause", r"\bqueasy", r"\bsick to my stomach",
                                  r"\bwant to throw up"],
    "vomiting":                  [r"\bvomit", r"\bthrew up", r"\bthrowing up", r"\bpuke"],
    "vertigo":                   [r"\bspinning", r"\bvertigo", r"\btumbling",
                                  r"\broom is moving"],
    "symptoms_on_head_movement": [r"(worse|bad).{0,25}(move|turn|tilt).{0,15}head",
                                  r"head movement makes it worse"],
    "cold_sweat":                [r"cold sweat", r"clammy", r"\bpale and sweaty"],
    "blurred_near_vision":       [r"(blurr?y|hard|harder|trouble|difficult).{0,25}(read|close ?up|near vision)",
                                  r"can'?t read", r"vision.{0,12}blurr?y"],
    "scotoma":                   [r"blind spot", r"dark (patch|spot)", r"scotoma"],
    "diplopia":                  [r"double vision", r"seeing double", r"diplopia"],
    "pulsatile_tinnitus":        [r"whoosh", r"pulsatile tinnitus",
                                  r"ringing.{0,15}with my (heart|pulse)"],
    "flank_pain":                [r"\bflank", r"pain in (my )?(right |left |lower )*(side|flank)",
                                  r"(right|left) side (hurts|is killing|pain)", r"\bside hurts"],
    "pain_colicky":              [r"comes? (and goes|in waves)", r"\bwaves\b", r"colicky"],
    "pain_radiates_groin":       [r"(down|toward|to).{0,15}groin", r"radiat\w+.{0,20}groin"],
    "hematuria":                 [r"blood in (my )?(urine|pee)",
                                  r"(urine|pee).{0,20}(red|pink|brown)", r"hematuria"],
    "dysuria":                   [r"burns? (when|to) (i )?(pee|urinat)",
                                  r"hurts to (pee|urinate)", r"dysuria"],
    "urine_output_low":          [r"(not|barely|hardly).{0,20}(peeing|urinating)",
                                  r"urine output.{0,15}(low|down|drop)"],
    "nasal_congestion":          [r"(stuffy|stuffed|blocked|congest|bunged|plugged)(\s?up)?",
                                  r"can'?t breathe through my nose",
                                  r"nose is (blocked|stuffed|plugged)"],
    "facial_fullness":           [r"face feels (full|puffy)", r"facial (fullness|puffiness)",
                                  r"puffy face"],
    "congestion_since_arrival":  [r"(since|ever since).{0,25}(i got here|arriv|launch|day one|docking)",
                                  r"(whole|entire) (mission|time)", r"never (really )?(cleared|went away)"],
    "sore_throat":               [r"sore throat", r"throat hurts", r"scratchy throat"],
    "cough":                     [r"\bcough"],
    "purulent_discharge":        [r"(yellow|green).{0,20}(mucus|discharge|snot)", r"purulent"],
    "shortness_of_breath":       [r"short(ness)? of breath", r"can'?t catch my breath",
                                  r"hard to breathe", r"winded"],
    "chest_pain":                [r"chest (pain|hurts|tight)", r"pain in my chest"],
    "neck_swelling":             [r"neck.{0,20}(swollen|swelling|bigger)", r"swelling in my neck"],
    "limb_swelling_unilateral":  [r"one (arm|leg).{0,20}(swollen|bigger)",
                                  r"(arm|leg).{0,15}swollen.{0,20}other"],
    "presyncope":                [r"light ?headed", r"about to (pass out|faint)",
                                  r"nearly fainted", r"dizzy when i stand"],
    "shoulder_pain":             [r"shoulder (pain|hurts|sore)", r"pain in my shoulder"],
    "back_pain":                 [r"back (pain|hurts|ache|sore)", r"my back is killing"],
    "pain_after_eva_training":   [r"(after|during).{0,20}(eva|spacewalk|suit)", r"suited (work|run)"],
    "pain_after_exercise":       [r"(after|during).{0,20}(ared|exercise|workout|lifting|resistive)"],
    "range_of_motion_limited":   [r"can'?t (lift|raise|move) (it|my)", r"range of motion", r"stiff"],
    "numbness_or_weakness":      [r"numb", r"tingl", r"pins and needles",
                                  r"weak(ness)? in my (arm|leg|hand)"],
    "height_increase":           [r"(taller|grown|gained height)", r"height.{0,15}(increase|up)"],
    "difficulty_falling_asleep": [r"(can'?t|trouble|hard to|struggling to) (fall|get to) ?asleep",
                                  r"lying awake"],
    "sleep_aid_use":             [r"(sleep|sleeping) (aid|pill|med)", r"took (an? )?ambien",
                                  r"melatonin"],
    "schedule_shifted":          [r"(schedule|sleep).{0,20}shift", r"slam(med)?",
                                  r"woke up early for (the )?(docking|eva)"],
    "cognitive_slowing":         [r"(can'?t|trouble|hard to) (concentrate|focus)", r"foggy",
                                  r"slow(er)? to react", r"brain fog"],
    "irritability":              [r"irritab", r"short[- ]tempered", r"snapping at", r"on edge"],
    "malaise":                   [r"run ?down", r"generally unwell", r"feel awful", r"lousy"],
    "recent_gravity_transition": [r"(just )?(landed|undock|launch|re-?entry)",
                                  r"(since|after) (landing|touchdown)"],
    "purulent_discharge_alt":    [],
}


# --- measured / numeric findings -------------------------------------------
# finding id -> one regex whose first non-empty group is the number.

NUMERIC_PATTERNS: dict[str, str] = {
    "fever":                r"(?:temp(?:erature)?|fever)\D{0,12}(\d{2}(?:\.\d)?)",
    "mission_elapsed_days": r"(?:flight day|fd|day|mission day)\s*(\d{1,3})\b",
    "sleep_hours":          r"(\d(?:\.\d)?)\s*(?:hours?|hrs?|h)\s*(?:of\s*)?sleep"
                            r"|sleeping\s*(?:about\s*)?(\d(?:\.\d)?)",
    "hr_elevated":          r"(?:heart rate|hr|pulse)\D{0,10}(\d{2,3})",
    "hyperopic_shift":      r"(\d(?:\.\d+)?)\s*(?:d|diopt)",
}

# "8 out of 10", "8/10". Attached to whichever pain finding is already present.
PAIN_SCALE_PATTERN = r"(\d{1,2})\s*(?:out of|/)\s*10"

# Findings a bare 0-10 score is allowed to attach to, best candidate first.
PAIN_SCALE_TARGETS = ("flank_pain", "back_pain", "shoulder_pain", "nausea", "fatigue")


# --- negation --------------------------------------------------------------
# Cues that flip a match from PRESENT to ABSENT when they sit just before it.

NEGATION_CUES = [
    r"\bno\b", r"\bnot\b", r"\bnever\b", r"\bwithout\b", r"\bdenies?\b",
    r"\bdon'?t have\b", r"\bhaven'?t\b", r"\bnothing\b", r"\bfree of\b",
]

# How far back to look for a cue, in characters.
NEGATION_LOOKBACK = 28

# The lookback stops dead at any of these. Without that, "never really cleared.
# My face feels full" reads the "never" from the previous sentence and records
# facial fullness as ABSENT - the exact opposite of what was said.
CLAUSE_BOUNDARIES = ".!?;,"
