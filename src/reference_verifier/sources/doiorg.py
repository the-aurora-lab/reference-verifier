"""doi.org content negotiation: resolves DOIs from every registration agency (Crossref, DataCite, mEDRA...)."""

from __future__ import annotations

from urllib.parse import quote

from ..http import Http
from ..model import Record

_CSL = {"Accept": "application/vnd.citationstyles.csl+json"}


def _first(v) -> str:
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def by_doi(http: Http, doi: str) -> tuple[Record | None, bool | None]:
    r = http.get(f"https://doi.org/{quote(doi, safe='/')}", headers=_CSL)
    if r.status == 404:
        return None, False  # not registered with any agency
    if r.status != 200:
        return None, None
    try:
        d = r.json()
    except ValueError:  # some agencies answer with HTML
        return None, None
    try:
        year = int(d["issued"]["date-parts"][0][0])
    except (KeyError, IndexError, TypeError, ValueError):
        year = None
    authors = [a.get("family") or a.get("literal") or a.get("name") or "" for a in d.get("author", [])]
    return (
        Record(
            source="doi.org",
            title=_first(d.get("title")),
            authors=[a for a in authors if a],
            year=year,
            venue=_first(d.get("container-title")),
            doi=(d.get("DOI") or doi).lower(),
            url=d.get("URL"),
            kind=str(d.get("type", "")),
            pages=str(d["page"]) if d.get("page") else None,
            volume=str(d["volume"]) if d.get("volume") else None,
            issue=str(d["issue"]) if d.get("issue") else None,
        ),
        True,
    )
