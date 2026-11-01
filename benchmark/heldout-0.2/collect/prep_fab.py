"""Write raw/fabricated.json from the reviewed candidates: registry checks, arXiv checks, hand review and
the quoted-title web search. Applies the final automatic filters, keeps the first TARGET candidates that pass
every step in review order (the random order of collect/fab_check.py), and records what was checked.

usage: HELDOUT_WORK=DIR python3 -I collect/prep_fab.py CANDS.json
Reads DIR/fab_order.json, fab_checks.json, fab_arxiv.json, fab_decisions.json (hand review) and fab_web.json
(quoted-title web searches).
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

WORK = Path(os.environ.get("HELDOUT_WORK", HERE / "work"))
cands = json.load(open(sys.argv[1], encoding="utf-8"))
review_order = json.load(open(WORK / "fab_order.json", encoding="utf-8"))
checks = json.load(open(WORK / "fab_checks.json", encoding="utf-8"))
arx = json.load(open(WORK / "fab_arxiv.json", encoding="utf-8"))
dec = json.load(open(WORK / "fab_decisions.json", encoding="utf-8"))
web = json.load(open(WORK / "fab_web.json", encoding="utf-8"))
TARGET = bh.TARGETS["fabricated"]
FIELD_FIX = {}
FIXES = {  # hand repairs of the transcription and hand spot-checks, keyed by candidate
    "1229": {"parsed": {"doi": ""}, "drop_check": "doi",
             "transcription_note": "the DOI in the source string is cut off and broken by spaces "
                                   "('10.18653/v1/2022. naacl-main. 1'), so it is left out"},
    "8": {"parsed": {"container": "International Conference on Computational Linguistics (Proceedings of the "
                                  "Conference: Long Papers, 2020)", "publisher": "Association for Computational Linguistics"}},
    "240": {"parsed": {"title": "An efficient multilingual byte-to-byte model for sequence-to-sequence tasks",
                       "container": "Findings of the Association for Computational Linguistics: EMNLP 2022"},
            "transcription_note": "the hyphen of 'sequence-to-sequence', lost at a line break when the table was "
                                  "extracted, is restored"},
    "330": {"parsed": {"container": "Findings of the Association for Computational Linguistics: EMNLP 2023"}},
    "977": {"parsed": {"container": "IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)",
                       "pages": "911-915"},
            "transcription_note": "the page range, printed inside a stray math environment, is moved to the pages field"},
    "1165": {"parsed": {"container": "Advances in Neural Information Processing Systems", "volume": "37"}},
    "1429": {"parsed": {"container": "Proceedings of the 2024 Conference on Empirical Methods in Natural Language "
                                     "Processing (EMNLP)", "publisher": "ACL"}},
    "1430": {"parsed": {"container": "Proceedings of the International Joint Conference on Artificial Intelligence "
                                     "(IJCAI)", "publisher": "IJCAI"}},
    "1533": {"parsed": {"container": "2009 IEEE/WIC/ACM International Joint Conference on Web Intelligence and "
                                     "Intelligent Agent Technology (WI-IAT)", "volume": "3", "publisher": "IEEE"}},
    "758": {"manual_check": "the arXiv ID belongs to a real paper on a related topic (LLM-Adapters, adapters for "
                            "parameter-efficient fine-tuning) with a different title and different authors, so a checker "
                            "that resolves the ID finds a real but different work."},
    "1249": {"manual_check": "the arXiv ID belongs to a real paper on a related topic (Neural Autoregressive Flows) with "
                             "a different title and different authors, so a checker that resolves the ID finds a real but "
                             "different work."},
    "1637": {"manual_check": "Crossref has no Proceedings of the IEEE 112(3) article starting at page 289: that issue "
                             "runs from page 181 to 300, and pages 247-299 are 'Drawing the Boundaries Between "
                             "Blockchain and Blockchain-Like Systems: A Comprehensive Survey' (10.1109/jproc.2024.3386257)."},
}
CHECKED, WEB_DATE = "2026-11-01", "2026-11-01"


def split_name(full):
    full = re.sub(r"^\s*(?:\[\d+\]|\(\d+\)|\d+[.)]|-)\s*", "", full).strip().strip(".").strip()
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


def cand_key(c):
    rid = row_of(c)
    return f"{c['src']}:{rid}" if c["src"] == "hallucitation-acl2026" else f"{c['src']}:{rid}:{bh.norm(c['p']['title'])}"


items, dropped, unchecked = [], {}, []
for k in (str(i) for i in review_order if dec.get(str(i), {}).get("keep")):
    c, v = cands[int(k)], checks[k]
    p = c["p"]
    title = p["title"]
    if k not in arx and len(items) >= TARGET:
        unchecked.append(k)  # the target was met before this candidate's arXiv check was needed
        continue
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
        shared = surnames(byid[0].get("authors", [])) & surnames(p["authors"])
        how = "a similar title" if byid[0]["sim"] >= 0.5 else f"a shared author surname ({', '.join(sorted(shared))})"
        dropped[k] = f"the arXiv ID {byid[0]['id']} belongs to a real paper with {how}: '{byid[0]['title']}'"
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
not_used = [it["candidate"] for it in items[TARGET:]]  # items are in review order here
items = items[:TARGET]
items.sort(key=lambda it: (it["source"] != "hallucitation-acl2026", int(it["candidate"])))
for n, it in enumerate(items, 1):
    it["n"] = n
rejected = {k: d["why"] for k, d in dec.items() if not d.get("keep")}
rejected.update(dropped)
pos = {str(i): n for n, i in enumerate(review_order)}


def entry(k, **extra):
    c = cands[int(k)]
    return {"source": c["src"], "row": row_of(c), "title": c["p"]["title"], **extra}


passes = [str(i) for i in review_order if checks.get(str(i), {}).get("status") == "pass"]
doc = {"description": "Hallucinated references for the 0.2 held-out set, from the HalluCitation tables (CC BY 4.0) and "
                      "the CiteTracer ICLR 2026 set (MIT). 'raw' is the printed reference string; 'parsed' is our "
                      "transcription; 'checks' are our registry title searches; 'web' is the quoted-title web search. "
                      "'rejected_after_registry_checks' lists every candidate that passed the registry filter and was "
                      "rejected at a later step, with the reason; 'passed_not_used' lists candidates that passed every "
                      "step or were not reviewed because the target was already met; 'registry_checked' lists every "
                      "candidate this build checked, in review order, so that later sets can avoid them.",
       "items": items,
       "rejected_after_registry_checks": [entry(k, why=w) for k, w in sorted(rejected.items(), key=lambda kv: pos[kv[0]])],
       "passed_not_used": [entry(k, why="passed every step; not needed, the target was met") for k in not_used]
                          + [entry(k, why="passed the hand review and the web search; arXiv check not run, the target "
                                          "was met") for k in unchecked]
                          + [entry(k, why="passed the registry filter; not reviewed, the target was met")
                             for k in passes if k not in dec],
       "registry_checked": [{"key": cand_key(cands[i]), "status": checks[str(i)]["status"],
                             **({"found_in": checks[str(i)]["found_in"]} if checks[str(i)].get("found_in") else {})}
                            for i in review_order if str(i) in checks]}
(HERE / "raw" / "fabricated.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(items), "kept;", len(dropped), "dropped at the final filters:", dropped)
print(len(not_used), "passed every step but not used;", len(unchecked), "not arXiv-checked (target met);", len([k for k in passes if k not in dec]), "passes not reviewed;",
      len(doc["registry_checked"]), "checked in all")
