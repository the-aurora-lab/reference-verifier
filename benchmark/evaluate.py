"""Score refverify's existence check on the labelled benchmark.

    python benchmark/evaluate.py [--out benchmark/results]

What the free check is expected to do with each label:
  real            found (anything else is a false alarm)
  fabricated      flagged: not found, unregistered DOI or a DOI of another work
  wrong_doi       flagged as a DOI problem
  retracted       found (the work exists; retraction flags are not part of the existence check)
  metadata_error  reported separately: the work exists, so "found" is correct for an existence check,
                  while "uncertain" (e.g. different authors) is a useful hint
Precision counts a flag on a real or retracted reference as a false positive.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

from reference_verifier import __version__
from reference_verifier.check import check_all
from reference_verifier.http import Cache, Http, default_cache_path
from reference_verifier.model import Status
from reference_verifier.parse import parse_bib
from reference_verifier.sources import Sources

HERE = Path(__file__).resolve().parent
FLAGS = {Status.NOT_FOUND, Status.DOI_NOT_FOUND, Status.DOI_OTHER_WORK}
DOI_FLAGS = {Status.DOI_NOT_FOUND, Status.DOI_OTHER_WORK}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=HERE / "data" / "benchmark.jsonl")
    ap.add_argument("--out", type=Path, default=HERE / "results")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    items = [json.loads(line) for line in args.data.read_text(encoding="utf-8").splitlines() if line.strip()]
    refs, labels = [], []
    for it in items:
        parsed = parse_bib(it["bibtex"], source_file=it["id"])
        if len(parsed) != 1:
            print(f"{it['id']}: expected one BibTeX entry, got {len(parsed)}", file=sys.stderr)
            return 2
        refs.append(parsed[0])
        labels.append(it)

    mailto = os.environ.get("REFVERIFY_MAILTO")
    http = Http(mailto=mailto, cache=Cache(default_cache_path()))
    src = Sources(http, mailto=mailto, openalex_key=os.environ.get("OPENALEX_API_KEY"),
                  s2_key=os.environ.get("S2_API_KEY"))

    def progress(done: int, total: int) -> None:
        if done % 25 == 0 or done == total:
            print(f"  {done}/{total}", file=sys.stderr, flush=True)

    results = check_all(refs, src, workers=args.workers, progress=progress)
    http.close()

    by_label: dict[str, Counter] = defaultdict(Counter)
    rows = []
    for it, r in zip(labels, results):
        by_label[it["label"]][r.status.value] += 1
        rows.append({"id": it["id"], "label": it["label"], "field": it["field"], "status": r.status.value,
                     "severity": r.severity, "note": r.note, "match": r.match.title if r.match else None})

    def count(label: str, statuses: set[Status]) -> tuple[int, int]:
        c = by_label[label]
        return sum(c[s.value] for s in statuses), sum(c.values())

    tp = sum(count(l, FLAGS)[0] for l in ("fabricated", "wrong_doi"))
    fp = sum(count(l, FLAGS)[0] for l in ("real", "retracted"))
    pos = sum(count(l, FLAGS)[1] for l in ("fabricated", "wrong_doi"))
    found_real, n_real = count("real", {Status.FOUND})
    flagged_fab, n_fab = count("fabricated", FLAGS)
    doi_hit, n_doi = count("wrong_doi", DOI_FLAGS)
    found_retr, n_retr = count("retracted", {Status.FOUND})

    def pct(a: int, b: int) -> str:
        return f"{a}/{b} ({100 * a / b:.1f}%)" if b else "n/a"

    lines = [
        f"# Benchmark results: refverify {__version__} (existence check)",
        "",
        f"{len(items)} labelled references; registries unavailable during the run: "
        f"{', '.join(sorted(src.unavailable)) or 'none'}.",
        "",
        "These are development-set numbers: the matching rules were adjusted after looking at misses on these",
        "items. Publish only scores from a held-out set the rules have not seen.",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Real references found | {pct(found_real, n_real)} |",
        f"| Fabricated references flagged | {pct(flagged_fab, n_fab)} |",
        f"| Wrong DOIs flagged as a DOI problem | {pct(doi_hit, n_doi)} |",
        f"| Retracted papers found (they exist) | {pct(found_retr, n_retr)} |",
        f"| Precision of flags (fabricated + wrong DOI vs real + retracted) | {pct(tp, tp + fp)} |",
        f"| Recall of flags | {pct(tp, pos)} |",
        "",
        "## Status by label",
        "",
        "| Label | " + " | ".join(s.value for s in Status) + " |",
        "|---|" + "---|" * len(Status),
    ]
    for label in ("real", "fabricated", "wrong_doi", "metadata_error", "retracted"):
        lines.append(f"| {label} | " + " | ".join(str(by_label[label][s.value]) for s in Status) + " |")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (args.out / "per_item.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
