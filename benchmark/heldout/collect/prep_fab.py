"""Write raw/fabricated.json from the reviewed candidates: registry checks, arXiv checks, hand review and
the quoted-title web search. Applies the final automatic filters and records what was checked.

usage: python3 -I collect/prep_fab.py CANDS.json
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

cands = json.load(open(sys.argv[1], encoding="utf-8"))
checks = json.load(open(HERE / "work" / "fab_checks.json", encoding="utf-8"))
arx = json.load(open(HERE / "work" / "fab_arxiv.json", encoding="utf-8"))
dec = json.load(open(HERE / "work" / "fab_decisions.json", encoding="utf-8"))
web = json.load(open(HERE / "work" / "fab_web.json", encoding="utf-8"))
FIELD_FIX = {"773": "other"}
FIXES = {  # hand repairs of the transcription and hand spot-checks, keyed by candidate
    "568": {"parsed": {"doi": ""}, "drop_check": "doi",
            "transcription_note": "the DOI in the source string is split by a line break and resolves in neither "
                                  "reading (10.1287/opre.48.6.836.1238 or 10.1287/opre.48.6.836.12382), so it is left out",
            "manual_check": "Crossref has no Operations Research 48(6) article starting at page 836: pages 833-845 are "
                            "'Free-Flight and en Route Air Safety: A First-Order Analysis' (10.1287/opre.48.6.833.12394) "
                            "and pages 846-857 are 'A Relational Modeling System for Linear and Integer Programming'."},
    "805": {"manual_check": "the arXiv ID belongs to a real paper on a related topic (strategic deception by LLMs) with a "
                            "different title and different authors, so a checker that resolves the ID finds a real but "
                            "different work."},
}
CHECKED, WEB_DATE = "2026-10-24", "2026-10-24"


def split_name(full):
    full = re.sub(r"^\s*(?:\[\d+\]|\d+[.)]|-)\s*", "", full).strip().strip(".").strip()
    if " " in full:
        return bh._split_name(full)
    return {"family": full, "given": ""}


def clean_venue(v):
    v = re.sub(r"\s*URL\s+\S+.*$", "", v.strip())
    v = re.sub(r"\s*https?://\S+", "", v)
    v = re.sub(r"\s*doi:\s*\S*(\s+\S+)?", "", v, flags=re.I)
    return v.strip().rstrip(".;").strip()


def to_meta(p, vtype):
    meta = {"registry": "fabricated", "title": p["title"].strip(), "subtitle": "",
            "authors": [split_name(a) for a in p["authors"]], "year": p["year"],
            "container": "", "short_container": "", "volume": "", "number": "", "pages": "",
            "publisher": "", "doi": p.get("doi", "").rstrip(".;"), "isbn": ""}
    if p.get("et_al"):
        meta["et_al"] = True
    v = clean_venue(p.get("venue_raw", ""))
    raw = p["raw"]
    if vtype == "arxiv":
        m = re.search(r"arXiv preprint arXiv:\s*(\d{4}\.\d{4,5})", raw, re.I)
        if m:
            meta["bibtype"] = "article"
            meta["container"] = f"arXiv preprint arXiv:{m.group(1)}"
        elif p.get("arxiv"):
            meta["bibtype"] = "misc"
            meta["arxiv"] = p["arxiv"]
        else:
            meta["bibtype"] = "misc"
            meta["note"] = "arXiv preprint"
        return meta
    pm = re.search(r"(?:pages|pp\.?)\s*([\dA-Za-z]+\s*[-–—]+\s*[\dA-Za-z]+|\d+)", v)
    if vtype == "proceedings" and not v.startswith("In ") and re.search(r"\d+\s*\(\d+\)\s*:\s*\d+", v):
        vtype = "journal"  # e.g. 'Transactions of the ACL, 12(3):215-229' is a journal citation
    if vtype == "proceedings":
        meta["bibtype"] = "inproceedings"
        if pm:
            meta["pages"] = pm.group(1)
            v = v[:pm.start()].rstrip(" ,.")
        v = re.sub(r"^In\s+", "", v)
        v = re.sub(r",?\s*\b(19|20)\d{2}[a-z]?\b\.?$", "", v).strip(" ,.")
        pubm = re.search(r"[.,]\s*(Association for Computational Linguistics|IEEE|ACM|Springer|PMLR|AAAI Press)\.?$", v)
        if pubm:
            meta["publisher"] = pubm.group(1)
            v = v[:pubm.start()].strip(" ,.")
        meta["container"] = v
        return meta
    meta["bibtype"] = "article"
    jm = re.match(r"^(.*?)[,\s]+(\d+)\s*(?:\(([\w\-–]+)\))?\s*[:,]\s*([\w]+(?:\s*[-–—]+\s*\w+)?)", v)
    if jm and jm.group(1):
        meta["container"] = jm.group(1).strip(" ,")
        meta["volume"] = jm.group(2)
        meta["number"] = jm.group(3) or ""
        meta["pages"] = jm.group(4)
    else:
        meta["container"] = re.sub(r",?\s*\b(19|20)\d{2}[a-z]?\b\.?$", "", v).strip(" ,.")
    meta["pages"] = re.sub(r"^(19|20)\d{2}$", "", meta["pages"])
    return meta


def contained(a, b):
    a, b = bh.norm(a), bh.norm(b)
    return len(a) >= 20 and len(b) >= 20 and (a in b or b in a)


def surnames(names):
    return {bh.norm(n).split()[-1] for n in names if bh.norm(n)}


def row_of(c):
    if c["src"] == "hallucitation-acl2026":
        m = re.search(r"Table (\d+) row (\d+)", c["loc"])
        return f"table{m.group(1)}:row{m.group(2)}"
    return c["citing"].replace("openreview:", "")


items, dropped = [], {}
order = sorted((k for k, d in dec.items() if d.get("keep")), key=lambda k: (cands[int(k)]["src"] != "hallucitation-acl2026", int(k)))
for k in order:
    c, v = cands[int(k)], checks[k]
    p = c["p"]
    title = p["title"]
    if k not in arx or any("error" in h for h in arx[k]):
        dropped[k] = "arXiv check missing"
        continue
    hits = [h for h in arx[k] if not h.get("by_id")]
    tw = bh.norm(title).split()
    if any(h["sim"] >= 0.70 or contained(title, h["title"]) or (len(tw) >= 5 and bh.norm(h["title"]).split()[:5] == tw[:5])
           for h in hits):
        dropped[k] = "arXiv title search found a match"
        continue
    byid = [h for h in arx[k] if h.get("by_id")]
    if byid and byid[0]["title"] and (byid[0]["sim"] >= 0.5 or surnames(byid[0].get("authors", [])) & surnames(p["authors"])):
        dropped[k] = f"arXiv ID {byid[0]['id']} is a related real paper ('{byid[0]['title']}')"
        continue
    doi_hits = v.get("doi", [])
    if doi_hits and doi_hits[0].get("title") and (doi_hits[0]["sim"] >= 0.5 or
                                                    set(bh.norm(a) for a in doi_hits[0].get("authors", []) if a) &
                                                    surnames(p["authors"])):
        dropped[k] = f"DOI {doi_hits[0]['id']} is a related real work"
        continue
    summary = {}
    for reg in ("crossref", "openalex", "dblp"):
        hs = [h for h in v.get(reg, []) if "sim" in h]
        b = max(hs, key=lambda h: h["sim"], default={"sim": 0.0, "title": "", "id": ""})
        summary[reg] = {"best_sim": b["sim"], "best_title": b["title"], "best_id": b.get("id", "")}
    b = max(hits, key=lambda h: h["sim"], default={"sim": 0.0, "title": "", "id": ""})
    summary["arxiv"] = {"best_sim": b["sim"], "best_title": b["title"], "best_id": b.get("id", "")}
    if byid:
        summary["arxiv_id"] = {"id": byid[0]["id"], "title": byid[0]["title"], "sim": byid[0]["sim"]}
    if doi_hits:
        summary["doi"] = {"id": doi_hits[0]["id"], "title": doi_hits[0]["title"], "sim": doi_hits[0]["sim"]}
    if c["src"] == "hallucitation-acl2026":
        m = re.search(r"Table (\d+) row (\d+)", c["loc"])
        row = f"table{m.group(1)}:row{m.group(2)}"
        loc = f"HalluCitation (ACL 2026), Table {m.group(1)} row {m.group(2)}"
        cited = f"ACL Anthology paper {c['citing']}"
    else:
        row = c["citing"].replace("openreview:", "")
        loc = "the CiteTracer ICLR 2026 set (desk-reject comments)"
        cited = f"OpenReview submission {row}"
    meta = to_meta(p, c["vtype"])
    fx = FIXES.get(k, {})
    meta.update(fx.get("parsed", {}))
    if fx.get("drop_check"):
        summary.pop(fx["drop_check"], None)
    extra = {f: fx[f] for f in ("transcription_note", "manual_check") if f in fx}
    items.append({**extra, "source": c["src"], "location": loc, "cited_in": cited, "row": row, "raw": c["text"],
                  "parsed": meta, "field": FIELD_FIX.get(k, dec[k]["field"]), "checked": CHECKED,
                  "checks": summary, "web": {"date": WEB_DATE, "query": f'"{title}"', "result": web[k]["result"]},
                  "candidate": k})
for n, it in enumerate(items, 1):
    it["n"] = n
rejected = {k: d["why"] for k, d in dec.items() if not d.get("keep")}
rejected.update(dropped)
doc = {"description": "Hallucinated references for the held-out set, from the HalluCitation tables (CC BY 4.0) and "
                      "the CiteTracer ICLR 2026 set (MIT). 'raw' is the printed reference string; 'parsed' is our "
                      "transcription; 'checks' are our registry title searches; 'web' is the quoted-title web search.",
       "items": items,
       "rejected_after_registry_checks": [{"source": cands[int(k)]["src"], "row": row_of(cands[int(k)]),
                                           "title": cands[int(k)]["p"]["title"], "why": w}
                                          for k, w in sorted(rejected.items(), key=lambda kv: int(kv[0]))]}
(HERE / "raw" / "fabricated.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(items), "kept;", len(dropped), "dropped at the final filters:", dropped)
