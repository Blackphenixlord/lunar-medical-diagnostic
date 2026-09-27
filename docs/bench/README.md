# Benchmark results

Dated, unedited output of `python -m vitals bench`. Each file is one full run of the
33-prompt bank in `prompts/complaints.yaml`. Keep these - they are the evidence for PDR.

| date | model | machine | named correctly | said "nothing fits" | missed escalations |
|---|---|---|---|---|---|
| 2026-09-26 | llama3.2 (3B) | Joshua's PC | 19/26 (73%) | 1/7 | 3 |
| 2026-09-26 | llama3.2 (3B), after fixes | Joshua's PC | 19/26 (73%) | 1/7 | **0** |
| 2026-09-26 | llama3.1:8b, after fixes | Joshua's PC | 22/26 (85%) | 0/7 | **0** |

"After fixes" = commit 18220ca: engine escalation backstop + phrasebook for DCS, dental and
wounds. The backstop is why missed escalations went to 0 while the hit rate did not move -
the model still picks the wrong name sometimes, but the alarm now fires anyway.

Weakest area on every model: saying "nothing in the knowledge base fits". Both models almost
always guess a condition, even for nonsense, burns, radiation and psych complaints.