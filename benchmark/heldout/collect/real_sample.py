"""Sample genuine references for the held-out set at random and cache their registry metadata.

usage: python3 -I collect/real_sample.py RETRACTION_WATCH.csv
Writes work/real_cands.json (the random samples) and raw/real.json (the chosen records).
Journal articles, books and chapters: OpenAlex `sample=` with a field filter, metadata from Crossref.
DOI-less conference papers: dblp SPARQL, random record keys from ten venues that do not mint DOIs.
arXiv-only preprints: OpenAlex `sample=` on the arXiv source, metadata from the arXiv API.
"""
import csv
import json
import os
import random
import re
import sys
import urllib.error
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

bh._MIN_INTERVAL["api.crossref.org"] = 0.4
SEED = 20261024
rng = random.Random(SEED)
csv.field_size_limit(10**9)
rw_dois = set()
for r in csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")):
    d = r["OriginalPaperDOI"].strip().lower()
    if d.startswith("10."):
        rw_dois.add(d)
fp = json.load(open(HERE / "raw" / "dev_fingerprints.json", encoding="utf-8"))
dev_dois, dev_titles = set(fp["dois"]), set(fp["norm_titles"])
KEY = os.environ["OPENALEX_API_KEY"]

FIELD_IDS = {"cs": [17], "biomed": [27, 13, 28, 24, 30], "physics": [31], "math": [26],
             "social": [33, 32, 20, 14], "humanities": [12], "other": [16, 25, 19, 23, 21, 22, 11]}
ARTICLE_QUOTA = {"cs": 9, "biomed": 11, "physics": 9, "math": 10, "social": 10, "humanities": 9, "other": 9}
BOOK_QUOTA = [("book", "humanities", 1), ("book", "social", 1), ("book", "math", 1), ("book", "other", 1),
              ("book-chapter", "humanities", 1), ("book-chapter", "social", 1), ("book-chapter", "cs", 1),
              ("book-chapter", "biomed", 1), ("book-chapter", "physics", 1)]
ARXIV_QUOTA = {"cs": 3, "math": 2, "physics": 3, "biomed": 1, "social": 1}
DBLP_VENUES = [("NeurIPS", "nips"), ("ICML", "icml"), ("ICLR", "iclr"), ("AISTATS", "aistats"), ("COLT", "colt"),
               ("UAI", "uai"), ("LREC", "lrec"), ("CoRL", "corl"), ("MIDL", "midl"), ("ISMIR", "ismir")]
BAD_TITLE = re.compile(r"\b(retract|withdrawn|erratum|errata|corrigend|correction|editorial|book review|"
                       r"in memoriam|obituary|preface|front matter|back matter|table of contents|index)\b", re.I)


def oa_sample(filt, n, seed):
    params = {"filter": filt, "sample": str(n), "seed": str(seed), "per-page": str(n),
              "select": "id,doi,title,publication_year,type,primary_topic,cited_by_count,language",
              "api_key": KEY}
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    return bh.get_json(url)["results"]


def ok_crossref(m, want_types):
    if m.get("type") not in want_types:
        return "type " + str(m.get("type"))
    if any(u.get("type") in ("retraction", "withdrawal", "removal") for u in m.get("updated-by", []) or []):
        return "has retraction/withdrawal"
    t = bh.clean_markup((m.get("title") or [""])[0])
    if len(t.split()) < 4:
        return "short title"
    if t.upper() == t:
        return "title in capitals"
    if BAD_TITLE.search(t):
        return "non-research title"
    if not any(a.get("family") for a in m.get("author", []) or []):
        return "no personal authors"
    if not (m.get("issued") or {}).get("date-parts", [[None]])[0][0]:
        return "no year"
    if m.get("type") == "journal-article" and not (m.get("container-title") and m.get("volume")):
        return "no journal/volume"
    if m.get("type") in ("book", "monograph") and not m.get("publisher"):
        return "no publisher"
    if m.get("type") == "book-chapter" and not m.get("container-title"):
        return "no book title"
    if m["DOI"].lower() in rw_dois or m["DOI"].lower() in dev_dois:
        return "in Retraction Watch or dev set"
    if bh.norm(t) in dev_titles:
        return "title in dev set"
    return None


cands_log, items = {}, []
_CACHE = HERE / "work" / "crossref_cache.json"
_cache = json.load(open(_CACHE)) if _CACHE.exists() else {}
_orig_work = bh.crossref_work


def _cached_work(doi):
    if doi.lower() not in _cache:
        try:
            _cache[doi.lower()] = _orig_work(doi)
        except urllib.error.HTTPError as exc:
            _cache[doi.lower()] = {"_http_error": exc.code}
        _CACHE.write_text(json.dumps(_cache), encoding="utf-8")
    m = _cache[doi.lower()]
    if "_http_error" in m:
        raise urllib.error.HTTPError(doi, m["_http_error"], "cached", None, None)
    return m


bh.crossref_work = _cached_work


def take_crossref(stratum, field, filt, quota, want_types, entry_type, seed):
    got, tries = 0, []
    pool = oa_sample(filt, max(40, quota * 5), seed)
    for w in pool:
        if got >= quota:
            break
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        if not doi:
            continue
        try:
            m = bh.crossref_work(doi)
        except urllib.error.HTTPError as exc:
            tries.append({"openalex": w["id"], "doi": doi, "skip": f"Crossref HTTP {exc.code}"})
            continue
        why = ok_crossref(m, want_types)
        if not why and w.get("language") not in (None, "en") and field != "humanities":
            why = "language " + str(w.get("language"))
        tries.append({"openalex": w["id"], "doi": doi, "skip": why})
        if why:
            continue
        meta = bh.meta_from_crossref(m)
        n_auth = len(meta["authors"])
        etype = entry_type(m)
        items.append({"registry": "crossref", "ident": meta["doi"], "field": field, "entry_type": etype,
                      "n_authors": n_auth, "meta": meta, "openalex": w["id"], "stratum": stratum,
                      "openalex_field": (w.get("primary_topic") or {}).get("field", {}).get("display_name", "")})
        got += 1
    cands_log[f"{stratum}:{field}"] = {"filter": filt, "seed": seed, "sampled": len(pool), "tried": tries}
    print(stratum, field, "got", got, "of", quota, "after", len(tries), flush=True)


BASE = "has_doi:true,is_retracted:false,is_paratext:false,cited_by_count:>4"
for k, (field, q) in enumerate(ARTICLE_QUOTA.items()):
    ids = "|".join(str(i) for i in FIELD_IDS[field])
    filt = f"{BASE},type:article,primary_location.source.type:journal,publication_year:1975-2025,primary_topic.field.id:{ids}"
    take_crossref("article", field, filt, q, ("journal-article",), lambda m: "article", SEED + k)
for k, (kind, field, q) in enumerate(BOOK_QUOTA):
    ids = "|".join(str(i) for i in FIELD_IDS[field])
    filt = f"{BASE},type:{kind},publication_year:1980-2025,primary_topic.field.id:{ids},language:en"
    want = ("book", "monograph", "edited-book") if kind == "book" else ("book-chapter",)
    take_crossref(kind, field, filt, q, want, lambda m: "book" if m["type"] != "book-chapter" else "incollection",
                  SEED + 100 + k)

# arXiv-only preprints
ARXIV_SOURCE = "S4306400194"
for k, (field, q) in enumerate(ARXIV_QUOTA.items()):
    ids = "|".join(str(i) for i in FIELD_IDS[field])
    filt = (f"primary_location.source.id:{ARXIV_SOURCE},locations_count:1,publication_year:2014-2024,"
            f"cited_by_count:>2,primary_topic.field.id:{ids}")
    pool = oa_sample(filt, 80, SEED + 200 + k)
    aids = []
    for w in pool:
        d = w.get("doi") or ""
        m = re.search(r"10\.48550/arxiv\.(.+)$", d, re.I)
        if m and re.fullmatch(r"\d{4}\.\d{4,5}", m.group(1)):
            aids.append(m.group(1))
    recs = []
    for c in range(0, len(aids), 40):
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"id_list": ",".join(aids[c:c + 40]), "max_results": "40"})
        recs += bh._arxiv_parse(bh.http_get(url, accept="application/atom+xml"))
    got, tries = 0, []
    for r in recs:
        if got >= q:
            break
        why = None
        if r["doi"] or r["journal_ref"]:
            why = "arXiv record has a DOI or journal reference"
        elif bh.norm(r["title"]) in dev_titles:
            why = "title in dev set"
        elif len(r["title"].split()) < 4:
            why = "short title"
        tries.append({"arxiv": r["id"], "skip": why})
        if why:
            continue
        meta = bh.meta_from_arxiv(r)
        items.append({"registry": "arxiv", "ident": r["id"], "field": field, "entry_type": "misc",
                      "n_authors": len(meta["authors"]), "meta": meta, "stratum": "arxiv"})
        got += 1
    cands_log[f"arxiv:{field}"] = {"filter": filt, "seed": SEED + 200 + k, "sampled": len(pool), "tried": tries}
    print("arxiv", field, "got", got, "of", q, flush=True)

# DOI-less conference papers from dblp
for venue, slug in DBLP_VENUES:
    year = str(rng.choice(range(2016, 2024)))
    q = bh._DBLP_PREFIX + (f'SELECT ?p WHERE {{ ?p dblp:publishedIn "{venue}" ; dblp:yearOfPublication ?y . '
                           f'FILTER(STR(?y)="{year}") FILTER(STRSTARTS(STR(?p), "https://dblp.org/rec/conf/{slug}/")) '
                           f'FILTER NOT EXISTS {{ ?p dblp:doi ?d }} }} LIMIT 5000')
    keys = sorted(r["p"].replace("https://dblp.org/rec/", "") for r in bh.dblp_sparql(q))
    order = list(keys)
    rng.shuffle(order)
    tries, got = [], 0
    for key in order[:6]:
        r = bh.dblp_record(key)
        why = None
        if r.get("doi"):
            why = "has DOI"
        elif bh.norm(r["title"]) in dev_titles:
            why = "title in dev set"
        elif len(r["title"].split()) < 4 or not r["authors"]:
            why = "short title or no authors"
        tries.append({"dblp": key, "skip": why})
        if why:
            continue
        meta = bh.meta_from_dblp(key, r)
        items.append({"registry": "dblp", "ident": key, "field": "cs", "entry_type": "inproceedings",
                      "n_authors": len(meta["authors"]), "meta": meta, "stratum": "dblp"})
        got = 1
        break
    cands_log[f"dblp:{venue}"] = {"year": year, "n_keys": len(keys), "tried": tries}
    print("dblp", venue, year, "keys", len(keys), "got", got, flush=True)

(HERE / "work" / "real_cands.json").write_text(json.dumps(cands_log, indent=1, ensure_ascii=False), encoding="utf-8")
(HERE / "work" / "real_items_raw.json").write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
print("total", len(items))
