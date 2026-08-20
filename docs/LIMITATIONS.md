# What this system cannot do

**Owner: Joaquin**

Required for FDR. Also shown in the crew terminal.

Documenting limits honestly is a feature. A tool that admits what it does not
know is more trustworthy than one that always produces an answer.

## Hard limits

- Cannot analyze images, scans, or ultrasound.
- Cannot measure vital signs — it only knows what the user types in.
- Cannot recommend medication or dosages.
- Cannot diagnose rare conditions or anything outside its rule set.
- Cannot account for a user's medical history.
- Has never been tested on real patients and never will be.
- Is not a certified medical device.

## Known failure modes

*(Joaquin: fill this in as testing finds them. "We found no failures" is not
a credible answer at FDR.)*

| What breaks it | What happens | Mitigation |
|---|---|---|
| | | |

## When the system escalates

- Any red-flag symptom is reported
- Best match scores below the confidence threshold
- Two categories score too close to choose between
- No rule matches at all
