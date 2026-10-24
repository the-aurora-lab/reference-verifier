#!/usr/bin/env python3
"""Build the Reference Verifier HELD-OUT test set: heldout.jsonl.

This set is independent of the development benchmark that the tool's matching rules were tuned on.
It is meant to be scored once. Standard library only. Every item comes from a cached input under raw/:

  raw/real.json             genuine references sampled at random (OpenAlex `sample=` by field, dblp, arXiv),
                            with the registry metadata they were built from and their messy-BibTeX styles
  raw/fabricated.json       hallucinated references from public compilations, with our existence checks
                            (Crossref, OpenAlex, arXiv, dblp) and a quoted-title web search
  raw/retracted.json        retracted papers from the Retraction Watch data that Crossref publishes
  raw/dev_fingerprints.json what the development set contains (DOIs, normalised titles, compilation rows,
                            CiteTracer submissions, Retraction Watch records, BibTeX keys), used to prove
                            that the two sets share nothing

The wrong_doi and metadata_error items are derived from the held-out real items with a fixed random seed
(different from the development seed), so the same inputs always give the same JSONL, byte for byte.

Usage
  python3 -I build_heldout.py                     rebuild heldout.jsonl offline and validate it
  python3 -I build_heldout.py --validate          validate the existing heldout.jsonl only
  python3 -I build_heldout.py --refresh           also re-fetch every real and retracted item from its
                                                  registry (Crossref, arXiv, dblp) and report any drift
  python3 -I build_heldout.py --check-fabricated  re-run the registry title searches for the fabricated items

Network calls are read-only and throttled per host (Crossref and OpenAlex at most 5 per second,
dblp SPARQL 1 per second, arXiv 1 per 3 seconds). OpenAlex is used only when OPENALEX_API_KEY is set.
"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SEED = 20261024  # the development set uses 20261023
MAILTO = "auroralab.skills@gmail.com"  # Crossref polite-pool mailto parameter only
USER_AGENT = "reference-verifier-heldout/1.0 (+https://github.com/the-aurora-lab/reference-verifier)"

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OUT = HERE / "heldout.jsonl"

LABELS = ("real", "fabricated", "wrong_doi", "metadata_error", "retracted")
FIELDS = ("cs", "biomed", "physics", "math", "social", "humanities", "other")
TARGETS = {"real": 80, "fabricated": 50, "wrong_doi": 25, "metadata_error": 25, "retracted": 25}
N_WRONG_DOI = 30
N_METADATA_ERROR = 32
PREFIX = {"real": "ho-real-", "fabricated": "ho-fab-", "wrong_doi": "ho-wdoi-", "metadata_error": "ho-meta-",
          "retracted": "ho-retr-"}

# Source registry: short name -> (url, licence). Item-level source_url points at the exact record.
SOURCES = {
    "crossref": ("https://api.crossref.org", "Crossref metadata: facts, no restrictions on reuse (CC0)"),
    "dblp": ("https://dblp.org", "CC0 1.0 (dblp data)"),
    "arxiv": ("https://arxiv.org", "CC0 1.0 (arXiv metadata)"),
    "openalex": ("https://openalex.org", "CC0 1.0 (OpenAlex data)"),
    "hallucitation-acl2026": (
        "https://aclanthology.org/2026.acl-long.2189/",
        "CC BY 4.0 (ACL Anthology); reference metadata only",
    ),
    "citetracer-iclr2026": (
        "https://huggingface.co/datasets/Afrostnova/Hallucinated_Citation",
        "MIT (dataset); quotes ICLR 2026 desk-reject comments on OpenReview, CC BY 4.0",
    ),
    "retraction-watch": (
        "https://gitlab.com/crossref/retraction-watch-data",
        "Retraction Watch data, made openly available by Crossref (no licence stated; facts only); "
        "bibliographic metadata from Crossref (CC0)",
    ),
}

# --------------------------------------------------------------------------------------------
# HTTP with per-host throttling
# --------------------------------------------------------------------------------------------

_MIN_INTERVAL = {
    "api.crossref.org": 0.2,
    "api.openalex.org": 0.2,
    "export.arxiv.org": 3.0,
    "sparql.dblp.org": 1.0,
}
_last_call: dict[str, float] = {}


def http_get(url: str, accept: str = "application/json", retries: int = 4, timeout: int = 60) -> bytes:
    host = urllib.parse.urlparse(url).netloc
    for attempt in range(retries + 1):
        wait = _MIN_INTERVAL.get(host, 1.0) - (time.monotonic() - _last_call.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                body = resp.read()
            if status == 202 and b"not a bot" in body[:2000]:
                raise RuntimeError(f"{host} returned a bot challenge; use the SPARQL endpoint instead")
            return body
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 ** attempt * 2)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries:
                time.sleep(2 ** attempt * 2)
                continue
            raise
    raise RuntimeError("unreachable")


def get_json(url: str) -> dict:
    return json.loads(http_get(url).decode("utf-8"))


# --------------------------------------------------------------------------------------------
# Text normalisation and similarity
# --------------------------------------------------------------------------------------------

_LATEX_ACCENT_RE = re.compile(r"\\([\"'`^~=.uvHckrbd])\s*\{?\s*\\?([A-Za-z])\s*\}?")
_LATEX_ACCENT_MAP = {'"': "\u0308", "'": "\u0301", "`": "\u0300", "^": "\u0302", "~": "\u0303",
                     "=": "\u0304", ".": "\u0307", "u": "\u0306", "v": "\u030c", "H": "\u030b",
                     "c": "\u0327", "k": "\u0328", "r": "\u030a", "b": "\u0331", "d": "\u0323"}
_LATEX_SYMBOLS = {r"\ss": "ss", r"\o": "o", r"\O": "O", r"\aa": "a", r"\AA": "A", r"\ae": "ae",
                  r"\AE": "AE", r"\oe": "oe", r"\OE": "OE", r"\l": "l", r"\L": "L", r"\i": "i"}


def delatex(s: str) -> str:
    """Turn common LaTeX markup into plain Unicode text."""
    s = _LATEX_ACCENT_RE.sub(lambda m: m.group(2) + _LATEX_ACCENT_MAP[m.group(1)], s)
    for k, v in _LATEX_SYMBOLS.items():
        s = re.sub(re.escape(k) + r"(?![A-Za-z])", v, s)
    s = re.sub(r"\\(textit|textbf|emph|mathrm|mathit|mathbf|text)\s*", "", s)
    s = re.sub(r"\\([&%$#_])", r"\1", s)
    s = s.replace("$", "").replace("{", "").replace("}", "").replace("~", " ")
    s = s.replace("--", "-")
    return unicodedata.normalize("NFC", s)


def norm(s: str) -> str:
    """Lower-case ASCII folding for comparisons."""
    s = delatex(html.unescape(s or ""))
    s = re.sub(r"<[^>]+>", " ", s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def title_sim(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def clean_markup(s: str) -> str:
    """Strip JATS/HTML tags and entities that registries put in titles."""
    s = html.unescape(s or "")
    s = re.sub(r"</?(i|b|em|strong|sup|sub|scp|u|span|mml:[a-z]+|jats:[a-z]+)[^>]*>", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return " ".join(s.split())


# --------------------------------------------------------------------------------------------
# Registry clients
# --------------------------------------------------------------------------------------------


def crossref_work(doi: str) -> dict:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}?mailto={MAILTO}"
    return get_json(url)["message"]


def crossref_search(query: str, rows: int = 5, filters: str = "") -> list[dict]:
    params = {"query.bibliographic": query, "rows": str(rows), "mailto": MAILTO,
              "select": "DOI,title,author,issued,container-title,type"}
    if filters:
        params["filter"] = filters
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    return get_json(url)["message"]["items"]


def openalex_search(title: str, rows: int = 5) -> list[dict]:
    """OpenAlex keyword search. Without OPENALEX_API_KEY the shared free budget is about 100 searches a day."""
    q = re.sub(r"[,:|!()\[\]]", " ", norm(title))
    params = {"search": q, "per-page": str(rows),
              "select": "id,doi,title,publication_year,authorships,primary_location,type"}
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    return get_json(url).get("results", [])


def _arxiv_parse(feed: bytes) -> list[dict]:
    import xml.etree.ElementTree as ET

    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(feed)
    out = []
    for e in root.findall("a:entry", ns):
        aid = (e.findtext("a:id", default="", namespaces=ns) or "").rsplit("/abs/", 1)[-1]
        title = " ".join((e.findtext("a:title", default="", namespaces=ns) or "").split())
        if not aid or title.lower() == "error":
            continue
        authors = [" ".join((a.findtext("a:name", default="", namespaces=ns) or "").split())
                   for a in e.findall("a:author", ns)]
        prim = e.find("arxiv:primary_category", ns)
        out.append({
            "id": re.sub(r"v\d+$", "", aid),
            "title": title,
            "authors": authors,
            "published": e.findtext("a:published", default="", namespaces=ns),
            "primary_category": prim.get("term") if prim is not None else "",
            "doi": e.findtext("arxiv:doi", default="", namespaces=ns) or "",
            "journal_ref": e.findtext("arxiv:journal_ref", default="", namespaces=ns) or "",
        })
    return out


def arxiv_by_id(aid: str) -> dict | None:
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": aid, "max_results": "1"})
    res = _arxiv_parse(http_get(url, accept="application/atom+xml"))
    return res[0] if res else None


def arxiv_search_title(title: str, rows: int = 5) -> list[dict]:
    """arXiv titles containing the five longest words of `title` (a loose query, ranked locally)."""
    words = sorted({w for w in norm(title).split() if len(w) > 3}, key=lambda w: (-len(w), w))[:5]
    if not words:
        return []
    q = " AND ".join(f"ti:{w}" for w in words)
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": q, "max_results": "25"})
    res = _arxiv_parse(http_get(url, accept="application/atom+xml"))
    res.sort(key=lambda r: -title_sim(title, r["title"]))
    return res[:rows]


def dblp_sparql(query: str) -> list[dict]:
    url = "https://sparql.dblp.org/sparql?" + urllib.parse.urlencode({"query": query})
    data = json.loads(http_get(url, accept="application/sparql-results+json", timeout=120))
    return [{k: v["value"] for k, v in b.items()} for b in data["results"]["bindings"]]


_DBLP_PREFIX = "PREFIX dblp: <https://dblp.org/rdf/schema#>\n"


def dblp_record(key: str) -> dict:
    """Metadata for one dblp record key, e.g. 'conf/nips/VaswaniSPUJGKP17'."""
    iri = f"<https://dblp.org/rec/{key}>"
    rows = dblp_sparql(_DBLP_PREFIX + f"""SELECT ?title ?year ?pages ?venue ?book ?booktitle ?doi ?page ?type ?volume ?issue WHERE {{
      {iri} dblp:title ?title ; dblp:yearOfPublication ?year ; dblp:bibtexType ?type .
      OPTIONAL {{ {iri} dblp:pagination ?pages }}
      OPTIONAL {{ {iri} dblp:publishedIn ?venue }}
      OPTIONAL {{ {iri} dblp:publishedAsPartOf ?book . ?book dblp:title ?booktitle }}
      OPTIONAL {{ {iri} dblp:doi ?doi }}
      OPTIONAL {{ {iri} dblp:primaryDocumentPage ?page }}
      OPTIONAL {{ {iri} dblp:publishedInJournalVolume ?volume }}
      OPTIONAL {{ {iri} dblp:publishedInJournalVolumeIssue ?issue }}
    }} LIMIT 5""")
    if not rows:
        raise KeyError(key)
    authors = dblp_sparql(_DBLP_PREFIX + f"""SELECT ?ord ?name WHERE {{
      {iri} dblp:hasSignature ?s . ?s dblp:signatureOrdinal ?ord ; dblp:signatureDblpName ?name .
    }} ORDER BY ?ord""")
    r = rows[0]
    names = [a["name"] for a in sorted(authors, key=lambda a: int(a["ord"]))]
    return {"title": r["title"], "year": int(r["year"]), "pages": r.get("pages", ""),
            "venue": r.get("venue", ""), "booktitle": r.get("booktitle", ""),
            "doi": r.get("doi", ""), "page": r.get("page", ""), "volume": r.get("volume", ""),
            "issue": r.get("issue", ""), "type": r["type"].rsplit("#", 1)[-1], "authors": names}


def _dblp_text_query(words: list[str], limit: int = 300) -> list[dict]:
    """dblp records whose title contains all `words` (QLever full-text index, fast)."""
    q = (_DBLP_PREFIX + "PREFIX ql: <http://qlever.cs.uni-freiburg.de/builtin-functions/>\n"
         f"SELECT ?p ?t WHERE {{ ?p dblp:title ?t . ?text ql:contains-entity ?t . "
         f'?text ql:contains-word "{" ".join(words)}" }} LIMIT {limit}')
    return dblp_sparql(q)


def dblp_title_search(title: str, limit: int = 5) -> list[dict]:
    """Best title matches among dblp records sharing the longest words of `title`."""
    words = sorted({w for w in norm(title).split() if len(w) > 3 and w.isalpha()}, key=lambda w: (-len(w), w))
    rows: list[dict] = []
    for k in (4, 3, 2):
        if len(words) < k and k != 2:
            continue
        rows += _dblp_text_query(words[:k])
        if len(rows) >= 3:
            break
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: -title_sim(title, r["t"])):
        if r["p"] in seen:
            continue
        seen.add(r["p"])
        out.append({"key": r["p"].replace("https://dblp.org/rec/", ""), "title": r["t"]})
    return out[:limit]


def dblp_exact_title(title: str) -> list[dict]:
    """dblp records whose title matches `title` up to case and punctuation."""
    words = [w for w in norm(title).split() if w.isalpha()]
    rows = _dblp_text_query(words, limit=100)
    return [{"key": r["p"].replace("https://dblp.org/rec/", ""), "title": r["t"]} for r in rows
            if norm(r["t"]) == norm(title)]


# --------------------------------------------------------------------------------------------
# Metadata extraction (registry record -> compact cached form)
# --------------------------------------------------------------------------------------------


def _split_name(full: str) -> dict:
    """'Ashish Vaswani' -> {'given': 'Ashish', 'family': 'Vaswani'}; dblp homonym digits removed."""
    full = re.sub(r"\s+\d{4}$", "", full.strip())
    parts = full.split()
    if len(parts) == 1:
        return {"family": parts[0], "given": ""}
    particles = {"van", "von", "de", "der", "den", "del", "della", "da", "di", "le", "la", "du", "dos", "ter"}
    i = len(parts) - 1
    while i > 1 and parts[i - 1].lower() in particles:
        i -= 1
    return {"given": " ".join(parts[:i]), "family": " ".join(parts[i:])}


def meta_from_crossref(m: dict) -> dict:
    ctype = m.get("type", "")
    issued = (m.get("issued") or {}).get("date-parts", [[None]])[0]
    year = issued[0] if issued and issued[0] else None
    authors = []
    for a in m.get("author", []) or []:
        if a.get("family"):
            authors.append({"given": clean_markup(a.get("given", "")), "family": clean_markup(a["family"])})
        elif a.get("name"):
            authors.append({"literal": clean_markup(a["name"])})
    editors = [{"given": clean_markup(a.get("given", "")), "family": clean_markup(a["family"])}
               for a in m.get("editor", []) or [] if a.get("family")]
    title = clean_markup((m.get("title") or [""])[0])
    subtitle = clean_markup((m.get("subtitle") or [""])[0]) if m.get("subtitle") else ""
    containers = [clean_markup(c) for c in m.get("container-title") or []]
    series = ""
    if len(containers) > 1 and ctype in ("book-chapter", "proceedings-article"):
        # e.g. ["Lecture Notes in Computer Science", "Medical Image Computing ... MICCAI 2015"]
        series, container = containers[0], containers[-1]
    else:
        container = containers[0] if containers else ""
    short = clean_markup((m.get("short-container-title") or [""])[0]) if m.get("short-container-title") else ""
    pages = m.get("page") or m.get("article-number") or ""
    out = {
        "registry": "crossref",
        "crossref_type": ctype,
        "title": title,
        "subtitle": subtitle,
        "authors": authors,
        "year": year,
        "container": container,
        "short_container": short,
        "volume": m.get("volume", ""),
        "number": m.get("issue", ""),
        "pages": pages,
        "publisher": m.get("publisher", ""),
        "doi": m.get("DOI", ""),
        "isbn": (m.get("ISBN") or [""])[0],
    }
    if series:
        out["series"] = series
    if editors:
        out["editors"] = editors
    return out


def meta_from_dblp(key: str, r: dict) -> dict:
    title = r["title"].rstrip(".")
    venue = r.get("booktitle") or r.get("venue", "")
    return {
        "registry": "dblp",
        "dblp_key": key,
        "dblp_type": r["type"],
        "title": title,
        "subtitle": "",
        "authors": [_split_name(n) for n in r["authors"]],
        "year": r["year"],
        "container": venue,
        "short_container": r.get("venue", ""),
        "volume": r.get("volume", ""),
        "number": r.get("issue", ""),
        "pages": r.get("pages", ""),
        "publisher": "",
        "doi": r.get("doi", "").replace("https://doi.org/", ""),
        "isbn": "",
        "url": r.get("page", ""),
    }


def meta_from_arxiv(r: dict) -> dict:
    return {
        "registry": "arxiv",
        "title": r["title"],
        "subtitle": "",
        "authors": [_split_name(n) for n in r["authors"]],
        "year": int(r["published"][:4]),
        "container": "",
        "short_container": "",
        "volume": "",
        "number": "",
        "pages": "",
        "publisher": "",
        "doi": "",
        "isbn": "",
        "arxiv": r["id"],
        "arxiv_class": r["primary_category"],
    }


# --------------------------------------------------------------------------------------------
# BibTeX writing
# --------------------------------------------------------------------------------------------

_TO_LATEX = {}
for _base, _chars in {
    '"': "äëïöüÿÄËÏÖÜŸ", "'": "áéíóúýćńśźÁÉÍÓÚÝĆŃŚŹ", "`": "àèìòùÀÈÌÒÙ", "^": "âêîôûÂÊÎÔÛ",
    "~": "ãõñÃÕÑ", "v": "šččžřěňďťŠČŽŘĚŇĎŤ", "H": "őűŐŰ", ".": "żŻ", "k": "ąęĄĘ", "u": "ăğĂĞ",
    "c": "çşţÇŞŢ",
}.items():
    for _ch in _chars:
        _plain = unicodedata.normalize("NFKD", _ch)[0]
        _TO_LATEX[_ch] = f"{{\\{_base}{_plain}}}" if _base in "\"'`^~.=" else f"{{\\{_base} {_plain}}}"
_TO_LATEX.update({"ß": r"{\ss}", "ø": r"{\o}", "Ø": r"{\O}", "å": r"{\aa}", "Å": r"{\AA}", "æ": r"{\ae}",
                  "Æ": r"{\AE}", "œ": r"{\oe}", "ł": r"{\l}", "Ł": r"{\L}", "ı": r"{\i}", "İ": r"{\.I}",
                  "Δ": r"$\Delta$", "α": r"$\alpha$", "β": r"$\beta$", "γ": r"$\gamma$", "κ": r"$\kappa$",
                  "μ": r"$\mu$", "τ": r"$\tau$", "−": "-", "–": "--", "—": "---"})


def to_latex(s: str) -> str:
    return "".join(_TO_LATEX.get(c, c) for c in s)


def escape_bib(s: str) -> str:
    """Escape characters that are special in BibTeX/LaTeX text (leaves $...$ math alone)."""
    s = s.replace("\\", "\\textbackslash{}") if "\\" in s and not re.search(r"\\[a-zA-Z{\"'`^~]", s) else s
    parts = re.split(r"(\$[^$]*\$)", s)
    return "".join(p if p.startswith("$") and p.endswith("$") and len(p) > 1
                   else re.sub(r"(?<!\\)([&%#_])", r"\\\1", p) for p in parts)


def protect_caps(title: str) -> str:
    """Brace words with inner capitals or digits-after-letters (BERT, ImageNet, GPT-4) as BibTeX users do."""
    def fix(m):
        w = m.group(0)
        parts = [p for p in w.split("-") if p]
        if any(re.search(r"[A-Z]{2}", p) or re.search(r"[a-z][A-Z]", p) for p in parts):
            return "{" + w + "}"
        return w
    return re.sub(r"(?<![{\\\w])[A-Za-z][\w\-]*", fix, title)


def initials(given: str) -> str:
    parts = re.split(r"(\s+|-)", given.strip())
    out = []
    for p in parts:
        if not p or p.isspace():
            out.append(" ")
        elif p == "-":
            out.append("-")
        else:
            letters = [c for c in p if c.isalpha()]
            if not letters:
                continue
            if len(p.rstrip(".")) <= 1 or (p.isupper() and len(p) <= 3 and "." not in p and len(given.split()) == 1 and len(p) > 1):
                out.append(". ".join(p.rstrip(".")) + ".")
            else:
                out.append(letters[0] + ".")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def format_person(a: dict, style: set[str]) -> str:
    if "literal" in a:
        return "{" + a["literal"] + "}"
    given, family = a.get("given", ""), a.get("family", "")
    if "initials" in style and given:
        given = initials(given)
    if not given:
        return family if " " not in family else "{" + family + "}"
    if "first_last" in style:
        return f"{given} {family}"
    return f"{family}, {given}"


def format_people(people: list[dict], style: set[str]) -> str:
    if "and_others" in style and len(people) > 4:
        return " and ".join(format_person(a, style) for a in people[:3]) + " and others"
    return " and ".join(format_person(a, style) for a in people)


def bib_pages(p: str) -> str:
    p = str(p).strip()
    return re.sub(r"\s*[-\u2013\u2014]+\s*", "--", p)


def make_key(meta: dict, used: set[str]) -> str:
    first = meta["authors"][0] if meta.get("authors") else {"literal": "anon"}
    surname = first.get("family") or first.get("literal", "anon")
    surname = norm(surname).split()
    surname = surname[-1] if surname else "anon"
    stop = {"a", "an", "the", "on", "of", "in", "for", "and", "to", "with", "is", "are", "from", "via", "at", "by",
            "towards", "toward", "can", "do", "does", "what", "how", "why", "when", "der", "die", "das", "uber", "zur"}
    words = [w for w in norm(meta.get("title", "")).split() if w not in stop and not w.isdigit()]
    word = words[0] if words else "untitled"
    base = f"{surname}{meta.get('year') or 'nd'}{word}"
    key, n = base, 0
    while key in used:
        key = base + "abcdefghijklmnopqrstuvwxyz"[n % 26] * (n // 26 + 1)
        n += 1
    used.add(key)
    return key


def bib_entry_type(meta: dict) -> str:
    if meta.get("bibtype"):
        return meta["bibtype"]
    reg = meta.get("registry")
    if reg == "arxiv":
        return "misc"
    if reg == "dblp":
        return {"Inproceedings": "inproceedings", "Article": "article", "Book": "book",
                "Incollection": "incollection"}.get(meta.get("dblp_type", ""), "misc")
    ct = meta.get("crossref_type", "")
    return {"journal-article": "article", "proceedings-article": "inproceedings", "book": "book",
            "monograph": "book", "edited-book": "book", "reference-book": "book",
            "book-chapter": "incollection", "posted-content": "misc"}.get(ct, "misc")


def to_bibtex(meta: dict, key: str, style: list[str] | None = None, entry_type: str | None = None) -> str:
    style = set(style or [])
    etype = entry_type or bib_entry_type(meta)
    fields: list[tuple[str, str]] = []

    def text(s: str) -> str:
        s = escape_bib(s)
        return to_latex(s) if "latex_accents" in style else s

    if meta.get("authors"):
        people = format_people(meta["authors"], style)
        if meta.get("et_al") and not people.endswith(" and others"):
            people += " and others"
        fields.append(("author", text(people)))
    if meta.get("editors") and etype in ("incollection", "book", "inproceedings"):
        fields.append(("editor", text(format_people(meta["editors"], style - {"and_others"}))))
    title = meta.get("title", "")
    if meta.get("subtitle") and "no_subtitle" not in style and not title.endswith(meta["subtitle"]):
        title = f"{title}: {meta['subtitle']}"
    title = text(title)
    if "double_brace" in style:
        title = "{" + title + "}"
    elif "plain_title" not in style:
        title = protect_caps(title)
    fields.append(("title", title))
    container = meta.get("container", "")
    if "abbrev_journal" in style and meta.get("short_container"):
        container = meta["short_container"]
    if etype == "article":
        if container:
            fields.append(("journal", text(container)))
    elif etype in ("inproceedings", "incollection"):
        if container:
            fields.append(("booktitle", text(container)))
    if meta.get("series"):
        fields.append(("series", text(meta["series"])))
    for f, k in (("volume", "volume"), ("number", "number")):
        if meta.get(k):
            fields.append((f, text(str(meta[k]))))
    if meta.get("pages"):
        fields.append(("pages", bib_pages(meta["pages"])))
    if meta.get("year"):
        fields.append(("year", str(meta["year"])))
    if meta.get("publisher") and etype in ("book", "incollection", "inproceedings") and "no_publisher" not in style:
        fields.append(("publisher", text(meta["publisher"])))
    if meta.get("isbn") and etype == "book" and "no_isbn" not in style:
        fields.append(("isbn", meta["isbn"]))
    if meta.get("doi") and "no_doi" not in style:
        fields.append(("doi", meta["doi"]))
    if meta.get("arxiv"):
        if "arxiv_journal" in style:
            fields.insert(2, ("journal", f"arXiv preprint arXiv:{meta['arxiv']}"))
        else:
            fields.append(("eprint", meta["arxiv"]))
            fields.append(("archivePrefix", "arXiv"))
            if meta.get("arxiv_class"):
                fields.append(("primaryClass", meta["arxiv_class"]))
    if meta.get("url") and "with_url" in style:
        fields.append(("url", meta["url"]))
    if meta.get("note"):
        fields.append(("note", text(meta["note"])))
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields)
    return f"@{etype}{{{key},\n{body}\n}}"


# --------------------------------------------------------------------------------------------
# Minimal BibTeX parser for validation
# --------------------------------------------------------------------------------------------

_ENTRY_HEAD = re.compile(r"\s*@([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,")


def parse_bibtex(s: str) -> tuple[str, str, dict[str, str]]:
    """Parse one entry. Raises ValueError on unbalanced braces or malformed fields."""
    m = _ENTRY_HEAD.match(s)
    if not m:
        raise ValueError("no @type{key, header")
    etype, key = m.group(1).lower(), m.group(2)
    depth = 0
    for i, c in enumerate(s):
        if c == "{" and (i == 0 or s[i - 1] != "\\"):
            depth += 1
        elif c == "}" and (i == 0 or s[i - 1] != "\\"):
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced braces")
    if depth != 0:
        raise ValueError("unbalanced braces")
    body = s[m.end():].rstrip()
    if not body.endswith("}"):
        raise ValueError("entry does not end with }")
    body = body[:-1]
    fields: dict[str, str] = {}
    pos = 0
    field_re = re.compile(r"\s*([A-Za-z][\w\-]*)\s*=\s*")
    while pos < len(body):
        if body[pos:].strip() in ("", ","):
            break
        fm = field_re.match(body, pos)
        if not fm:
            raise ValueError(f"bad field near: {body[pos:pos + 30]!r}")
        name = fm.group(1).lower()
        pos = fm.end()
        if body[pos] == "{":
            d, j = 0, pos
            while True:
                if body[j] == "{" and body[j - 1] != "\\":
                    d += 1
                elif body[j] == "}" and body[j - 1] != "\\":
                    d -= 1
                    if d == 0:
                        break
                j += 1
            value = body[pos + 1:j]
            pos = j + 1
        elif body[pos] == '"':
            j = body.index('"', pos + 1)
            value, pos = body[pos + 1:j], j + 1
        else:
            vm = re.match(r"[\w\-]+", body[pos:])
            if not vm:
                raise ValueError("bad bare value")
            value, pos = vm.group(0), pos + vm.end()
        if name in fields:
            raise ValueError(f"duplicate field {name}")
        fields[name] = value
        cm = re.match(r"\s*,?", body[pos:])
        pos += cm.end()
    return etype, key, fields


# --------------------------------------------------------------------------------------------
# Dataset construction
# --------------------------------------------------------------------------------------------

ITEM_FIELDS = ("id", "label", "bibtex", "field", "entry_type", "source", "source_url", "licence",
               "constructed", "notes")
_RETRACTED_PREFIX = re.compile(r"^\s*(\[\s*retracted\s*\]|(retracted( article)?|retraction|withdrawn)\s*[:.\-])\s*", re.I)


def load_raw(name: str) -> dict:
    return json.loads((RAW / name).read_text(encoding="utf-8"))


def item(**kw) -> dict:
    missing = [f for f in ITEM_FIELDS if f not in kw]
    if missing:
        raise ValueError(f"item missing {missing}")
    return {f: kw[f] for f in ITEM_FIELDS}


def record_url(rec: dict) -> str:
    reg, ident = rec["registry"], rec["ident"]
    if reg == "crossref":
        return f"https://doi.org/{ident}"
    if reg == "dblp":
        return f"https://dblp.org/rec/{ident}"
    if reg == "arxiv":
        return f"https://arxiv.org/abs/{ident}"
    raise ValueError(reg)


def short(s: str, n: int = 80) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 3].rstrip() + "..."


def person_str(a: dict) -> str:
    if "literal" in a:
        return a["literal"]
    return f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")


def build_real(real: list[dict], used: set[str]) -> list[dict]:
    out = []
    for rec in real:
        meta = rec["meta"]
        style = rec.get("style", [])
        if rec.get("n_authors", 0) > len(meta.get("authors", [])) and "and_others" not in style:
            raise ValueError(f"ho-real-{rec['n']:04d}: author list truncated in cache but style lacks and_others")
        key = make_key(meta, used)
        etype = rec["entry_type"]
        bib = to_bibtex(meta, key, style, etype)
        how = {"crossref": f"Crossref record {meta.get('doi')}", "dblp": f"dblp record {rec['ident']}",
               "arxiv": f"arXiv record {rec['ident']}"}[rec["registry"]]
        note = f"Genuine reference, drawn at random ({rec['sampled']}). BibTeX written from the {how}."
        if style:
            note += " Messy-but-valid forms: " + ", ".join(sorted(style)) + "."
        if rec.get("extra_note"):
            note += " " + rec["extra_note"]
        out.append(item(id=f"{PREFIX['real']}{rec['n']:04d}", label="real", bibtex=bib, field=rec["field"],
                        entry_type=etype, source=rec["registry"], source_url=record_url(rec),
                        licence=SOURCES[rec["registry"]][1], constructed=False, notes=note))
    return out


def _check_summary(checks: dict) -> str:
    parts = []
    for reg in ("crossref", "openalex", "arxiv", "dblp"):
        c = checks.get(reg)
        if c is None:
            continue
        if c["best_sim"] == 0 and not c.get("best_title"):
            parts.append(f"{reg} search returned no candidates")
        else:
            parts.append(f"{reg} best title similarity {c['best_sim']:.2f}")
    s = "; ".join(parts)
    if checks.get("arxiv_id"):
        a = checks["arxiv_id"]
        s += f"; the arXiv ID {a['id']} " + (f"belongs to a different paper, '{short(a['title'], 70)}'"
                                            if a.get("title") else "does not resolve")
    if checks.get("doi"):
        d = checks["doi"]
        s += f"; the DOI {d['id']} " + (f"belongs to a different work, '{short(d['title'], 70)}'"
                                        if d.get("title") else "does not resolve in Crossref")
    return s


def build_fabricated(fab: list[dict], used: set[str]) -> list[dict]:
    out = []
    for rec in fab:
        meta = dict(rec["parsed"])
        meta.setdefault("registry", "fabricated")
        key = make_key(meta, used)
        bib = to_bibtex(meta, key, rec.get("style", []), meta["bibtype"])
        src = rec["source"]
        note = (f"Hallucinated reference that appeared in a real paper or submission, listed in {rec['location']} "
                f"(cited in {rec['cited_in']}). BibTeX transcribed from the printed reference string"
                + (f" ({rec['transcription_note'].rstrip('.')})" if rec.get("transcription_note") else "")
                + f". Registry title searches on {rec['checked']}: {_check_summary(rec['checks'])}."
                + f" Web search for the exact title in quotes on {rec['web']['date']}: {rec['web']['result'].rstrip('.')}.")
        if rec.get("manual_check"):
            note += " Reviewed by hand: " + rec["manual_check"]
        out.append(item(id=f"{PREFIX['fabricated']}{rec['n']:04d}", label="fabricated", bibtex=bib, field=rec["field"],
                        entry_type=meta["bibtype"], source=src, source_url=SOURCES[src][0],
                        licence=SOURCES[src][1], constructed=False, notes=note))
    return out


def build_retracted(ret: list[dict], used: set[str]) -> list[dict]:
    out = []
    for rec in ret:
        meta = dict(rec["meta"])
        meta.update(json.loads(json.dumps(rec.get("overrides", {}))))
        orig = rec["meta"]["title"]
        stripped = _RETRACTED_PREFIX.sub("", meta["title"])
        prefix_note = ""
        if stripped != orig:
            prefix = orig[:orig.find(stripped[:12])].strip() if stripped[:12] in orig else ""
            prefix_note = (f" Title given without the '{prefix}' prefix that the publisher added after retraction."
                           if prefix else f" The registry stores the title as '{orig}'; the entry uses the printed form.")
        meta["title"] = stripped
        style = rec.get("style", [])
        if rec.get("n_authors", 0) > len(meta.get("authors", [])):
            style = sorted(set(style) | {"and_others"})
        key = make_key(meta, used)
        etype = rec["entry_type"]
        bib = to_bibtex(meta, key, style, etype)
        rw = rec["rw"]
        note = (f"Retracted. Retraction notice DOI {rec['notice_doi']} (dated {rec['retraction_date']}); "
                f"Retraction Watch record {rw['record_id']}; Crossref lists the retraction in updated-by "
                f"(source: {rec['crossref_source']}).")
        if rw.get("reasons"):
            note += " Reasons recorded by Retraction Watch: " + "; ".join(rw["reasons"][:4]) + "."
        note += prefix_note
        if style:
            note += " Messy-but-valid forms: " + ", ".join(sorted(style)) + "."
        out.append(item(id=f"{PREFIX['retracted']}{rec['n']:04d}", label="retracted", bibtex=bib, field=rec["field"],
                        entry_type=etype, source="retraction-watch",
                        source_url=f"https://api.crossref.org/works/{urllib.parse.quote(meta['doi'], safe='/')}",
                        licence=SOURCES["retraction-watch"][1], constructed=False, notes=note))
    return out


def _rid(rec: dict) -> str:
    return f"{PREFIX['real']}{rec['n']:04d}"


def build_wrong_doi(real: list[dict], rng: random.Random, used: set[str]) -> list[dict]:
    pool = sorted((r for r in real if r["meta"].get("doi") and r["registry"] == "crossref"), key=lambda r: r["n"])
    bases = rng.sample(pool, N_WRONG_DOI)
    out = []
    for i, base in enumerate(bases, 1):
        same = i % 2 == 0
        donors = [d for d in pool if d is not base and (d["field"] == base["field"]) == same
                  and d["meta"]["doi"].lower() != base["meta"]["doi"].lower()]
        donor = rng.choice(donors)
        meta = json.loads(json.dumps(base["meta"]))
        meta["doi"] = donor["meta"]["doi"]
        style = [s for s in base.get("style", []) if s != "no_doi"]
        key = make_key(meta, used)
        bib = to_bibtex(meta, key, style, base["entry_type"])
        dm = donor["meta"]
        note = (f"Constructed from {_rid(base)}: the entry's own DOI is {base['meta']['doi']}; it was replaced "
                f"with {dm['doi']}, which belongs to '{short(dm['title'], 70)}' ({person_str(dm['authors'][0]) if dm['authors'] else 'n.a.'}, "
                f"{dm.get('year')}), a {'same' if same else 'different'}-field work ({_rid(donor)}).")
        out.append(item(id=f"{PREFIX['wrong_doi']}{i:04d}", label="wrong_doi", bibtex=bib, field=base["field"],
                        entry_type=base["entry_type"], source="constructed", source_url=record_url(base),
                        licence="constructed", constructed=True, notes=note))
    return out


_TITLE_STOP = {"a", "an", "the", "of", "and", "in", "on", "for", "to", "with", "by", "from", "via", "at", "as",
               "is", "are", "its", "their", "into", "using", "under", "between", "over", "der", "die", "und"}


def _alter_title(title: str, vocab: list[str], rng: random.Random) -> str:
    words = title.split()
    content = [i for i, w in enumerate(words) if re.fullmatch(r"[A-Za-z][a-z\-]{3,}[,:;]?", w)
               and w.lower().strip(",:;") not in _TITLE_STOP]
    k = max(2, round(len(content) * 0.4))
    for _ in range(20):
        new = list(words)
        for i in rng.sample(content, min(k, len(content))):
            w = words[i]
            punct = w[-1] if w[-1] in ",:;" else ""
            rep = rng.choice([v for v in vocab if v.lower() != w.lower().strip(",:;")])
            if w[0].isupper():
                rep = rep[0].upper() + rep[1:]
            new[i] = rep + punct
        cand = " ".join(new)
        if title_sim(cand, title) < 0.85:
            return cand
        k += 1
    raise ValueError(f"could not alter title {title!r}")


def build_metadata_error(real: list[dict], rng: random.Random, used: set[str]) -> list[dict]:
    pool = sorted(real, key=lambda r: r["n"])
    kinds = ["year", "first_author", "venue", "title"] * (N_METADATA_ERROR // 4)
    taken: set[int] = set()
    vocab_by_field: dict[str, list[str]] = {}
    english = {"the", "of", "and", "for", "in", "with", "a", "on", "by", "from"}
    for r in pool:
        if not english & set(r["meta"]["title"].lower().split()):
            continue  # keep the replacement vocabulary English
        for w in r["meta"]["title"].split():
            w = w.strip(",:;.?!()\"'")
            if re.fullmatch(r"[a-z][a-z\-]{4,}", w.lower()) and w.lower() not in _TITLE_STOP:
                vocab_by_field.setdefault(r["field"], []).append(w.lower())
    for f in vocab_by_field:
        vocab_by_field[f] = sorted(set(vocab_by_field[f]))

    def eligible(r: dict, kind: str) -> bool:
        m = r["meta"]
        if r["n"] in taken:
            return False
        if kind == "year":
            return bool(m.get("year"))
        if kind == "first_author":
            return bool(m.get("authors")) and "literal" not in m["authors"][0]
        if kind == "venue":
            return r["entry_type"] in ("article", "inproceedings") and bool(m.get("container"))
        if kind == "title":
            return (len([w for w in m["title"].split() if len(w) >= 4]) >= 4 and len(m["title"].split()) >= 6
                    and "$" not in m["title"])
        return False

    out = []
    for i, kind in enumerate(kinds, 1):
        base = rng.choice([r for r in pool if eligible(r, kind)])
        taken.add(base["n"])
        meta = json.loads(json.dumps(base["meta"]))
        if kind == "year":
            delta = rng.choice([-6, -5, -4, -3, -2, 2, 3, 4, 5, 6])
            new = meta["year"] + delta
            if new > 2026:
                new = meta["year"] - abs(delta)
            change = f"year changed {meta['year']} -> {new}"
            meta["year"] = new
        elif kind == "first_author":
            fams = {norm(a.get("family", a.get("literal", ""))) for a in meta["authors"]}
            donors = [r for r in pool if r is not base and r["field"] != base["field"] and r["meta"].get("authors")
                      and "literal" not in r["meta"]["authors"][0]
                      and norm(r["meta"]["authors"][0]["family"]) not in fams]
            new = dict(rng.choice(donors)["meta"]["authors"][0])
            change = f"first author replaced: '{person_str(meta['authors'][0])}' -> '{person_str(new)}'"
            meta["authors"][0] = new
        elif kind == "venue":
            donors = sorted({r["meta"]["container"] for r in pool if r["entry_type"] == base["entry_type"]
                             and r["meta"].get("container") and title_sim(r["meta"]["container"], meta["container"]) < 0.6})
            new = rng.choice(donors)
            fieldname = "journal" if base["entry_type"] == "article" else "booktitle"
            change = f"{fieldname} changed '{meta['container']}' -> '{new}'"
            meta["container"] = new
            meta["short_container"] = ""
        else:
            new = _alter_title(meta["title"], vocab_by_field[base["field"]], rng)
            change = f"title words altered: '{meta['title']}' -> '{new}'"
            meta["title"] = new
            meta["subtitle"] = ""
        style = [s for s in base.get("style", []) if s != "with_url" and not (kind == "venue" and s == "abbrev_journal")]
        key = make_key(meta, used)
        bib = to_bibtex(meta, key, style, base["entry_type"])
        note = f"Constructed from {_rid(base)}; corrupted field: {kind}; {change}."
        if not meta.get("doi"):
            note += " The entry has no DOI, so the mismatch can only be found by a title or author search."
        out.append(item(id=f"{PREFIX['metadata_error']}{i:04d}", label="metadata_error", bibtex=bib, field=base["field"],
                        entry_type=base["entry_type"], source="constructed", source_url=record_url(base),
                        licence="constructed", constructed=True, notes=note))
    return out


def build() -> list[dict]:
    real = load_raw("real.json")["items"]
    fab = load_raw("fabricated.json")["items"]
    ret = load_raw("retracted.json")["items"]
    used: set[str] = set(load_raw("dev_fingerprints.json")["bibtex_keys"])  # keys stay unique across both sets
    rng = random.Random(SEED)
    items = build_real(real, used)
    items += build_fabricated(fab, used)
    items += build_wrong_doi(real, rng, used)
    items += build_metadata_error(real, rng, used)
    items += build_retracted(ret, used)
    return items


def write_jsonl(items: list[dict], path: Path = OUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------------------------
# Validation, including independence from the development set
# --------------------------------------------------------------------------------------------


def independence_problems(items: list[dict]) -> list[str]:
    """Every way a held-out item could overlap the development set."""
    fp = load_raw("dev_fingerprints.json")
    dev_dois, dev_titles, dev_keys = set(fp["dois"]), set(fp["norm_titles"]), set(fp["bibtex_keys"])
    dev_recs = set(fp["registry_records"])
    out = []
    for it in items:
        _, key, f = parse_bibtex(it["bibtex"])
        if f.get("doi", "").lower() in dev_dois:
            out.append(f"{it['id']}: DOI {f['doi']} is in the development set")
        if norm(f.get("title", "")) in dev_titles:
            out.append(f"{it['id']}: title is in the development set")
        if key in dev_keys:
            out.append(f"{it['id']}: BibTeX key {key} is used in the development set")
    for rec in load_raw("real.json")["items"]:
        if f"{rec['registry']}:{rec['ident']}" in dev_recs or rec["meta"].get("doi", "").lower() in dev_dois:
            out.append(f"real #{rec['n']}: registry record {rec['ident']} is in the development set")
    hc, ct = set(fp["hallucitation_rows"]), set(fp["citetracer_submissions"])
    raw_dev = set(fp["fabricated_raw_norm"])
    reviewed = set(fp["dev_reviewed_candidates"])
    for rec in load_raw("fabricated.json")["items"]:
        if rec["row"] in (hc if rec["source"] == "hallucitation-acl2026" else ct):
            out.append(f"fabricated #{rec['n']}: source row {rec['row']} is used in the development set")
        if norm(rec["raw"]) in raw_dev:
            out.append(f"fabricated #{rec['n']}: reference string is in the development set")
        if (f"{rec['source']}:{rec['row']}" in reviewed
                or f"{rec['source']}:{rec['row']}:{norm(rec['parsed']['title'])}" in reviewed):
            out.append(f"fabricated #{rec['n']}: the development build already reviewed this candidate")
    rw, notices = set(fp["retraction_watch_records"]), set(fp["retraction_notice_dois"])
    for rec in load_raw("retracted.json")["items"]:
        if rec["rw"]["record_id"] in rw or rec["notice_doi"].lower() in notices:
            out.append(f"retracted #{rec['n']}: Retraction Watch record {rec['rw']['record_id']} is in the development set")
    return out


def validate(path: Path = OUT) -> bool:
    ok = True
    ids, keys = set(), set()
    counts: dict[str, dict[str, int]] = {}
    items = []
    with open(path, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            try:
                it = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"line {ln}: invalid JSON: {exc}")
                ok = False
                continue
            items.append(it)
            problems = []
            if list(it) != list(ITEM_FIELDS):
                problems.append(f"fields {list(it)}")
            if it.get("label") not in LABELS:
                problems.append(f"label {it.get('label')}")
            elif not str(it.get("id", "")).startswith(PREFIX[it["label"]]):
                problems.append(f"id prefix does not match label {it['label']}")
            if it.get("field") not in FIELDS:
                problems.append(f"field {it.get('field')}")
            if not isinstance(it.get("constructed"), bool):
                problems.append("constructed not bool")
            if it.get("constructed") != (it.get("label") in ("wrong_doi", "metadata_error")):
                problems.append("constructed flag does not match label")
            if it.get("constructed") and it.get("licence") != "constructed":
                problems.append("constructed item licence must be 'constructed'")
            for f in ("id", "bibtex", "entry_type", "source", "source_url", "licence", "notes"):
                if not isinstance(it.get(f), str) or not it.get(f):
                    problems.append(f"empty {f}")
            if it.get("id") in ids:
                problems.append("duplicate id")
            ids.add(it.get("id"))
            try:
                etype, key, fields = parse_bibtex(it["bibtex"])
                if key in keys:
                    problems.append(f"duplicate bibtex key {key}")
                keys.add(key)
                if etype != it["entry_type"]:
                    problems.append(f"entry_type {it['entry_type']} != @{etype}")
                for req in ("author", "title", "year"):
                    if req not in fields:
                        problems.append(f"bibtex lacks {req}")
                if it["label"] == "wrong_doi" and "doi" not in fields:
                    problems.append("wrong_doi item without doi")
                if it["label"] == "retracted" and "doi" not in fields:
                    problems.append("retracted item without doi")
            except (ValueError, IndexError, KeyError) as exc:
                problems.append(f"bibtex: {exc}")
            if problems:
                ok = False
                print(f"line {ln} ({it.get('id')}): " + "; ".join(problems))
            counts.setdefault(it.get("label"), {}).setdefault(it.get("field"), 0)
            counts[it.get("label")][it.get("field")] += 1
    try:
        overlap = independence_problems(items)
    except (ValueError, KeyError) as exc:
        overlap = [f"independence check failed: {exc}"]
    for p in overlap:
        print("overlap with development set: " + p)
    ok &= not overlap
    total = sum(sum(v.values()) for v in counts.values())
    print(f"{path.name}: {total} items, {len(keys)} unique BibTeX keys; "
          f"overlap with the development set: {len(overlap)}")
    header = f"{'label':<15}" + "".join(f"{f:>11}" for f in FIELDS) + f"{'total':>8}"
    print(header)
    for lab in LABELS:
        row = counts.get(lab, {})
        n = sum(row.values())
        print(f"{lab:<15}" + "".join(f"{row.get(f, 0):>11}" for f in FIELDS) + f"{n:>8}")
        if n < TARGETS[lab]:
            print(f"  below target: {lab} has {n}, needs {TARGETS[lab]}")
            ok = False
    print("validation", "passed" if ok else "FAILED")
    return ok


# --------------------------------------------------------------------------------------------
# Refresh (re-fetch real and retracted items) and fabricated re-check
# --------------------------------------------------------------------------------------------

_COMPARE = ("title", "subtitle", "year", "container", "volume", "number", "pages", "doi")


def _fetch_meta(rec: dict) -> tuple[dict, int, dict | None]:
    reg, ident = rec["registry"], rec["ident"]
    if reg == "crossref":
        m = crossref_work(ident)
        return meta_from_crossref(m), len(m.get("author", []) or []), m
    if reg == "arxiv":
        r = arxiv_by_id(ident)
        if r is None:
            raise KeyError(ident)
        return meta_from_arxiv(r), len(r["authors"]), None
    if reg == "dblp":
        r = dblp_record(ident)
        return meta_from_dblp(ident, r), len(r["authors"]), None
    raise ValueError(reg)


def _diff(old: dict, new: dict) -> list[str]:
    d = [f"{k}: {old.get(k)!r} -> {new.get(k)!r}" for k in _COMPARE if str(old.get(k) or "") != str(new.get(k) or "")]
    oa = [norm(a.get("family", a.get("literal", ""))) for a in old.get("authors", [])]
    na = [norm(a.get("family", a.get("literal", ""))) for a in new.get("authors", [])][: len(oa)]
    if oa != na:
        d.append(f"authors: {oa[:4]} -> {na[:4]}")
    return d


def refresh(update_cache: bool) -> bool:
    ok = True
    for fname in ("real.json", "retracted.json"):
        data = load_raw(fname)
        changed = 0
        for rec in data["items"]:
            label = f"{fname[:-5]}#{rec['n']} {rec['registry']}:{rec['ident']}"
            try:
                new, n_auth, raw = _fetch_meta(rec)
            except Exception as exc:  # noqa: BLE001
                print(f"{label}: fetch failed: {exc}")
                ok = False
                continue
            limit = len(rec["meta"].get("authors", []))
            new["authors"] = new["authors"][:limit] if n_auth > limit else new["authors"]
            if fname == "real.json":  # retracted.json keeps the registry form and applies overrides at build time
                new.update(json.loads(json.dumps(rec.get("overrides", {}))))  # curated changes, see real.json
            diffs = _diff(rec["meta"], new)
            if fname == "retracted.json":
                ups = [u for u in (raw or {}).get("updated-by", []) or [] if u.get("type") == "retraction"]
                if not ups:
                    diffs.append("Crossref no longer lists a retraction in updated-by")
                    ok = False
            if diffs:
                print(f"{label}: " + " | ".join(diffs))
                if update_cache:
                    rec["meta"] = new
                    rec["n_authors"] = n_auth
                    changed += 1
        if update_cache and changed:
            (RAW / fname).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"{fname}: updated {changed} cached records")
    return ok


def default_registries() -> tuple[str, ...]:
    regs = ("crossref", "arxiv", "dblp")
    return regs + ("openalex",) if os.environ.get("OPENALEX_API_KEY") else regs


def existence_checks(title: str, first_author: str = "", arxiv: str = "", doi: str = "",
                     registries: tuple[str, ...] | None = None) -> dict:
    """Search each registry for `title`; report the best-matching title and its similarity."""
    registries = registries or default_registries()
    res: dict = {}
    if "crossref" in registries:
        items = crossref_search(f"{title} {first_author}".strip(), rows=5)
        best = max(items, key=lambda it: title_sim(title, (it.get("title") or [""])[0]), default=None)
        res["crossref"] = {"best_title": (best.get("title") or [""])[0] if best else "",
                           "best_id": best.get("DOI", "") if best else "",
                           "best_sim": round(title_sim(title, (best.get("title") or [""])[0]), 3) if best else 0.0}
    if "openalex" in registries:
        items = openalex_search(title, rows=5)
        best = max(items, key=lambda it: title_sim(title, it.get("title") or ""), default=None)
        res["openalex"] = {"best_title": (best or {}).get("title") or "", "best_id": (best or {}).get("id", ""),
                           "best_sim": round(title_sim(title, (best or {}).get("title") or ""), 3) if best else 0.0}
    if "arxiv" in registries:
        items = arxiv_search_title(title, rows=5)
        best = max(items, key=lambda it: title_sim(title, it["title"]), default=None)
        res["arxiv"] = {"best_title": best["title"] if best else "", "best_id": best["id"] if best else "",
                        "best_sim": round(title_sim(title, best["title"]), 3) if best else 0.0}
        if arxiv:
            r = arxiv_by_id(arxiv)
            res["arxiv_id"] = {"id": arxiv, "title": r["title"] if r else "",
                               "sim": round(title_sim(title, r["title"]), 3) if r else 0.0}
    if "dblp" in registries:
        items = dblp_title_search(title, limit=3)
        best = items[0] if items else None
        res["dblp"] = {"best_title": best["title"] if best else "", "best_id": best["key"] if best else "",
                       "best_sim": round(title_sim(title, best["title"]), 3) if best else 0.0}
    if doi:
        try:
            m = crossref_work(doi)
            t = clean_markup((m.get("title") or [""])[0])
            res["doi"] = {"id": doi, "title": t, "sim": round(title_sim(title, t), 3)}
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            res["doi"] = {"id": doi, "title": "", "sim": 0.0}
    return res


FOUND_THRESHOLD = 0.85


def check_fabricated() -> bool:
    ok = True
    for rec in load_raw("fabricated.json")["items"]:
        p = rec["parsed"]
        first = person_str(p["authors"][0]) if p.get("authors") else ""
        try:
            res = existence_checks(p["title"], first, p.get("arxiv", ""), p.get("doi", ""))
        except Exception as exc:  # noqa: BLE001
            print(f"ho-fab-{rec['n']:04d}: check failed: {exc}")
            ok = False
            continue
        hits = [f"{reg} {v['best_sim']:.2f} '{short(v['best_title'], 60)}'" for reg, v in res.items()
                if "best_sim" in v and v["best_sim"] >= FOUND_THRESHOLD]
        if hits:
            ok = False
            print(f"ho-fab-{rec['n']:04d}: possible real match: " + "; ".join(hits))
        else:
            print(f"ho-fab-{rec['n']:04d}: still not found (max similarity "
                  f"{max(v.get('best_sim', 0) for v in res.values()):.2f})")
    return ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--validate", action="store_true", help="only validate the existing JSONL")
    ap.add_argument("--refresh", action="store_true", help="re-fetch real and retracted items and report drift")
    ap.add_argument("--update-cache", action="store_true", help="with --refresh, write fresh metadata to raw/")
    ap.add_argument("--check-fabricated", action="store_true", help="re-run existence searches for fabricated items")
    ap.add_argument("--out", type=Path, default=OUT, help="output path (default heldout.jsonl)")
    args = ap.parse_args(argv)
    ok = True
    if args.validate:
        return 0 if validate(args.out) else 1
    if args.refresh:
        ok &= refresh(args.update_cache)
    if args.check_fabricated:
        ok &= check_fabricated()
    write_jsonl(build(), args.out)
    ok &= validate(args.out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
