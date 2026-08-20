"""
Minimal command-line terminal. This is a DEVELOPMENT tool.
Cruz builds the real crew interface in terminal/.
"""

from engine.rules import Engine


def main():
    eng = Engine()

    print("=" * 60)
    print("  LUNAR MEDICAL DIAGNOSTIC SYSTEM  —  dev terminal")
    print("=" * 60)

    missing = eng.unsourced_rules()
    if missing:
        print(f"\n  !! WARNING: {len(missing)} rule(s) have no source: {', '.join(missing)}")
        print("     These must be sourced before PDR.\n")

    ids = list(eng.symptoms)
    print("\nWhat is wrong? Enter the numbers, separated by spaces.\n")
    for i, sid in enumerate(ids, 1):
        print(f"  {i:>2}. {eng.symptoms[sid]['prompt']}")

    raw = input("\n> ").strip()
    try:
        picked = [ids[int(n) - 1] for n in raw.split()]
    except (ValueError, IndexError):
        print("Could not read that. Enter numbers from the list, like: 1 3")
        return

    r = eng.assess(picked)

    print("\n" + "-" * 60)
    if r.escalate:
        print("  STOP — WAIT FOR EARTH")
        print("-" * 60)
        print(f"\n  Why: {r.reason}\n")
        print(f"  {r.procedure}\n")
    else:
        print(f"  Possible issue: {r.category}")
        print("-" * 60)
        print(f"\n  How sure are we: {r.confidence_label} ({r.confidence})")
        print(f"\n  What to do:\n    {r.procedure}\n")
        print(f"  Based on rules: {', '.join(r.fired_rules)}")
    print("-" * 60)
    print("\n  This is a student prototype. It is not a medical device.")
    print("  Never use it to make real medical decisions.\n")


if __name__ == "__main__":
    main()
