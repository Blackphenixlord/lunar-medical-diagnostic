# Crew Terminal

**Owner: Cruz**

This is the interface an astronaut actually uses. Nothing here yet — start with
paper sketches before code.

## Design constraints

1. **The user is not a doctor.** No medical jargon anywhere. If a word would
   not appear in a normal conversation, do not use it.
2. **The user may be stressed, injured, or alone.** Big targets, few steps,
   nothing clever.
3. **Show uncertainty honestly.** Never make a low-confidence answer look
   confident. "Not very confident" must look different from "fairly confident."
4. **The STOP screen matters most.** When the system escalates, that screen is
   the whole product. Make it unmissable.
5. **Runs offline.** No web fonts, no CDNs, no API calls.

## Talking to the engine

```python
from engine.rules import Engine

eng = Engine()
result = eng.assess(["headache", "fatigue"])

result.escalate           # True = show the STOP screen
result.reason             # why it escalated
result.category           # what it thinks the issue is
result.procedure          # what to tell the user to do
result.confidence         # 0.0 - 1.0
result.confidence_label   # plain language version — use this in the UI
```

## User testing

Log every session. Where did the tester hesitate? What did they misread? What
did they click that you did not expect? That log is a CDR deliverable, not
just notes for yourself.
