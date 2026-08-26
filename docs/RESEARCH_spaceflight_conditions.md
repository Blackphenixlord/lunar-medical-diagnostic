# Research notes — medical conditions specific to spaceflight

*Monday board item: "Research medical conditions specific to spaceflight" (Joaquin, due Sep 18).*
*Starting pass. Every condition below is already encoded in `kb/conditions/`.*

---

## The finding that shaped the whole design

**NASA's own risk-modelling papers say in-flight medical event data is severely
limited.** For several conditions on this list the recorded in-flight incidence
is literally zero — they are modelled hazards, not observed ones. Renal stones
with colic is the headline example: NASA models it as a credible mission-
threatening event that *has not yet happened in flight*.

That is why this project is a weighted-evidence expert system and not a trained
classifier. There is nothing to train on. It is also the strongest answer we
have to "why does this need to exist" — the crew has to be ready for the first
one, and there is no case history to learn from.

---

## 1. Spaceflight-Associated Neuro-Ocular Syndrome (SANS)
`kb/conditions/sans.yaml`

Does not exist on Earth. Driven by the headward fluid shift.

- Case definition: optic disc edema, posterior globe flattening, choroidal/retinal
  folds, optic nerve sheath distension, hyperopic refractive shift.
- Hyperopic shift **up to 1.5 D, within 3 weeks** of microgravity exposure.
- Dose–response with mission length: **~23%** report near-vision disturbance after
  short-duration flight vs **~47%** after long-duration ISS increments.
- **Diplopia, pulsatile tinnitus and transient visual obscurations are notably
  ABSENT** — unlike terrestrial idiopathic intracranial hypertension. Their
  absence supports SANS. We encoded them as negative weights.
- Optic nerve kinks reported at 96% prevalence on MRI.

## 2. Space Motion Sickness
`kb/conditions/space_motion_sickness.yaml`

Nausea and headaches are named as **frequently occurring in-flight conditions
requiring medical attention**. Almost entirely a first-72-hours phenomenon,
provoked by head movement. The engine weights mission elapsed time *negatively*
so the same symptoms on flight day 40 stop reading as SMS — that time-dependence
is the point.

## 3. Renal stone with renal colic
`kb/conditions/renal_stone.yaml`

Bone demineralization dumps calcium into urine while crew are chronically
underhydrated. NASA lists this as a modelled-but-unobserved hazard. Most likely
condition on this list to force a medical evacuation. Discriminators against the
benign look-alike (adaptation back pain): colicky character, radiation to groin,
hematuria. **Fever + flank pain + low urine output = infected obstruction = emergency.**

## 4. Fluid-shift sinonasal congestion
`kb/conditions/sinonasal_congestion.yaml`

The classic microgravity mimic — feels like a permanent head cold that never
becomes one. Discriminator is **time course**: fluid-shift congestion starts on
arrival and never fully clears; infection has a defined onset, a sore throat or
fever, and resolves. Getting this wrong wastes the mission's very limited
antibiotic supply, which is why we built a rule for it rather than folding it
into URTI.

## 5. Upper respiratory tract infection
`kb/conditions/urti.yaml`

The **Health Stabilization Program** pre-screens crew specifically to keep
respiratory and enteric infections off the vehicle, so the on-orbit base rate is
lower than terrestrial. But closed-loop air and no real isolation mean one
infection is a crew-wide operational problem.

## 6. Internal jugular venous thrombosis
`kb/conditions/jugular_vte.yaml`

On Earth gravity drains the head; in microgravity the IJVs engorge and flow can
stagnate or reverse. NASA has documented altered IJV flow across crew and at
least one in-flight thrombus. **Terrestrial risk scoring does not transfer** — a
crewmember with zero conventional risk factors can still develop this. Lowest
prior in the KB (0.5%) and the one that can kill someone, so the rule is tuned
to escalate early.

## 7. Shoulder overuse injury
`kb/conditions/msk_shoulder_overuse.yaml`

Musculoskeletal is the highest-volume injury category in flight: **219
musculoskeletal injuries across ~231,725 hours** of US in-flight operations.
NASA specifically tracks shoulder injury from EVA suit training. Note the trap:
ARED resistive exercise is the countermeasure for bone loss *and* a cause of
these injuries.

## 8. Adaptation back pain / spinal elongation
`kb/conditions/msk_back_pain_adaptation.yaml`

The spine unloads, discs rehydrate, crew measurably get taller, and the stretch
hurts. Benign and self-limiting — but it sits in the same body region as renal
colic, which is not. Existing in the KB mainly so the engine has something
correct to prefer over a stone.

## 9. Circadian desynchrony and sleep disruption
`kb/conditions/sleep_disruption_circadian.yaml`

**Sleep difficulty affects more than half of all US crews.** The SDMIF model
predicted **~51 ± 39 sleep-medication doses per astronaut per ISS increment**.
Sixteen sunrises a day plus schedule slams for dockings and EVAs. Danger is
indirect: inattention, slowed reaction time, poor decision-making. Highest prior
in the KB (0.50) — closer to the default state than to a disease.

## 10. Orthostatic intolerance
`kb/conditions/orthostatic_intolerance.yaml`

The one condition here that is dangerous **on the ground**. Weeks of fluid shift
shed plasma volume and slacken the baroreflex; when gravity returns there is not
enough blood to perfuse the brain on standing. Peak risk is the first hours to
days after landing — exactly when a crewmember might need to exit a vehicle
unaided.

## 11. Elevated-CO₂ / environmental headache
`kb/conditions/tension_headache_co2.yaml`

No convection in microgravity, so exhaled CO₂ pools around a stationary
crewmember's head — someone working head-down in a rack can be breathing far
worse air than the cabin sensor reports. Crew report headache well below
terrestrial industrial CO₂ limits. **The tell is epidemiological, not clinical:
if more than one crewmember has a headache at once, suspect the atmosphere, not
the people.** No other rule in the KB is diagnosed by asking about somebody else.

---

## Gaps — next research pass

**Closed 23 Aug** (were gaps, now have rules):

- **Decompression sickness** — `kb/conditions/decompression_sickness.yaml`. EVA problem,
  not a microgravity problem: the cabin is at sea-level pressure and the suit is far lower,
  so every spacewalk is a decompression. Type I is joint pain and mottled skin; Type II hits
  the CNS and can kill. Prevention is denitrogenation via 3–5 hour prebreathe. Treatment is
  repressurization to a minimum of 16.4 psia. **NASA has never had a Type II event in
  spaceflight** — a statement about how good the prevention is, not how safe the physiology is.
- **Dental emergency** — `kb/conditions/dental_emergency.yaml`. NASA's Integrated Medical
  Model predicts, per person-year: caries **0.39**, abscess 0.023, exposed pulp 0.020,
  crown replacement 0.005, avulsion 0.003. Caries at 0.39 makes this one of the likeliest
  events in the whole knowledge base. No documented US in-flight case, but a cosmonaut on
  Salyut 6 in 1978 had incapacitating dental pain for the last two weeks of a 96-day flight.
  Crew training tops out at pulling a tooth.
- **Laceration / open wound** — `kb/conditions/wound_laceration.yaml`. Two things change in
  microgravity: blood does not fall (it pools in surface-tension domes and floats free, so it
  has to be captured, not mopped), and a closed vehicle with a finite antibiotic supply makes
  infection much worse than the same wound on Earth. Crew are trained to stitch.

**Still open:**

- **Burns** — real hazard, no rule. Must not be swallowed by the laceration rule; the
  treatment is entirely different.
- **Ocular foreign body** — debris does not fall in microgravity, it floats at head height.
  Genuine ISS hazard, no rule.
- **Behavioral health** — deliberately excluded, not forgotten. A scoring engine is the wrong
  tool and a wrong answer here does real harm. Be ready to defend that as a choice.

**Deliberately NOT a rule — radiation.** This one is worth saying out loud at review.
Radiation risk is **dosimetry and long-term cancer probability**, not something you can
diagnose from a complaint — acute radiation syndrome does not present at ISS dose rates. A
symptom-driven engine is structurally the wrong tool, so the correct behaviour is to return
nothing and route to the ground. There is a prompt in the bank (`none_radiation`) that
enforces exactly that.

- We still need a **real medical source** to review these weights. That is the open CRITICAL
  item on the board and the single biggest risk to the project's credibility at review.
  Numbers pulled from literature by three high schoolers are a starting point, not a
  validated knowledge base.

## Sources

- [Spaceflight-Associated Neuro-Ocular Syndrome (SANS) — EyeWiki](https://eyewiki.org/Spaceflight-Associated_Neuro-Ocular_Syndrome_(SANS))
- [SANS and the neuro-ophthalmologic effects of microgravity: a review and an update — npj Microgravity](https://www.nature.com/articles/s41526-020-0097-9)
- [SANS: expert consensus on diagnosis and management — Eye (Nature)](https://www.nature.com/articles/s41433-026-04651-6)
- [Medical Operations and Clinical Care — NASA](https://www.nasa.gov/reference/medical-operations-and-clinical-care/)
- [Predictive modelling of rare in-flight medical events — NASA NTRS](https://ntrs.nasa.gov/api/citations/20110008743/downloads/20110008743.pdf)
- [Managing Risks to Astronaut Health — Safe Passage (NCBI Bookshelf)](https://www.ncbi.nlm.nih.gov/books/NBK223777/)
- [Infections in long-duration space missions — ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2666524724000983)
- [Congestion and Sinonasal Illness in Outer Space: A Study on the ISS — PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12322577/)
- [What the first medical evacuation from the ISS tells us about healthcare in space — The Conversation](https://theconversation.com/what-the-first-medical-evacuation-from-the-international-space-station-tells-us-about-healthcare-in-space-273728)
