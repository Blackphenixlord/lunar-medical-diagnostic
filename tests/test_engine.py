"""
Test suite.

Run:  python3 -m tests.test_engine

NASA HUNCH grades quality assurance and user testing as separate categories
from code. CDR requires a Test Plan and Test Results with statistics. This
file is the machine-checkable half of that.

Joaquin owns the CASES list. Every case is a symptom set with a known
correct answer, and the source for WHY it is the correct answer.
"""

import sys
from engine.rules import Engine


# ---------------------------------------------------------------------
# CASES
# Each case: (name, symptoms, expected_escalate, expected_category_or_None)
#
# Joaquin: add 20 of these before PDR. Each one needs to come from the
# same sourced material as the rules themselves.
# ---------------------------------------------------------------------
CASES = [
    ("chest pain always escalates",       ["chest_pain"],                True,  None),
    ("breathing trouble always escalates", ["shortness_of_breath"],      True,  None),
    ("confusion always escalates",         ["confusion"],                True,  None),
    ("red flag wins even with others",     ["headache", "chest_pain"],   True,  None),
    ("nothing entered does not crash",     [],                           False, None),
    ("unknown combo escalates",            ["nausea"],                   True,  None),
]


def run():
    eng = Engine()
    passed = failed = 0
    failures = []

    print("=" * 62)
    print("  TEST RESULTS")
    print("=" * 62)

    # --- integrity check: every rule must cite a source ---------------
    print("\n[INTEGRITY] Every rule must cite a source")
    unsourced = eng.unsourced_rules()
    if unsourced:
        print(f"  FAIL — {len(unsourced)} unsourced rule(s): {', '.join(unsourced)}")
        print("         A judge WILL ask where our medical rules came from.")
        failed += 1
        failures.append("unsourced rules")
    else:
        print("  PASS")
        passed += 1

    # --- behaviour cases ---------------------------------------------
    print("\n[BEHAVIOUR]")
    for name, symptoms, want_esc, want_cat in CASES:
        try:
            r = eng.assess(symptoms)
        except Exception as e:
            print(f"  FAIL  {name}  — raised {type(e).__name__}: {e}")
            failed += 1
            failures.append(name)
            continue

        ok = (r.escalate == want_esc)
        if ok and want_cat is not None:
            ok = (r.category == want_cat)

        if ok:
            print(f"  PASS  {name}")
            passed += 1
        else:
            print(f"  FAIL  {name}")
            print(f"        wanted escalate={want_esc}, got escalate={r.escalate} "
                  f"category={r.category!r}")
            failed += 1
            failures.append(name)

    total = passed + failed
    pct = (passed / total * 100) if total else 0
    print("\n" + "-" * 62)
    print(f"  {passed}/{total} passed  ({pct:.1f}%)")
    if failures:
        print(f"  Failing: {', '.join(failures)}")
    print("-" * 62)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
