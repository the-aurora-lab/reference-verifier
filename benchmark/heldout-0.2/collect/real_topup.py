"""Top up the arXiv-only and dblp strata after the first run of real_sample.py (appends to DIR/real_items_raw.json
and DIR/real_cands.json).

usage: HELDOUT_WORK=DIR python3 -I collect/real_topup.py

arXiv: OpenAlex now leaves `doi` empty for most arXiv-only works, so the first run, which read the arXiv ID from
the DOI, found only a few IDs per sample. The same samples (same filter, seed and size) are drawn again with the
landing-page URL, the arXiv ID is read from it, and IDs the first run already tried are skipped.
dblp: two drawn venue-years gave no DOI-less records. dblp names NeurIPS 2017 "NIPS", so that venue is queried
under both names; a venue that still has none gets a new year drawn with random.Random(SEED).
"""
import json
import os
import random
import re
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

WORK = Path(os.environ.get("HELDOUT_WORK", HERE / "work"))
bh._MIN_INTERVAL["api.crossref.org"] = 0.5
bh._MIN_INTERVAL["api.openalex.org"] = 0.4
bh._MIN_INTERVAL["sparql.dblp.org"] = 2.0
SEED = bh.SEED
prior = json.load(open(HERE / "raw" / "prior_fingerprints.json", encoding="utf-8"))["sets"]
prior_titles = set().union(*(set(s["norm_titles"]) for s in prior.values()))
prior_records = set().union(*(set(s["registry_records"]) for s in prior.values()))
prior_sampled = set().union(*(set(s["sampled_records"]) for s in prior.values()))
items = json.load(open(WORK / "real_items_raw.json", encoding="utf-8"))
log = json.load(open(WORK / "real_cands.json", encoding="utf-8"))
FIELD_IDS = {"cs": [17], "biomed": [27, 13, 28, 24, 30], "physics": [31], "math": [26], "social": [33, 32, 20, 14]}
ARXIV_QUOTA = {"cs": 3, "math": 2, "physics": 3, "biomed": 1, "social": 1}
ARXIV_ID = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?", re.I)

for field, q in ARXIV_QUOTA.items():
    have = sum(1 for it in items if it["stratum"] == "arxiv" and it["field"] == field)
    if have >= q:
        continue
    L = log[f"arxiv:{field}"]
    tried = {t["arxiv"] for t in L["tried"]}
    params = {"filter": L["filter"], "sample": str(L["sampled"]), "seed": str(SEED), "per-page": str(L["sampled"]),
              "select": "id,doi,primary_location"}
    pool = bh.openalex_get(params)["results"]
    aids = []
    for w in pool:
        m = ARXIV_ID.search((w.get("primary_location") or {}).get("landing_page_url") or "") or \
            re.search(r"10\.48550/arxiv\.(\d{4}\.\d{4,5})$", w.get("doi") or "", re.I)
        if m and m.group(1) not in tried and m.group(1) not in aids:
            aids.append(m.group(1))
    got, tries = have, []
    for c in range(0, len(aids), 20):
        if got >= q:
            break
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"id_list": ",".join(aids[c:c + 20]), "max_results": "20"})
        recs = bh._arxiv_parse(bh.http_get(url, accept="application/atom+xml"))
        for r in sorted(recs, key=lambda r: aids.index(r["id"]) if r["id"] in aids else len(aids)):
            if got >= q:
                break
            why = None
            if r["doi"] or r["journal_ref"]:
                why = "arXiv record has a DOI or journal reference"
            elif f"arxiv:{r['id']}" in prior_records or f"arxiv:{r['id']}" in prior_sampled:
                why = "record in an earlier set"
            elif bh.norm(r["title"]) in prior_titles:
                why = "title in an earlier set"
            elif len(r["title"].split()) < 4:
                why = "short title"
            tries.append({"arxiv": r["id"], "skip": why})
            if why:
                continue
            meta = bh.meta_from_arxiv(r)
            items.append({"registry": "arxiv", "ident": r["id"], "field": field, "entry_type": "misc",
                          "n_authors": len(meta["authors"]), "meta": meta, "stratum": "arxiv"})
            got += 1
    log[f"arxiv-topup:{field}"] = {"filter": L["filter"], "seed": SEED, "sampled": len(pool),
                                   "ids_from": "landing-page URL", "tried": tries}
    print("arxiv topup", field, "now", got, "of", q, "tried", len(tries), flush=True)

DBLP_NAMES = {"nips": ("NeurIPS", "NIPS"), "corl": ("CoRL",)}
rng = random.Random(SEED)
for venue, slug in (("NeurIPS", "nips"), ("CoRL", "corl")):
    if any(it["stratum"] == "dblp" and it["ident"].startswith(f"conf/{slug}/") for it in items):
        continue
    years_tried = [log[f"dblp:{venue}"]["year"]]
    year, keys, attempt = years_tried[0], [], 0
    while True:
        names = " ".join(f'"{n}"' for n in DBLP_NAMES[slug])
        q = bh._DBLP_PREFIX + (f'SELECT ?p WHERE {{ VALUES ?v {{ {names} }} ?p dblp:publishedIn ?v ; '
                               f'dblp:yearOfPublication ?y . FILTER(STR(?y)="{year}") '
                               f'FILTER(STRSTARTS(STR(?p), "https://dblp.org/rec/conf/{slug}/")) '
                               f'FILTER NOT EXISTS {{ ?p dblp:doi ?d }} }} LIMIT 5000')
        keys = sorted(r["p"].replace("https://dblp.org/rec/", "") for r in bh.dblp_sparql(q))
        if keys or attempt >= 3:
            break
        attempt += 1
        year = str(rng.choice([y for y in range(2016, 2024) if str(y) not in years_tried]))
        years_tried.append(year)
    order = list(keys)
    rng.shuffle(order)
    tries, got = [], 0
    for key in order[:6]:
        if f"dblp:{key}" in prior_records or f"dblp:{key}" in prior_sampled:
            tries.append({"dblp": key, "skip": "record in an earlier set"})
            continue
        r = bh.dblp_record(key)
        why = None
        if r.get("doi"):
            why = "has DOI"
        elif bh.norm(r["title"]) in prior_titles:
            why = "title in an earlier set"
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
    log[f"dblp-topup:{venue}"] = {"year": year, "years_tried": years_tried, "venue_names": list(DBLP_NAMES[slug]),
                                  "n_keys": len(keys), "tried": tries}
    print("dblp topup", venue, "years", years_tried, "keys", len(keys), "got", got, flush=True)

(WORK / "real_cands.json").write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
(WORK / "real_items_raw.json").write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
print("total", len(items))
