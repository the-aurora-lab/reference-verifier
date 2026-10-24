"""Write raw/dev_fingerprints.json: what the development benchmark contains, so the held-out set can avoid it.

usage: python3 -I collect/dev_fingerprints.py DEV_BENCHMARK_DIR [DEV_DECISIONS.json DEV_CANDS.json]
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

dev = Path(sys.argv[1])
items = [json.loads(l) for l in open(dev / "data" / "benchmark.jsonl", encoding="utf-8")]
dois, titles, keys = set(), set(), set()
for it in items:
    _, key, f = bh.parse_bibtex(it["bibtex"])
    keys.add(key)
    if f.get("doi"):
        dois.add(f["doi"].strip().lower())
    titles.add(bh.norm(f.get("title", "")))
raw = dev / "data" / "raw"
real = json.load(open(raw / "real.json", encoding="utf-8"))["items"]
fab = json.load(open(raw / "fabricated.json", encoding="utf-8"))["items"]
ret = json.load(open(raw / "retracted.json", encoding="utf-8"))["items"]
for r in real + ret:
    m = r["meta"]
    if m.get("doi"):
        dois.add(m["doi"].lower())
    titles.add(bh.norm(m["title"]))
    titles.add(bh.norm(bh._RETRACTED_PREFIX.sub("", m["title"])))
idents = sorted({f"{r['registry']}:{r['ident']}" for r in real})
hc_rows, ct_subs, raw_strings = set(), set(), set()
for r in fab:
    titles.add(bh.norm(r["parsed"]["title"]))
    raw_strings.add(bh.norm(r["raw"]))
    if r["source"] == "hallucitation-acl2026":
        m = re.search(r"Table (\d+) row (\d+)", r["location"])
        hc_rows.add(f"table{m.group(1)}:row{m.group(2)}")
    elif r["source"] == "citetracer-iclr2026":
        ct_subs.add(r["cited_in"].replace("OpenReview submission ", "").strip())
rw_ids = sorted({r["rw"]["record_id"] for r in ret})
notice_dois = sorted({r["notice_doi"].lower() for r in ret})
# candidates the dev build reviewed by hand (kept or rejected): never reuse them
reviewed = []
if len(sys.argv) > 3:  # DECISIONS.json CANDS.json from the dev build's scratch: record the reviewed rows
    dec = json.load(open(sys.argv[2], encoding="utf-8"))
    cands = json.load(open(sys.argv[3], encoding="utf-8"))
    for k in dec:
        src, idx = k.rsplit(":", 1)
        if src == "ansari2026-neurips2025":
            continue
        c = cands[int(idx)]
        if src == "hallucitation-acl2026":
            m = re.search(r"Table (\d+) row (\d+)", c["loc"])
            reviewed.append(f"{src}:table{m.group(1)}:row{m.group(2)}")
        else:
            reviewed.append(f"{src}:{c['citing'].replace('openreview:', '')}:{bh.norm(c['p']['title'])}")
    reviewed = sorted(set(reviewed))
out = {
    "description": "Fingerprints of the development benchmark (342 items). The held-out set must share none of "
                   "these DOIs, normalised titles, registry records, compilation rows, CiteTracer submissions or "
                   "Retraction Watch records.",
    "n_items": len(items),
    "dois": sorted(dois),
    "norm_titles": sorted(t for t in titles if t),
    "registry_records": idents,
    "hallucitation_rows": sorted(hc_rows),
    "citetracer_submissions": sorted(ct_subs),
    "fabricated_raw_norm": sorted(raw_strings),
    "dev_reviewed_candidates": reviewed,
    "retraction_watch_records": rw_ids,
    "retraction_notice_dois": notice_dois,
    "bibtex_keys": sorted(keys),
}
(HERE / "raw" / "dev_fingerprints.json").write_text(json.dumps(out, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
print({k: len(v) for k, v in out.items() if isinstance(v, list)})
