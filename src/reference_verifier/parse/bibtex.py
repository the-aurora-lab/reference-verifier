"""Read BibTeX/BibLaTeX files into References."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.latexenc import latex_to_unicode

from ..model import Reference

# Old SICI-style DOIs contain angle brackets: 10.1175/1520-0469(1963)020<0130:DNF>2.0.CO;2
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"{}]+", re.IGNORECASE)
_ARXIV_NEW = re.compile(r"(?<![\d.])(\d{4}\.\d{4,5})(?:v\d+)?(?!\d)")
_ARXIV_OLD = re.compile(r"\b([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?\b")
_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$")


def clean(s: str) -> str:
    try:
        s = latex_to_unicode(s)
    except Exception:  # malformed LaTeX: fall back to the raw text
        pass
    return " ".join(s.replace("{", "").replace("}", "").replace("~", " ").split())


def split_names(field: str) -> tuple[list[str], bool]:
    """Split an author field on ' and ' outside braces. Returns (names, has_et_al)."""
    names, depth, start, i = [], 0, 0, 0
    lower = field.lower()
    while i < len(field):
        c = field[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif depth == 0 and lower.startswith(" and ", i):
            names.append(field[start:i])
            i += 5
            start = i
            continue
        i += 1
    names.append(field[start:])
    names = [" ".join(n.split()) for n in names if n.strip()]
    et_al = any(n.lower() == "others" for n in names)
    return [n for n in names if n.lower() != "others"], et_al


def family_name(name: str) -> str:
    """'Last, First' or 'First von Last' -> the family part, as written."""
    depth = 0
    for i, c in enumerate(name):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "," and depth == 0:
            return clean(name[:i])
    tokens, depth, cur = [], 0, ""
    for c in name:  # whitespace split outside braces, so {World Health Organization} stays whole
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        if c.isspace() and depth == 0:
            if cur:
                tokens.append(cur)
            cur = ""
        else:
            cur += c
    if cur:
        tokens.append(cur)
    return clean(tokens[-1]) if tokens else ""


def normalize_doi(s: str | None) -> str | None:
    if not s:
        return None
    m = DOI_RE.search(unquote(s))
    return m.group(0).rstrip(".,;)]").lower() if m else None


def find_arxiv_id(e: dict, doi: str | None) -> str | None:
    if doi:
        m = _ARXIV_DOI.match(doi)
        if m:
            return m.group(1)
    prefix = e.get("archiveprefix", e.get("eprinttype", "arxiv")).lower()
    # The eprint field counts on its own; other fields only when they mention arXiv.
    candidates = [(e.get("eprint", ""), prefix == "arxiv")]
    candidates += [(e.get(f, ""), False) for f in ("journal", "note", "url", "howpublished", "volume", "booktitle", "publisher")]
    for text, trusted in candidates:
        if not text or not (trusted or "arxiv" in text.lower()):
            continue
        m = _ARXIV_NEW.search(text) or _ARXIV_OLD.search(text)
        if m:
            return m.group(1)
    return None


def to_reference(e: dict, source_file: str = "") -> Reference:
    names, _ = split_names(e.get("author") or e.get("editor") or "")
    doi = normalize_doi(e.get("doi")) or (normalize_doi(e.get("url")) if "doi.org" in e.get("url", "") else None)
    year = re.search(r"\d{4}", e.get("year") or e.get("date") or "")
    venue = next((e[f] for f in ("journal", "journaltitle", "booktitle", "publisher", "howpublished", "school", "institution") if e.get(f)), "")
    pmid = re.sub(r"\D", "", e.get("pmid", "")) or None
    return Reference(
        key=e.get("ID", ""),
        entry_type=e.get("ENTRYTYPE", "misc").lower(),
        title=clean(e.get("title", "")),
        authors=[f for f in (family_name(n) for n in names) if f],
        year=int(year.group(0)) if year else None,
        venue=clean(venue),
        doi=doi,
        arxiv_id=find_arxiv_id(e, doi),
        pmid=pmid,
        url=e.get("url") or None,
        source_file=source_file,
        fields={k: v for k, v in e.items() if k not in ("ID", "ENTRYTYPE")},
    )


def parse_bib(text: str, source_file: str = "") -> list[Reference]:
    parser = BibTexParser(common_strings=True, ignore_nonstandard_types=False, add_missing_from_crossref=True)
    db = bibtexparser.loads(text, parser=parser)
    return [to_reference(e, source_file) for e in db.entries]


def load_bib(path: str | Path) -> list[Reference]:
    p = Path(path)
    return parse_bib(p.read_text(encoding="utf-8", errors="replace"), source_file=str(p))
