"""Crossref REST API: DOI lookups and bibliographic search (free, polite pool with mailto)."""

from __future__ import annotations

from urllib.parse import quote

from ..http import Http
from ..model import Record, Reference

API = "https://api.crossref.org/works"
_SELECT = "DOI,title,subtitle,author,issued,container-title,type,URL"


def _params(mailto: str | None) -> dict:
    return {"mailto": mailto} if mailto else {}


def _year(issued: dict | None) -> int | None:
    try:
        return int(issued["date-parts"][0][0])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _relations(item: dict) -> dict[str, list[str]]:
    """Crossref relations that point at other DOIs: {"is-preprint-of": ["10.1038/..."], ...}."""
    out: dict[str, list[str]] = {}
    for kind, targets in (item.get("relation") or {}).items():
        dois = [t["id"].lower() for t in targets if isinstance(t, dict) and t.get("id-type") == "doi" and t.get("id")]
        if dois:
            out[kind] = dois
    return out


def to_record(item: dict) -> Record:
    authors = [a.get("family") or a.get("name") or "" for a in item.get("author", [])]
    title = (item.get("title") or [""])[0]
    subtitle = (item.get("subtitle") or [""])[0]  # Crossref stores "BLEU" + "a method for ..." separately
    if subtitle and subtitle.lower() not in title.lower():
        title = f"{title}: {subtitle}"
    return Record(
        source="Crossref",
        title=title,
        authors=[a for a in authors if a],
        year=_year(item.get("issued")),
        venue=(item.get("container-title") or [""])[0],
        doi=(item.get("DOI") or "").lower() or None,
        url=item.get("URL"),
        kind=item.get("type", ""),
        pages=item.get("page") or None,
        volume=item.get("volume") or None,
        issue=item.get("issue") or None,
        relations=_relations(item),
    )


def by_doi(http: Http, doi: str, mailto: str | None) -> tuple[Record | None, bool | None]:
    r = http.get(f"{API}/{quote(doi, safe='/')}", params=_params(mailto))
    if r.status == 404:
        return None, False
    if r.status != 200:
        return None, None
    return to_record(r.json()["message"]), True


def search(http: Http, ref: Reference, mailto: str | None, rows: int = 5) -> list[Record] | None:
    query = " ".join(x for x in (ref.title, ref.authors[0] if ref.authors else "", str(ref.year or "")) if x)
    r = http.get(API, params={"query.bibliographic": query, "rows": rows, "select": _SELECT, **_params(mailto)})
    if r.status != 200:
        return None
    return [to_record(item) for item in r.json()["message"]["items"]]
