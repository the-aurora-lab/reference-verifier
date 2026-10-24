"""Top up the arXiv-only stratum (the first sample found too few records without a DOI or journal reference).

usage: python3 -I collect/real_arxiv_topup.py   (appends to work/real_items_raw.json)
"""
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

SEED = 20261024
bh._MIN_INTERVAL["export.arxiv.org"] = 5.0
KEY = os.environ["OPENALEX_API_KEY"]
fp = json.load(open(HERE / "raw" / "dev_fingerprints.json", encoding="utf-8"))
dev_titles = set(fp["norm_titles"])
items = json.load(open(HERE / "work" / "real_items_raw.json", encoding="utf-8"))
have = {it["ident"] for it in items}
log = json.load(open(HERE / "work" / "real_cands.json", encoding="utf-8"))
QUOTA = {"cs": ("17", 1), "math": ("26", 1), "social": ("20|33|32", 1)}
for k, (field, (ids, q)) in enumerate(QUOTA.items()):
    filt = (f"primary_location.source.id:S4306400194,locations_count:1,publication_year:2014-2024,"
            f"cited_by_count:>2,primary_topic.field.id:{ids}")
    params = {"filter": filt, "sample": "120", "seed": str(SEED + 300 + k), "per-page": "120",
              "select": "id,doi,title", "api_key": KEY}
    pool = bh.get_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))["results"]
    aids = []
    for w in pool:
        m = re.search(r"10\.48550/arxiv\.(\d{4}\.\d{4,5})$", w.get("doi") or "", re.I)
        if m and m.group(1) not in have:
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
        elif bh.norm(r["title"]) in dev_titles or len(r["title"].split()) < 4:
            why = "dev title or short title"
        tries.append({"arxiv": r["id"], "skip": why})
        if why:
            continue
        meta = bh.meta_from_arxiv(r)
        items.append({"registry": "arxiv", "ident": r["id"], "field": field, "entry_type": "misc",
                      "n_authors": len(meta["authors"]), "meta": meta, "stratum": "arxiv"})
        got += 1
    log[f"arxiv-topup:{field}"] = {"filter": filt, "seed": SEED + 300 + k, "sampled": len(pool), "tried": tries}
    print(field, "got", got, "of", q, "tried", len(tries), flush=True)
(HERE / "work" / "real_items_raw.json").write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
(HERE / "work" / "real_cands.json").write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
