# Incidence data — real numbers for every condition in the knowledge base

Collected 27 Sep 2026. **Purpose:** the `prior` values in `kb/conditions/*.yaml` were invented.
This file lists published spaceflight numbers for each condition so the team can replace them
with sourced ones, and so we can say at PDR exactly where every number comes from.

**The model never sees these numbers.** They only affect the backup scoring engine (the
cross-check, and the escalation backstop added 26 Sep).

## The main source: NASA's Integrated Medical Model (IMM) baselines

NASA publishes a "Clinical Finding Form (CliFF) Baseline" per medical condition. Each one is
the incidence NASA's own Integrated Medical Model uses, with the arithmetic shown (for example
`419 / 588` crew for motion sickness). They are the most defensible numbers available to us:
NASA-built, flight-data-based, and each carries a level-of-evidence rating.
Posted at nasa.gov in Aug 2026; most are dated 2020.

Two kinds of number appear below — do not mix them up:
- **per flight** — "space adaptation" conditions that happen once, in the first days
  (motion sickness, back pain, congestion). The number is the fraction of crew affected.
- **per person-year** — conditions that can happen any time. For a ~6-month ISS mission the
  chance of at least one event is `1 - exp(-rate x 0.5)`, shown in the last column.

## The table

| Condition (KB id) | Current `prior` (invented) | Published number | Chance per ~6-month mission | Source |
|---|---|---|---|---|
| Space motion sickness (`space_motion_sickness`) | 0.35 | **71.3% of crew** (419/588) | 0.71 | NASA IMM baseline, 2020 [1]; NASA tech brief says ~73% [2] |
| Back pain, space adaptation (`msk_back_pain_adaptation`) | 0.40 | **48.8% of crew** (425/871); 97% mild-moderate | 0.49 | NASA IMM baseline, 2020 [3]; Kerstman study: 53% of 722 [4] |
| Nasal congestion, fluid shift (`sinonasal_congestion`) | 0.45 | **56.8% of crew** (458/807); ISS-only study: 75% of 71 astronauts | 0.57 | NASA IMM baseline, 2020 [5]; Khan et al. 2025 [6] |
| Sleep disruption (`sleep_disruption_circadian`) | 0.50 | **47.2% insomnia** (381/807); **75% of ISS crew used sleep medication**, avg ~6.1 h sleep | 0.47 | NASA IMM baseline, 2020 [7]; Barger et al., Lancet Neurology 2014 [8] |
| CO2 headache (`tension_headache_co2`) | 0.25 | **1.52 events per person-year** (69/45.49); odds double per +1 mmHg CO2 | 0.53 | NASA IMM baseline, 2020 [9]; Law et al. 2014 [10] |
| Headache, early flight (context for the above) | — | **34.8% of crew** in first 5 days (IMM); **92% (22/24)** in a 2024 diary study | — | NASA IMM baseline [11]; Van Oosterhout et al., Neurology 2024 [12] |
| Upper respiratory infection (`urti`) | 0.10 | **0.97 upper-respiratory events per flight-year** (46 ISS crew, 20.6 flight-years) | 0.38 | Crucian et al. 2016 [13] |
| SANS (`sans`) | 0.30 | **81% of NASA astronauts (52/64)** had at least one ocular finding | 0.81 (any finding) | Expert consensus, Eye 2026 [14] |
| Orthostatic intolerance (`orthostatic_intolerance`) | 0.20 | **20–30% after short flights; 66–83% after long flights** (on landing day) | 0.66–0.83 after landing | NASA HRP evidence report [15] |
| Shoulder injury (`msk_shoulder_overuse`) | 0.08 | **0.79 sprain/strain events per person-year** in flight (35/44.58) | 0.32 | NASA IMM baseline, 2020 [16] — see note A |
| Laceration (`wound_laceration`) | 0.06 | **0.13 per person-year** (6/45.49) — an older study counted 1.06 | 0.064 | NASA IMM baseline, 2020 [17] — see note B |
| Dental emergency (`dental_emergency`) | 0.08 | **abscess 0.0082 + caries 0.0094 per person-year** | ~0.009 | NASA IMM baselines, 2016 [18][19] — see note C |
| Kidney stone (`renal_stone`) | 0.04 | **0.0040 per person-year**; 0 of 14 US astronaut stone events happened in flight | 0.002 | NASA IMM baseline, 2020 [20]; npj Microgravity 2022 [21] |
| Decompression sickness (`decompression_sickness`) | 0.01 | **~0.8% per EVA** (Bayesian estimate from 0 cases in 247 EVAs) | per EVA, not per mission | NASA IMM baseline, 2020 [22]; HRP DCS report [23] |
| Jugular vein clot (`jugular_vte`) | 0.005 | **1 occlusive + 1 partial clot in 11 ISS crew**; 6/11 had stagnant or reverse flow | small study — see note D | Marshall-Goebel et al., JAMA Netw Open 2019 [24] |

## What this changes

**Invented priors that are far off** (by more than 2x):

- Motion sickness 0.35 → ~0.71, too low
- CO2 headache 0.25 → ~0.53, too low
- Respiratory infection 0.10 → ~0.38, too low
- SANS 0.30 → up to 0.81, too low
- Shoulder injury 0.08 → ~0.32, too low (see note A)
- Dental 0.08 → ~0.01, **8x too high**
- Kidney stone 0.04 → ~0.002, **20x too high**

**Invented priors that land close:** back pain, congestion, sleep, laceration, decompression
sickness.

**Note A — shoulder.** The IMM number counts *in-flight* sprains and strains from any cause.
NASA's shoulder tech brief says EVA-*training* shoulder injuries happen on the ground (64% of 22
astronauts surveyed in 2002 had shoulder pain from suit training) and reports no in-flight
EVA-training shoulder injuries. Our rule is about overuse; decide which number fits it. [25]

**Note B — laceration.** IMM counts 6 events with a strict definition; Scheuring 2009 counted 28
over 26.45 person-years. IMM itself says incomplete records push its number down.

**Note C — dental. Our KB and prompt bank currently say caries is "0.39 per person-year".**
That figure is quoted correctly from a 2012 NASA review (Menon) [26], but NASA's own newer 2016
IMM baseline puts caries at 0.0094 — about 40x lower. Use the 2016 number. Dental abscess is
still, per NASA, the medical condition most likely to force an ISS evacuation [26].

**Note D — jugular clot.** 2/11 is one small study, found by ultrasound surveillance, most with
no symptoms. It says clots are far more common than 0.5%, but not how often they cause
*symptoms*. Treat as "rare to uncommon, dangerous", not a precise rate.

**What these numbers are not.** A `prior` in the engine means "how likely is this, before
hearing the complaint". An incidence is "how often does it happen to a crewmember". They are
close but not identical: the engine only runs when someone is already complaining, and
adaptation conditions only apply in the first days of flight (the rules already handle that
with `mission_elapsed_days`). Changing priors will shift the engine's ranking — re-run
`pytest` and `vitals bench` after any change, and have Joaquin sign off.

## General conditions added 2 Oct 2026

Twelve rules added from NASA IMM baselines so VITALS covers ordinary medicine, not only
space-adaptation conditions. Their `prior` values follow the same calibrated range as the rest
of the KB (not yet switched to IMM numbers, same as above); the IMM figure is written in a
comment at the top of each file. Rare emergencies are floored at 0.003-0.005 so the backup
engine can still surface them - a missed heart attack costs more than a false alarm.

| Condition (KB id) | `prior` used | Published number | Source |
|---|---|---|---|
| Eye foreign body / abrasion (`eye_foreign_body`) | 0.15 | **2.33 per person-year** in flight (106/45.49); foreign bodies 88.5% | IMM 2020 [28] |
| Skin rash (`skin_rash`) | 0.15 | **2.64 per person-year** in flight (120/45.49); ISS ~25x terrestrial | IMM 2020 [29]; Crucian 2016 [13] |
| Urinary tract infection (`urinary_tract_infection`) | 0.05 | **0.264 per person-year** (12/45.49); female 0.856, male 0.134 | IMM 2020 [30] |
| Diarrhea (`diarrhea_gastroenteritis`) | 0.08 | **0.88 per person-year** in flight (40/45.49) | IMM 2020 [31] |
| Constipation, space adaptation (`constipation_adaptation`) | 0.12 | **18.7% of crew** (151/807), first 5 days | IMM 2020 [32] |
| Appendicitis (`appendicitis`) | 0.005 (floored) | **0.000934 per person-year** (Bayesian; no in-flight case) | IMM 2020 [33] |
| Allergic reaction, mild-moderate (`allergic_reaction`) | 0.08 | **0.57 per person-year** in flight (26/45.49); most often a medicine | IMM 2020 [27] |
| Anaphylaxis (`anaphylaxis`) | 0.003 (floored) | **0.000491 per person-year** (terrestrial, age 40-49) | IMM 2020 [34] |
| Heart attack / angina (`acute_coronary_syndrome`) | 0.003 (floored) | **0.00063 male, 0.00047 female per person-year**; none in flight | IMM 2020 [35] |
| Head injury (`head_injury`) | 0.005 (floored) | **0.00042 per person-year** (terrestrial trauma data) | IMM 2020 [36] |
| Burn (`burn`) | 0.01 | **0.00504 per person-year** from fire; small contact burns not counted | IMM 2020 [37] |
| Toxic / smoke inhalation (`toxic_inhalation`) | 0.02 | **0.354 toxic events per year**; smoke **0.018 per person-year** | IMM 2023 [38]; IMM 2020 [39] |

## Still missing

Deliberately left out: behavioural health (anxiety, depression - a scoring engine is the wrong
tool) and radiation (dosimetry, not a symptom). Next candidates with NASA baselines: eye
infection / corneal ulcer, chest injury, abdominal injury, atrial fibrillation, hypertension,
nosebleed, sprains of the wrist, ankle and knee, and a chest-wall strain rule (the prompt bank
has a mimic for it that currently, correctly, returns nothing).

## Sources

1. NASA, Space Motion Sickness (space adaptation) CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/space-motion-sickness-space-adaptation-cliff.pdf
2. NASA-STD-3001 Technical Brief, Space Adaptation Sickness, 2025 — https://www.nasa.gov/wp-content/uploads/2025/09/ochmo-mtb-004-space-adaptation-sickness-sas.pdf
3. NASA, Back Pain (space adaptation) CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/back-pain-space-adaptation-cliff.pdf
4. Kerstman et al., Space Adaptation Back Pain: A Retrospective Study — https://ntrs.nasa.gov/citations/20080045877
5. NASA, Nasal Congestion (space adaptation) CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/nasal-congestion-space-adaptation-cliff.pdf
6. Khan et al., Congestion and Sinonasal Illness in Outer Space, Laryngoscope Investig Otolaryngol 2025 — https://onlinelibrary.wiley.com/doi/10.1002/lio2.70229
7. NASA, Insomnia (space adaptation) CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/insomnia-space-adaptation-cliff.pdf
8. Barger et al., Lancet Neurology 2014 (summary) — https://www.sciencedaily.com/releases/2014/08/140807215803.htm
9. NASA, Headache (CO2 induced) CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/headache-co2-induced-cliff.pdf
10. Law et al., J Occup Environ Med 2014 (summary) — https://www.sciencedaily.com/releases/2014/05/140501100922.htm
11. NASA, Headache (space adaptation) CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/headache-space-adaptation-cliff.pdf
12. Van Oosterhout et al., Neurology 2024 — https://pmc.ncbi.nlm.nih.gov/articles/PMC11033988
13. Crucian et al., Incidence of clinical symptoms during long-duration orbital spaceflight, IJGM 2016 — https://www.dovepress.com/incidence-of-clinical-symptoms-during-long-duration-orbital-spacefligh-peer-reviewed-fulltext-article-IJGM
14. SANS expert consensus, Eye 2026 — https://www.nature.com/articles/s41433-026-04651-6
15. NASA HRP Evidence Report, Risk of Orthostatic Intolerance — https://ntrs.nasa.gov/api/citations/20150007319/downloads/20150007319.pdf
16. NASA, Shoulder Sprain/Strain CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/shoulder-sprain-strain-cliff.pdf
17. NASA, Skin Laceration CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/skin-laceration-cliff.pdf
18. NASA, Dental Abscess CliFF Baseline, 2016 — https://www.nasa.gov/wp-content/uploads/2026/08/dental-abscess-cliff.pdf
19. NASA, Dental Caries CliFF Baseline, 2016 — https://www.nasa.gov/wp-content/uploads/2026/08/dental-caries-cliff.pdf
20. NASA, Nephrolithiasis CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/nephrolithiasis-cliff.pdf
21. Numerical characterization of astronaut CaOx renal stone incidence rates, npj Microgravity 2022 — https://www.nature.com/articles/s41526-021-00187-z
22. NASA, Decompression Sickness Secondary to EVA CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/decompression-sickness-secondary-to-extravehicular-activity-cliff.pdf
23. NASA HRP Evidence Report, Risk of Decompression Sickness — https://ntrs.nasa.gov/api/citations/20140003729/downloads/20140003729.pdf
24. Marshall-Goebel et al., JAMA Network Open 2019 — https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2755307
25. NASA-STD-3001 Technical Brief, Shoulder Injury, 2025 — https://www.nasa.gov/wp-content/uploads/2025/09/ochmo-mtb-006-shoulder-injury.pdf
26. Menon, Review of Spaceflight Dental Emergencies, NASA/TM-2012-217368 — https://humanresearchroadmap.nasa.gov/gaps/closureDocumentation/2-Menon-A_TM-2012-217368.pdf
27. NASA, Allergic Reaction (mild to moderate) CliFF Baseline — https://www.nasa.gov/wp-content/uploads/2026/08/allergic-reaction-mild-to-moderate-cliff.pdf
28. NASA, Eye Irritation/Abrasion CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/eye-irritation-abrasion-cliff.pdf
29. NASA, Skin Rash CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/skin-rash-cliff.pdf
30. NASA, Urinary Tract Infection CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/urinary-tract-infection-cliff.pdf
31. NASA, Diarrhea CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/diarrhea-cliff.pdf
32. NASA, Constipation (space adaptation) CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/constipation-space-adaptation-cliff.pdf
33. NASA, Appendicitis CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/appendicitis-cliff.pdf
34. NASA, Anaphylaxis CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/anaphylaxis-cliff.pdf
35. NASA, Angina/Myocardial Infarction CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/angina-myocardial-infarction-cliff.pdf
36. NASA, Head Injury CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/head-injury-cliff.pdf
37. NASA, Burns secondary to Fire CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/burns-secondary-to-fire-cliff.pdf
38. NASA, Toxic Inhalation Exposure CliFF Baseline, 2023 — https://www.nasa.gov/wp-content/uploads/2026/08/toxic-inhalation-exposure-cliff-2023.pdf
39. NASA, Smoke Inhalation CliFF Baseline, 2020 — https://www.nasa.gov/wp-content/uploads/2026/08/smoke-inhalation-cliff.pdf
