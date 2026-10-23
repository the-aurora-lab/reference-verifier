"""arXiv API: identifier lookups (batched) and title search. arXiv asks for one request every 3 s."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..http import Http
from ..match import normalize_title
from ..model import Record, Reference

API = "https://export.arxiv.org/api/query"
_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
_BATCH = 50


def _entries(xml_text: str) -> list[tuple[str, Record]]:
    out = []
    for e in ET.fromstring(xml_text).findall("a:entry", _NS):
        id_url = e.findtext("a:id", "", _NS)
        title = " ".join(e.findtext("a:title", "", _NS).split())
        if "/abs/" not in id_url or not title:
            continue  # error entries carry an api/errors id and no title
        aid = re.sub(r"v\d+$", "", id_url.rsplit("/abs/", 1)[1])
        published = e.findtext("a:published", "", _NS)[:4]
        doi = e.findtext("arxiv:doi", None, _NS)
        out.append(
            (
                aid,
                Record(
                    source="arXiv",
                    title=title,
                    authors=[" ".join(a.findtext("a:name", "", _NS).split()) for a in e.findall("a:author", _NS)],
                    year=int(published) if published.isdigit() else None,
                    venue="arXiv",
                    doi=doi.lower() if doi else None,
                    url=f"https://arxiv.org/abs/{aid}",
                    full_names=True,
                ),
            )
        )
    return out


def by_ids(http: Http, ids: list[str]) -> dict[str, Record] | None:
    """Look up many identifiers at once. Identifiers missing from the result do not exist."""
    found: dict[str, Record] = {}
    for i in range(0, len(ids), _BATCH):
        chunk = ids[i : i + _BATCH]
        r = http.get(API, params={"id_list": ",".join(chunk), "max_results": len(chunk)})
        if r.status != 200:
            return None
        found.update(_entries(r.text))
    return found


def search(http: Http, ref: Reference, results: int = 5) -> list[Record] | None:
    words = normalize_title(ref.title)
    if not words:
        return []
    r = http.get(API, params={"search_query": f'ti:"{words}"', "max_results": results})
    if r.status != 200:
        return None
    return [rec for _, rec in _entries(r.text)]
