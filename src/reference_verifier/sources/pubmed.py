"""PubMed E-utilities: PMID lookups."""

from __future__ import annotations

import re

from ..http import Http
from ..model import Record

API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def _family(name: str) -> str:
    # PubMed writes "Smith JA" / "van der Berg J": drop the trailing initials.
    parts = name.rsplit(" ", 1)
    return parts[0] if len(parts) == 2 and re.fullmatch(r"[A-Z]{1,4}", parts[1]) else name


def by_pmid(http: Http, pmid: str, mailto: str | None) -> tuple[Record | None, bool | None]:
    params = {"db": "pubmed", "id": pmid, "retmode": "json", "tool": "reference-verifier"}
    if mailto:
        params["email"] = mailto
    r = http.get(API, params=params)
    if r.status != 200:
        return None, None
    d = r.json().get("result", {}).get(pmid)
    if not d or "error" in d:
        return None, False
    doi = next((a["value"] for a in d.get("articleids", []) if a.get("idtype") == "doi"), None)
    year = d.get("pubdate", "")[:4]
    return (
        Record(
            source="PubMed",
            title=d.get("title", "").rstrip("."),
            authors=[_family(a["name"]) for a in d.get("authors", []) if a.get("authtype") == "Author"],
            year=int(year) if year.isdigit() else None,
            venue=d.get("fulljournalname", ""),
            doi=doi.lower() if doi else None,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            pages=d.get("pages") or None,
            volume=d.get("volume") or None,
            issue=d.get("issue") or None,
        ),
        True,
    )
