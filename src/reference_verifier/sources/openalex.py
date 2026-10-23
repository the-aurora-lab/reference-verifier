"""OpenAlex title search. Searches draw on the caller's daily budget ($0.001 each; a free key
gives $1/day, no key shares $0.10/day per network), so OpenAlex is the last source tried."""

from __future__ import annotations

import re

from ..http import Http
from ..model import Record, Reference

API = "https://api.openalex.org/works"
_SELECT = "id,doi,display_name,authorships,publication_year,primary_location"


def _record(w: dict) -> Record:
    source = (w.get("primary_location") or {}).get("source") or {}
    return Record(
        source="OpenAlex",
        title=w.get("display_name") or "",
        authors=[a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")],
        year=w.get("publication_year"),
        venue=source.get("display_name") or "",
        doi=(w.get("doi") or "").replace("https://doi.org/", "").lower() or None,
        url=w.get("id"),
        full_names=True,
    )


def search(http: Http, ref: Reference, api_key: str | None, results: int = 5) -> list[Record] | None:
    # Commas, colons and pipes are filter syntax in OpenAlex.
    title = " ".join(re.sub(r"[,:|!()\[\]{}]", " ", ref.title).split())
    if not title:
        return []
    params = {"filter": f"title.search:{title}", "per_page": results, "select": _SELECT}
    if api_key:
        params["api_key"] = api_key
    r = http.get(API, params=params, secret=("api_key",))
    if r.status != 200:
        return None
    return [_record(w) for w in r.json().get("results", [])]
