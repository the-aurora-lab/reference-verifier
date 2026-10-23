"""Terminal and JSON output."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from . import __version__
from .model import Result, Status
from .sources import LABELS

LABEL = {
    Status.FOUND: "found",
    Status.NOT_FOUND: "NOT FOUND",
    Status.UNCERTAIN: "UNCERTAIN",
    Status.DOI_NOT_FOUND: "BAD DOI",
    Status.DOI_OTHER_WORK: "WRONG DOI",
    Status.SKIPPED: "skipped",
    Status.ERROR: "ERROR",
}
SUMMARY = [
    (Status.FOUND, "found"),
    (Status.NOT_FOUND, "not found"),
    (Status.DOI_OTHER_WORK, "wrong DOI"),
    (Status.DOI_NOT_FOUND, "unregistered DOI"),
    (Status.UNCERTAIN, "uncertain"),
    (Status.SKIPPED, "skipped"),
    (Status.ERROR, "could not check"),
]
_ORDER = {"high": 0, "medium": 1, "low": 2, "ok": 3}
_COLOR = {"high": "31", "medium": "33", "low": "36", "ok": "32"}


def use_color(stream=sys.stdout) -> bool:
    return stream.isatty() and "NO_COLOR" not in os.environ


def _paint(text: str, severity: str, color: bool) -> str:
    return f"\033[{_COLOR[severity]}m{text}\033[0m" if color else text


def _describe(r: Result) -> str:
    year = f" ({r.ref.year})" if r.ref.year else ""
    return (r.ref.title or r.ref.doi or r.ref.arxiv_id or "(no title)") + year


def render_text(results: list[Result], inputs: list[str], calls: dict[str, int], color: bool = False,
                show_all: bool = False, gave_up: list[str] | None = None) -> str:
    counts = {st: sum(r.status is st for r in results) for st, _ in SUMMARY}
    lines = [f"Reference Verifier {__version__}: {len(results)} references from {', '.join(inputs)}", ""]
    lines.append("  " + " · ".join(f"{counts[st]} {name}" for st, name in SUMMARY if counts[st] or st is Status.FOUND))
    lines.append("")
    shown = sorted(
        (r for r in results if show_all or r.severity != "ok"),
        key=lambda r: (_ORDER[r.severity], r.ref.key),
    )
    width = max((len(r.ref.key) for r in shown), default=0)
    for r in shown:
        tag = _paint(f"{LABEL[r.status]:<10}", r.severity, color)
        lines.append(f"  {tag} {r.ref.key:<{width}}  {_describe(r)}")
        detail = r.note or (f'matched "{r.match.title}" in {r.match.source}' if r.match else "")
        if detail:
            lines.append(f"  {'':<10} {'':<{width}}  {detail}")
    if shown:
        lines.append("")
    if any(r.status is Status.NOT_FOUND for r in results):
        lines.append("  Not found means no registry lists a matching work. Check those entries by hand before")
        lines.append("  changing anything: books, theses, reports and very new papers are often missing.")
    if gave_up:
        names = ", ".join(LABELS.get(g, g) for g in gave_up)
        lines.append(f"  {names} stopped answering during this run and was skipped; rerun later to include it.")
    if calls:
        lines.append("  Requests: " + ", ".join(f"{host} {n}" for host, n in sorted(calls.items())) + " (repeat runs use the local cache)")
    else:
        lines.append("  All answers came from the local cache.")
    return "\n".join(lines)


def _record(rec) -> dict | None:
    if rec is None:
        return None
    return {"source": rec.source, "title": rec.title, "authors": rec.authors, "year": rec.year,
            "venue": rec.venue, "doi": rec.doi, "url": rec.url}


def to_json(results: list[Result], inputs: list[str]) -> dict:
    return {
        "tool": "reference-verifier",
        "version": __version__,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": inputs,
        "summary": {st.value: sum(r.status is st for r in results) for st, _ in SUMMARY},
        "results": [
            {
                "key": r.ref.key,
                "entry_type": r.ref.entry_type,
                "status": r.status.value,
                "severity": r.severity,
                "title": r.ref.title,
                "year": r.ref.year,
                "doi": r.ref.doi,
                "arxiv_id": r.ref.arxiv_id,
                "note": r.note,
                "match": _record(r.match),
                "doi_record": _record(r.doi_record),
                "scores": None if r.score is None else {
                    "title": round(r.score.title, 3),
                    "authors_ok": r.score.authors_ok,
                    "first_author": r.score.first_author,
                    "author_overlap": None if r.score.author_overlap is None else round(r.score.author_overlap, 3),
                    "year_delta": r.score.year_delta,
                },
                "sources_tried": r.sources_tried,
                "source_file": r.ref.source_file,
            }
            for r in results
        ],
    }
