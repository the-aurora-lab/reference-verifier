"""The registries a reference is checked against, in the order they are tried."""

from __future__ import annotations

import threading
import xml.etree.ElementTree as ET

import httpx

from ..http import Http, Offline
from ..model import Record, Reference
from . import arxiv, crossref, dblp, doiorg, openalex, pubmed, semanticscholar

# Crossref is free and fast; OpenAlex is fast and covers conference papers without DOIs (at a small
# budget cost per search); DBLP is free but asks for restraint; arXiv allows one request every 3 s.
SEARCH_ORDER = ("crossref", "openalex", "dblp", "semanticscholar", "arxiv")
LABELS = {"crossref": "Crossref", "openalex": "OpenAlex", "dblp": "DBLP", "semanticscholar": "Semantic Scholar",
          "arxiv": "arXiv"}
_MAX_FAILURES = 2  # a registry that fails this many times in a row is skipped for the rest of the run

# Anything a registry can throw at us: network trouble, offline cache misses, bad JSON or XML.
_FAILURES = (httpx.HTTPError, Offline, ValueError, KeyError, TypeError, ET.ParseError)


class Sources:
    def __init__(self, http: Http, mailto: str | None = None, openalex_key: str | None = None,
                 s2_key: str | None = None, search_order=SEARCH_ORDER):
        self.http = http
        self.mailto = mailto
        self.openalex_key = openalex_key
        self.s2_key = s2_key
        self.search_order = tuple(s for s in search_order if s != "semanticscholar" or s2_key)
        self.unavailable: set[str] = set()
        self._failures: dict[str, int] = {}
        self._lock = threading.Lock()
        self._arxiv: dict[str, Record] | None = None

    def doi(self, doi: str) -> tuple[Record | None, bool | None, list[str]]:
        """(record, resolved, sources tried). resolved is False only when doi.org says the DOI is unregistered."""
        try:
            rec, ok = crossref.by_doi(self.http, doi, self.mailto)
        except _FAILURES:
            rec, ok = None, None
        if ok:
            return rec, True, ["Crossref"]
        try:
            rec, ok = doiorg.by_doi(self.http, doi)
        except _FAILURES:
            rec, ok = None, None
        return rec, ok, ["Crossref", "doi.org"]

    def prefetch_arxiv(self, ids: list[str]) -> None:
        if not ids:
            return
        try:
            found = arxiv.by_ids(self.http, sorted(set(ids)))
        except _FAILURES:
            found = None
        with self._lock:
            self._arxiv = found

    def arxiv_id(self, aid: str) -> tuple[Record | None, bool | None]:
        with self._lock:
            cached = self._arxiv
        if cached is not None:
            rec = cached.get(aid)
            return rec, rec is not None
        try:
            found = arxiv.by_ids(self.http, [aid])
        except _FAILURES:
            return None, None
        if found is None:
            return None, None
        rec = found.get(aid)
        return rec, rec is not None

    def pmid(self, pmid: str) -> tuple[Record | None, bool | None]:
        try:
            return pubmed.by_pmid(self.http, pmid, self.mailto)
        except _FAILURES:
            return None, None

    def _search(self, name: str, ref: Reference) -> list[Record] | None:
        if name == "crossref":
            return crossref.search(self.http, ref, self.mailto)
        if name == "openalex":
            return openalex.search(self.http, ref, self.openalex_key)
        if name == "dblp":
            return dblp.search(self.http, ref)
        if name == "semanticscholar":
            return semanticscholar.match(self.http, ref, self.s2_key or "")
        if name == "arxiv":
            return arxiv.search(self.http, ref)
        raise ValueError(f"unknown source {name!r}")

    def search(self, name: str, ref: Reference) -> list[Record] | None:
        """Title search in one registry; None when it could not be reached (or was given up on)."""
        with self._lock:
            if name in self.unavailable:
                return None
        try:
            recs = self._search(name, ref)
        except _FAILURES:
            recs = None
        with self._lock:
            if recs is None:
                self._failures[name] = self._failures.get(name, 0) + 1
                if self._failures[name] >= _MAX_FAILURES:
                    self.unavailable.add(name)
            else:
                self._failures[name] = 0
        return recs
