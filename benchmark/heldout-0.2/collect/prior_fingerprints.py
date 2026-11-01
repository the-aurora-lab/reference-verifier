"""Write raw/prior_fingerprints.json: what the development set and the 0.1 held-out set contain or checked,
so that the 0.2 held-out set can avoid all of it and `build_heldout.py --validate` can prove it.

usage: python3 -I collect/prior_fingerprints.py CANDS.json DEV_CHECKS.json DEV_DECISIONS.json DEV_RET_SAMPLE.json

CANDS.json is the list of 1,699 reference strings parsed from the two hallucination compilations by the
development build (the same list the 0.1 held-out build drew from); DEV_CHECKS.json, DEV_DECISIONS.json and
DEV_RET_SAMPLE.json are the development build's registry-check log, hand-review decisions and Retraction Watch
sample. None of them is redistributed. The two benchmark sets are read from ../data/ and ../heldout/.

The 0.1 held-out build did not keep its registry-check log, only the candidates it reviewed (raw/fabricated.json
there). Its candidate order is reproduced here from its published rules (same eligibility, random.Random(20261024),
a journal-first second pass) and a superset of what it can have checked is recorded: the first 300 non-journal
candidates in its order plus every journal-style candidate it could draw (it checked 291 in total, and both of its
passes keep the non-journal candidates in the same relative order).
"""
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
BENCH = HERE.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

cands = json.load(open(sys.argv[1], encoding="utf-8"))
dev_checks = json.load(open(sys.argv[2], encoding="utf-8"))
dev_dec = json.load(open(sys.argv[3], encoding="utf-8"))
dev_ret_sample = json.load(open(sys.argv[4], encoding="utf-8"))


def row_id(c: dict) -> str:
    if c["src"] == "hallucitation-acl2026":
        m = re.search(r"Table (\d+) row (\d+)", c["loc"])
        return f"table{m.group(1)}:row{m.group(2)}"
    return c["citing"].replace("openreview:", "")


def cand_key(src: str, row: str, title: str) -> str:
    """HalluCitation rows hold one reference each; a CiteTracer submission can hold several."""
    return f"{src}:{row}" if src == "hallucitation-acl2026" else f"{src}:{row}:{bh.norm(title)}"


def key_of(i: int) -> str:
    c = cands[i]
    return cand_key(c["src"], row_id(c), (c.get("p") or {}).get("title", ""))


def bench_fingerprints(jsonl: Path, raw: Path) -> dict:
    items = [json.loads(line) for line in open(jsonl, encoding="utf-8")]
    dois, titles, keys = set(), set(), set()
    for it in items:
        _, key, f = bh.parse_bibtex(it["bibtex"])
        keys.add(key)
        if f.get("doi"):
            dois.add(f["doi"].strip().lower())
        titles.add(bh.norm(f.get("title", "")))
    real = json.load(open(raw / "real.json", encoding="utf-8"))["items"]
    fab = json.load(open(raw / "fabricated.json", encoding="utf-8"))
    ret = json.load(open(raw / "retracted.json", encoding="utf-8"))["items"]
    for r in real + ret:
        m = r["meta"]
        if m.get("doi"):
            dois.add(m["doi"].lower())
        titles.add(bh.norm(m["title"]))
        titles.add(bh.norm(bh._RETRACTED_PREFIX.sub("", m["title"])))
    hc_rows, ct_subs, raw_strings, used = set(), set(), set(), set()
    for r in fab["items"]:
        titles.add(bh.norm(r["parsed"]["title"]))
        raw_strings.add(bh.norm(r["raw"]))
        if r["parsed"].get("doi"):
            dois.add(r["parsed"]["doi"].lower())
        if r["source"] == "hallucitation-acl2026":
            m = re.search(r"Table (\d+) row (\d+)", r["location"])
            row = f"table{m.group(1)}:row{m.group(2)}"
            hc_rows.add(row)
        elif r["source"] == "citetracer-iclr2026":
            row = r["cited_in"].replace("OpenReview submission ", "").strip()
            ct_subs.add(row)
        else:
            continue
        used.add(cand_key(r["source"], row, r["parsed"]["title"]))
    return {
        "n_items": len(items),
        "dois": dois, "norm_titles": {t for t in titles if t}, "bibtex_keys": keys,
        "registry_records": {f"{r['registry']}:{r['ident']}" for r in real},
        "hallucitation_rows": hc_rows, "citetracer_submissions": ct_subs, "fabricated_raw_norm": raw_strings,
        "used_candidates": used,
        "retraction_watch_records": {r["rw"]["record_id"] for r in ret},
        "retraction_notice_dois": {r["notice_doi"].lower() for r in ret},
        "fab": fab,
    }


# ---------------------------------------------------------------- development set
dev = bench_fingerprints(BENCH / "data" / "benchmark.jsonl", BENCH / "data" / "raw")
dev_reviewed = set()
for k in dev_dec:
    src, idx = k.rsplit(":", 1)
    if src not in ("hallucitation-acl2026", "citetracer-iclr2026"):
        continue  # a third compilation the development set used; this set does not draw from it
    c = cands[int(idx)]
    dev_reviewed.add(key_of(int(idx)))
    (dev["hallucitation_rows"] if src == "hallucitation-acl2026" else dev["citetracer_submissions"]).add(row_id(c))
dev_checked_idx = {int(k) for k in dev_checks}
dev["reviewed_candidates"] = dev_reviewed | dev["used_candidates"]
dev["checked_candidates"] = {key_of(i) for i in dev_checked_idx} | dev["reviewed_candidates"]
dev["retraction_watch_checked"] = {r["rw"]["Record ID"] for r in dev_ret_sample} | dev["retraction_watch_records"]
dev["sampled_records"] = set()  # the development set's real items were chosen by hand, not sampled

# ---------------------------------------------------------------- 0.1 held-out set
old = json.load(open(BENCH / "heldout" / "raw" / "dev_fingerprints.json", encoding="utf-8"))
for name in ("dois", "norm_titles", "bibtex_keys", "registry_records", "fabricated_raw_norm",
             "retraction_watch_records", "retraction_notice_dois"):  # same fingerprints as the 0.1 build computed
    assert set(old[name]) <= dev[name], name
ho = bench_fingerprints(BENCH / "heldout" / "heldout.jsonl", BENCH / "heldout" / "raw")
by_key = {}
for i, c in enumerate(cands):
    if c.get("p"):
        by_key.setdefault((c["src"], row_id(c), c["p"]["title"]), []).append(i)
ho_reviewed_idx = [int(r["candidate"]) for r in ho["fab"]["items"]]
for r in ho["fab"]["rejected_after_registry_checks"]:
    (i,) = by_key[(r["source"], r["row"], r["title"])]
    ho_reviewed_idx.append(i)
    (ho["hallucitation_rows"] if r["source"] == "hallucitation-acl2026" else ho["citetracer_submissions"]).add(r["row"])
ho["reviewed_candidates"] = {key_of(i) for i in ho_reviewed_idx} | ho["used_candidates"]

# reproduce the 0.1 build's candidate order (collect/fab_check.py there)
reviewed_rows_01 = set(old["dev_reviewed_candidates"])
elig = []
for i, c in enumerate(cands):
    if i in dev_checked_idx or c.get("vtype") == "none":
        continue
    p = c["p"]
    if not p or not p.get("title") or len(bh.norm(p["title"]).split()) < 4 or not p.get("authors"):
        continue
    rid = row_id(c)
    if f"{c['src']}:{rid}" in reviewed_rows_01 or f"{c['src']}:{rid}:{bh.norm(p['title'])}" in reviewed_rows_01:
        continue
    if c["src"] == "hallucitation-acl2026" and rid in set(old["hallucitation_rows"]):
        continue
    if c["src"] == "citetracer-iclr2026" and rid in set(old["citetracer_submissions"]):
        continue
    if bh.norm(p["title"]) in set(old["norm_titles"]) or bh.norm(c["text"]) in set(old["fabricated_raw_norm"]):
        continue
    elig.append(i)
random.Random(20261024).shuffle(elig)
assert all(i in set(elig) for i in ho_reviewed_idx), "0.1 candidate order not reproduced"
non_journal = [i for i in elig if cands[i].get("vtype") != "journal"]
superset = set(non_journal[:300]) | {i for i in elig if cands[i].get("vtype") == "journal"}
assert set(ho_reviewed_idx) <= superset
ho["checked_candidates"] = {key_of(i) for i in superset} | ho["reviewed_candidates"]
ho_ret_log = json.load(open(BENCH / "heldout" / "raw" / "retracted_sampling.json", encoding="utf-8"))["tried"]
ho["retraction_watch_checked"] = {t["record"] for t in ho_ret_log} | ho["retraction_watch_records"]
ho_real_log = json.load(open(BENCH / "heldout" / "raw" / "real_sampling.json", encoding="utf-8"))["strata"]
sampled = set()
for log in ho_real_log.values():
    for t in log["tried"]:
        if t.get("doi"):
            sampled.add(f"doi:{t['doi'].lower()}")
        if t.get("openalex"):
            sampled.add(f"openalex:{t['openalex'].rsplit('/', 1)[-1]}")
        if t.get("arxiv"):
            sampled.add(f"arxiv:{t['arxiv']}")
        if t.get("dblp"):
            sampled.add(f"dblp:{t['dblp']}")
ho["sampled_records"] = sampled

FIELDS_OUT = ("dois", "norm_titles", "registry_records", "sampled_records", "hallucitation_rows",
              "citetracer_submissions", "fabricated_raw_norm", "reviewed_candidates", "checked_candidates",
              "retraction_watch_records", "retraction_watch_checked", "retraction_notice_dois", "bibtex_keys")
out = {
    "description": (
        "Fingerprints of the two earlier sets: the development benchmark (data/benchmark.jsonl) and the 0.1 held-out "
        "set (heldout/heldout.jsonl). The 0.2 held-out set must share none of these DOIs, normalised titles, "
        "registry records (including records the 0.1 sampling looked at and skipped), HalluCitation rows or "
        "CiteTracer submissions that either set used or reviewed, compilation candidates either build checked "
        "(for 0.1, a reconstructed superset), reference strings, Retraction Watch records (used or looked at), "
        "notice DOIs or BibTeX keys. Candidate keys are 'source:table:row' for HalluCitation and "
        "'source:submission:normalised title' for CiteTracer."),
    "sets": {},
}
for name, fp in (("dev", dev), ("heldout-0.1", ho)):
    out["sets"][name] = {"n_items": fp["n_items"], **{k: sorted(fp[k]) for k in FIELDS_OUT}}
(HERE / "raw" / "prior_fingerprints.json").write_text(json.dumps(out, indent=0, ensure_ascii=False) + "\n",
                                                      encoding="utf-8")
for name, s in out["sets"].items():
    print(name, {k: (len(v) if isinstance(v, list) else v) for k, v in s.items()})
