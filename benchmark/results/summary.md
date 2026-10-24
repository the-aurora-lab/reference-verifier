# Benchmark results: refverify 0.1.0 (existence check)

342 labelled references (benchmark.jsonl); registries unavailable during the run: dblp.

These are development-set numbers: the matching rules were adjusted after looking at misses on these
items. Publish only scores from a held-out set the rules have not seen.

| Measure | Result |
|---|---|
| Real references found | 139/140 (99.3%, 95% CI 96.1–99.9%) |
| Fabricated references flagged | 81/81 (100.0%, 95% CI 95.5–100.0%) |
| Wrong DOIs flagged as a DOI problem | 36/36 (100.0%, 95% CI 90.4–100.0%) |
| Retracted papers found (they exist) | 45/45 (100.0%, 95% CI 92.1–100.0%) |
| Precision of flags (fabricated + wrong DOI vs real + retracted) | 117/117 (100.0%, 95% CI 96.8–100.0%) |
| Recall of flags | 117/117 (100.0%, 95% CI 96.8–100.0%) |

## Status by label

| Label | found | not_found | uncertain | doi_not_found | doi_other_work | skipped | error |
|---|---|---|---|---|---|---|---|
| real | 139 | 0 | 1 | 0 | 0 | 0 | 0 |
| fabricated | 0 | 76 | 0 | 2 | 3 | 0 | 0 |
| wrong_doi | 0 | 0 | 0 | 0 | 36 | 0 | 0 |
| metadata_error | 28 | 7 | 5 | 0 | 0 | 0 | 0 |
| retracted | 45 | 0 | 0 | 0 | 0 | 0 | 0 |
