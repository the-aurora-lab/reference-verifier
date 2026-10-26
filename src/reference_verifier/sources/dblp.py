"""DBLP publication search: computer science conference papers, many of them without DOIs."""

from __future__ import annotations

import re

from ..http import Http
from ..match import normalize_title
from ..model import Record, Reference

API = "https://dblp.org/search/publ/api"


def _record(info: dict) -> Record:
    authors = info.get("authors", {}).get("author", [])
    if isinstance(authors, dict):
        authors = [authors]
    venue = info.get("venue", "")
    year = info.get("year", "")
    return Record(
        source="DBLP",
        title=info.get("title", "").rstrip("."),
        # DBLP disambiguates homonyms with a suffix: "Wei Wang 0010".
        authors=[re.sub(r"\s+\d{4}$", "", a.get("text", "")) for a in authors],
        year=int(year) if str(year).isdigit() else None,
        venue=", ".join(venue) if isinstance(venue, list) else venue,
        doi=(info.get("doi") or "").lower() or None,
        url=info.get("ee") or info.get("url"),
        full_names=True,
        pages=info.get("pages") or None,
        volume=info.get("volume") or None,
        issue=info.get("number") or None,
    )


def search(http: Http, ref: Reference, hits: int = 5) -> list[Record] | None:
    r = http.get(API, params={"q": normalize_title(ref.title), "format": "json", "h": hits})
    if r.status != 200:
        return None
    found = r.json().get("result", {}).get("hits", {}).get("hit", []) or []
    return [_record(h.get("info", {})) for h in found]
