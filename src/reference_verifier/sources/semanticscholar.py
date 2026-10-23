"""Semantic Scholar title match. Used only with an API key: anonymous calls share a pool that is
usually rate-limited. It indexes reports and preprints the other registries miss (GPT-2, for one)."""

from __future__ import annotations

from ..http import Http
from ..model import Record, Reference

API = "https://api.semanticscholar.org/graph/v1/paper/search/match"
_FIELDS = "title,year,authors,venue,externalIds,url"


def match(http: Http, ref: Reference, api_key: str) -> list[Record] | None:
    if not ref.title:
        return []
    r = http.get(API, params={"query": ref.title, "fields": _FIELDS}, headers={"x-api-key": api_key})
    if r.status == 404:  # "Title match not found"
        return []
    if r.status != 200:
        return None
    out = []
    for p in r.json().get("data", []):
        doi = (p.get("externalIds") or {}).get("DOI")
        out.append(
            Record(
                source="Semantic Scholar",
                title=p.get("title") or "",
                authors=[a.get("name", "") for a in p.get("authors", [])],
                year=p.get("year"),
                venue=p.get("venue") or "",
                doi=doi.lower() if doi else None,
                url=p.get("url"),
                full_names=True,
            )
        )
    return out
