"""Existence checks for 0.2 held-out fabricated-reference candidates (staged; resumable).

usage: HELDOUT_WORK=DIR python3 -I collect/fab_check.py CANDS.json [target_passes]
CANDS.json is the parsed candidate list from the HalluCitation tables and the CiteTracer set. Every candidate
that the development build or the 0.1 held-out build checked or reviewed, every HalluCitation row and
CiteTracer submission that either set used or reviewed, and every title or reference string in either set
is skipped (raw/prior_fingerprints.json). Writes DIR/fab_checks.json.
"""
import json
import os
import random
import re
import sys
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

bh._MIN_INTERVAL["api.crossref.org"] = 0.5  # another process may use Crossref at the same time
bh._MIN_INTERVAL["api.openalex.org"] = 0.4
bh._MIN_INTERVAL["sparql.dblp.org"] = float(os.environ.get("DBLP_INTERVAL", "1.0"))
cands = json.load(open(sys.argv[1], encoding="utf-8"))
target = int(sys.argv[2]) if len(sys.argv) > 2 else 150
prior = json.load(open(HERE / "raw" / "prior_fingerprints.json", encoding="utf-8"))["sets"]


def union(name):
    return set().union(*(set(s[name]) for s in prior.values()))


prior_titles, prior_raw = union("norm_titles"), union("fabricated_raw_norm")
prior_hc, prior_ct = union("hallucitation_rows"), union("citetracer_submissions")
prior_checked = union("checked_candidates") | union("reviewed_candidates")
WORK = Path(os.environ.get("HELDOUT_WORK", HERE / "work"))
OUTP = WORK / "fab_checks.json"
res = json.load(open(OUTP)) if OUTP.exists() else {}


def row_id(c):
    if c["src"] == "hallucitation-acl2026":
        m = re.search(r"Table (\d+) row (\d+)", c["loc"])
        return f"table{m.group(1)}:row{m.group(2)}"
    return c["citing"].replace("openreview:", "")


def cand_key(c):
    rid = row_id(c)
    return f"{c['src']}:{rid}" if c["src"] == "hallucitation-acl2026" else f"{c['src']}:{rid}:{bh.norm(c['p']['title'])}"


elig = []
for i, c in enumerate(cands):
    if c.get("vtype") == "none":
        continue
    p = c["p"]
    if not p or not p.get("title") or len(bh.norm(p["title"]).split()) < 4 or not p.get("authors"):
        continue
    rid = row_id(c)
    if cand_key(c) in prior_checked:
        continue
    if c["src"] == "hallucitation-acl2026" and rid in prior_hc:
        continue
    if c["src"] == "citetracer-iclr2026" and rid in prior_ct:
        continue
    if bh.norm(p["title"]) in prior_titles or bh.norm(c["text"]) in prior_raw:
        continue
    elig.append(i)
rng = random.Random(bh.SEED)
rng.shuffle(elig)
(WORK / "fab_order.json").write_text(json.dumps(elig), encoding="utf-8")
if os.environ.get("PRIORITY"):  # second pass: journal-style references first, to reach fields beyond CS
    elig.sort(key=lambda i: cands[i].get("vtype") != os.environ["PRIORITY"])
print("eligible", len(elig), flush=True)


def contained(a, b):
    a, b = bh.norm(a), bh.norm(b)
    return len(a) >= 20 and len(b) >= 20 and (a in b or b in a)


def found(title, hits):
    tw = bh.norm(title).split()
    for h in hits:
        if h.get("by_id"):
            continue
        if h.get("sim", 0) >= 0.70 or contained(title, h.get("title", "")):
            return True
        if len(tw) >= 5 and bh.norm(h.get("title", "")).split()[:5] == tw[:5]:
            return True
    return False


def save():
    tmp = str(OUTP) + ".tmp"
    json.dump(res, open(tmp, "w"), indent=0, ensure_ascii=False)
    os.replace(tmp, OUTP)


def run_reg(reg, p):
    title = p["title"]
    if reg == "crossref":
        first = p["authors"][0] if p["authors"] else ""
        items = bh.crossref_search(f"{title} {first}", rows=5)
        return [{"title": bh.clean_markup((it.get("title") or [""])[0]), "id": it.get("DOI", ""),
                 "sim": round(bh.title_sim(title, (it.get("title") or [""])[0]), 3)} for it in items]
    if reg == "dblp":
        items = bh.dblp_title_search(title, limit=5)
        return [{"title": it["title"], "id": it["key"], "sim": round(bh.title_sim(title, it["title"]), 3)} for it in items]
    if reg == "arxiv":
        items = bh.arxiv_search_title(title, rows=5)
        hits = [{"title": it["title"], "id": it["id"], "sim": round(bh.title_sim(title, it["title"]), 3)} for it in items]
        if p.get("arxiv"):
            r = bh.arxiv_by_id(p["arxiv"])
            hits.append({"title": r["title"] if r else "", "id": p["arxiv"], "by_id": True,
                         "authors": (r or {}).get("authors", [])[:6],
                         "sim": round(bh.title_sim(title, r["title"]), 3) if r else 0.0})
        return hits
    if reg == "openalex":
        items = bh.openalex_search(title, rows=5)
        return [{"title": it.get("title") or "", "id": it.get("id", ""), "doi": it.get("doi") or "",
                 "sim": round(bh.title_sim(title, it.get("title") or ""), 3)} for it in items]
    if reg == "doi":
        try:
            m = bh.crossref_work(p["doi"])
            t = bh.clean_markup((m.get("title") or [""])[0])
            return [{"title": t, "id": p["doi"], "by_id": True, "sim": round(bh.title_sim(title, t), 3),
                     "authors": [a.get("family", "") for a in m.get("author", []) or []][:6]}]
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            return [{"title": "", "id": p["doi"], "by_id": True, "sim": 0.0}]
    raise ValueError(reg)


oa_used = 0  # counted across processes by bh.openalex_get (OPENALEX_COUNTER, OPENALEX_BUDGET)
passes = sum(1 for v in res.values() if v.get("status") == "pass")
order = ["crossref", "dblp", "openalex"]  # arXiv runs later on the reviewed shortlist (its API rate-limits hard)
for n, i in enumerate(elig):
    if passes >= target:
        break
    key = str(i)
    v = res.setdefault(key, {})
    if v.get("status") in ("pass", "found"):
        continue
    p = cands[i]["p"]
    status = None
    regs = order + (["doi"] if p.get("doi") else [])
    for reg in regs:
        if reg not in v:
            try:
                v[reg] = run_reg(reg, p)
            except Exception as exc:  # noqa: BLE001
                if "budget" in str(exc):
                    status = "budget"
                    break
                v[reg] = [{"error": f"{type(exc).__name__}: {exc}"[:200]}]
            if reg == "openalex":
                oa_used += 1
        if any("error" in h for h in v[reg]):
            status = "error"
            break
        if found(p["title"], v[reg]):
            status = "found"
            v["found_in"] = reg
            break
    if status is None:
        status = "pass"
        passes += 1
    v["status"] = status
    if status == "budget":
        print("OpenAlex budget used up; stopping", flush=True)
        break
    if n % 10 == 0:
        save()
        print(n, "checked; passes", passes, "openalex", oa_used, flush=True)
save()
print("done; passes", passes, "openalex searches", oa_used, flush=True)
