"""arXiv checks for the shortlisted fabricated candidates: a keyword title search, an exact-phrase title
search, and resolution of any arXiv ID the reference gives. Resumable; writes work/fab_arxiv.json.

usage: python3 -I collect/fab_arxiv.py CANDS.json
"""
import json
import os
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

bh._MIN_INTERVAL["export.arxiv.org"] = 4.0
cands = json.load(open(sys.argv[1], encoding="utf-8"))
OUTP = HERE / "work" / "fab_arxiv.json"
if not OUTP.exists():
    OUTP.write_text("{}")
dec = json.load(open(HERE / "work" / "fab_decisions.json", encoding="utf-8"))


def phrase(title):
    words = bh.norm(title).split()
    q = f'ti:"{" ".join(words)}"'
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": q, "max_results": "10"})
    return bh._arxiv_parse(bh.http_get(url, accept="application/atom+xml"))


for k, d in dec.items():
    if not d.get("keep"):
        continue
    res = json.load(open(OUTP, encoding="utf-8"))
    if k in res and not any("error" in h for h in res[k]):
        continue
    p = cands[int(k)]["p"]
    title = p["title"]
    try:
        hits = [{"title": it["title"], "id": it["id"], "sim": round(bh.title_sim(title, it["title"]), 3)}
                for it in bh.arxiv_search_title(title, rows=5)]
        hits += [{"title": it["title"], "id": it["id"], "phrase": True, "sim": round(bh.title_sim(title, it["title"]), 3)}
                 for it in phrase(title)[:5]]
        if p.get("arxiv"):
            r = bh.arxiv_by_id(p["arxiv"])
            hits.append({"title": r["title"] if r else "", "id": p["arxiv"], "by_id": True,
                         "authors": (r or {}).get("authors", [])[:8],
                         "sim": round(bh.title_sim(title, r["title"]), 3) if r else 0.0})
    except Exception as exc:  # noqa: BLE001
        hits = [{"error": f"{type(exc).__name__}: {exc}"[:200]}]
    res[k] = hits
    tmp = str(OUTP) + ".arx.tmp"
    json.dump(res, open(tmp, "w"), indent=0, ensure_ascii=False)
    os.replace(tmp, OUTP)
    best = max((h.get("sim", 0) for h in hits if not h.get("by_id")), default=0)
    print(k, "arxiv best", best, "by_id" if p.get("arxiv") else "", flush=True)
print("done")
