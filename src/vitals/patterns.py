"""The phrasebook: how crewmembers actually say things -> finding ids.

This file is pure data. It lives apart from extract.py so that adding a
phrasing is a one-line edit to an obvious table, and so seventy lines of regex
do not bury the twenty lines of logic that use them.

WHO EDITS THIS
    Cruz. Every phrasing user testing turns up that we did not anticipate goes
    in here. That IS the test data - `tests/test_extract.py` reads these tables.

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
                                  r"blood when i (pee|urinate)", r"peeing blood",
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
                                  r"hard to breathe", r"winded", r"out of breath",
                                  r"breathless"],
    "chest_pain":                [r"chest (pain|hurts|tight)", r"pain in my chest"],
    "neck_swelling":             [r"neck.{0,20}(swollen|swelling|bigger)", r"swelling in my neck"],
    "limb_swelling_unilateral":  [r"one (arm|leg).{0,20}(swollen|bigger)",
                                  r"(arm|leg).{0,15}swollen.{0,20}other"],
    "presyncope":                [r"light ?headed", r"about to (pass out|faint)",
                                  r"nearly fainted", r"dizzy when i stand"],
    "shoulder_pain":             [r"shoulder (pain|hurts|sore)", r"pain in my shoulder",
                                  r"shoulder.{0,25}(ache|aching|hurt|sore|pain)"],
    "back_pain":                 [r"back (pain|hurts|ache|sore)", r"my back is killing"],
    "pain_after_eva_training":   [r"(after|during).{0,20}(eva|spacewalk|suit)", r"suited (work|run)"],
    "pain_after_exercise":       [r"(after|during).{0,20}(ared|exercise|workout|lifting|resistive)"],
    "range_of_motion_limited":   [r"can'?t (lift|raise|move) (it|my)", r"range of motion", r"stiff"],
    "numbness_or_weakness":      [r"numb", r"tingl", r"pins and needles",
                                  r"weak(ness)? in my (arm|leg|hand)",
                                  r"(arm|leg|hand)s? (feels?|is|are|went|going) weak"],
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
    # --- added 26 Sep: whole sections that had NO phrasings at all ------------
    # The first benchmark run on Joshua's PC showed the extractor finding
    # nothing in "came in off the EVA ... blotchy marbled rash" or "tooth has
    # been killing me". DCS, dental and wounds were added to the knowledge base
    # after this file was written and never got a phrasebook.

    # decompression / EVA
    "recent_decompression":      [r"(off|after|back from|finished|since) (the |my |an? )?(eva|spacewalk)",
                                  r"(eva|spacewalk).{0,25}(today|this morning|earlier|hours? ago|yesterday)",
                                  r"\bpost[- ]?(eva|spacewalk)", r"\bairlock", r"\bdepress(uriz|ur)", r"(just|recently) (did|came in from) (an? |the )?(eva|spacewalk)"],
    "prebreathe_shortened":      [r"pre-?breathe.{0,30}(short|cut|skip|rush|early)",
                                  r"(short|cut|skip|rush)\w*.{0,20}pre-?breathe"],
    "relief_on_repressurization": [r"(better|eased|relief|went away).{0,30}(repress|pressure (went|was) (up|raised))"],
    "joint_pain":                [r"\bjoints?\b.{0,25}(ache|aching|hurt|pain|sore)",
                                  r"(ache|pain|hurt)\w*.{0,15}in (my|the) (elbow|knee|wrist|joint)",
                                  r"(elbow|knee|wrist).{0,20}(ache|aching|hurt|pain)",
                                  r"deep (boring |dull |aching )?(ache|pain)"],
    "skin_mottling":             [r"(blotch|marbl|mottl)\w*", r"cutis marmorata",
                                  r"(purple|red).{0,15}(patch|rash).{0,25}(skin|arm|chest)"],
    "confusion":                 [r"\bconfus", r"disorient", r"don'?t know where i am",
                                  r"can'?t think straight"],
    "balance_impaired":          [r"(balance|coordination).{0,20}(off|bad|gone|problem|trouble)",
                                  r"\bunsteady", r"keep (bumping|stumbling|falling)", r"clumsy"],

    # dental
    "tooth_pain":                [r"\btooth", r"\bteeth", r"\bmolar", r"toothache"],
    "pain_on_cold":              [r"(cold|hot) (drink|water|food|air).{0,25}(hurt|pain|zing|shoot)",
                                  r"(hurt|pain|zing|shoot)\w*.{0,20}(cold|hot) (drink|water|food)",
                                  r"sensitive to (cold|hot)"],
    "pain_on_biting":            [r"(bit|bite|biting|chew|chewing).{0,25}(hurt|pain|kill)",
                                  r"hurts? (to|when i) (bite|chew)"],
    "jaw_or_face_swelling":      [r"(jaw|gum|cheek|face).{0,20}(swollen|swelling|puffed)",
                                  r"swell\w*.{0,20}(jaw|gum|cheek)"],
    "lost_filling_or_crown":     [r"(lost|fell out|came out|broke|cracked|chipped).{0,20}(filling|crown|tooth)",
                                  r"(filling|crown).{0,20}(fell|came|popped) out"],
    "pain_wakes_from_sleep":     [r"(wakes?|waking|woke) me (up)?", r"keeps me up at night",
                                  r"can'?t sleep (because|from) the pain"],

    # wounds
    "open_wound":                [r"\bcut (my|myself|it|open|across|on|in)", r"\b(gash|laceration)",
                                  r"\b(deep|bad|big|nasty|long) cut",
                                  r"sliced", r"\bwound\b", r"\bi cut\b"],
    "bleeding_uncontrolled":     [r"(won'?t|doesn'?t|isn'?t|not) stop(ping)? bleeding",
                                  r"bleeding.{0,20}(won'?t|doesn'?t|not) stop",
                                  r"(still|keeps) bleeding.{0,20}(pressure|despite)"],
    "wound_gaping":              [r"(gap|gaping|spread(s|ing)? open|won'?t (stay|close) (shut|closed))",
                                  r"edges.{0,20}(apart|open|won'?t close)", r"(needs|might need) stitches"],
    "foreign_body":              [r"(something|metal|glass|debris|splinter|shard).{0,20}(in|stuck in) (it|the (cut|wound))",
                                  r"foreign (body|object)"],
    "wound_spreading_redness":   [r"(red|redness).{0,20}(spread|streak|getting bigger)",
                                  r"\bpus\b", r"(warm|hot) (to the touch|around the cut)",
                                  r"oozing"],
    "tetanus_status_unknown":    [r"(don'?t know|not sure|can'?t remember).{0,25}tetanus",
                                  r"tetanus.{0,25}(out of date|expired|years ago)"],

    # general
    "fatigue":                   [r"\btired", r"exhausted", r"\bfatigue", r"no energy", r"wiped out"],

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
PAIN_SCALE_PATTERN = (
    r"(\d{1,2})\s*(?:out of|/)\s*10"
    r"|\b(?:a|an|maybe a|maybe an|about a|about an|like a|like an|around a|around an)\s+"
    r"(10|[0-9])\b(?!\s*(?:hours?|hrs?|days?|mins?|minutes?|am|pm|times?|diopt|d\b|[:./]\d))"
)

# Findings a bare 0-10 score is allowed to attach to, best candidate first.
PAIN_SCALE_TARGETS = ("flank_pain", "back_pain", "tooth_pain", "joint_pain",
                      "shoulder_pain", "nausea", "fatigue")


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
