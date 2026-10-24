# Benchmark results: refverify 0.1.0 (existence check)

246 labelled references (heldout.jsonl); registries unavailable during the run: dblp.

Held-out set: built independently of the development set and scored once; the matching rules were
not changed after seeing these results.

| Measure | Result |
|---|---|
| Real references found | 93/95 (97.9%, 95% CI 92.6–99.4%) |
| Fabricated references flagged | 54/54 (100.0%, 95% CI 93.4–100.0%) |
| Wrong DOIs flagged as a DOI problem | 30/30 (100.0%, 95% CI 88.6–100.0%) |
| Retracted papers found (they exist) | 35/35 (100.0%, 95% CI 90.1–100.0%) |
| Precision of flags (fabricated + wrong DOI vs real + retracted) | 84/86 (97.7%, 95% CI 91.9–99.4%) |
| Recall of flags | 84/84 (100.0%, 95% CI 95.6–100.0%) |

## Status by label

| Label | found | not_found | uncertain | doi_not_found | doi_other_work | skipped | error |
|---|---|---|---|---|---|---|---|
| real | 93 | 2 | 0 | 0 | 0 | 0 | 0 |
| fabricated | 0 | 53 | 0 | 0 | 1 | 0 | 0 |
| wrong_doi | 0 | 0 | 0 | 0 | 30 | 0 | 0 |
| metadata_error | 23 | 5 | 4 | 0 | 0 | 0 | 0 |
| retracted | 35 | 0 | 0 | 0 | 0 | 0 | 0 |
