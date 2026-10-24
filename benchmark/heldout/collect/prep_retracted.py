"""Write raw/retracted.json from the confirmed Retraction Watch picks (numbering, curated title fixes, styles).

usage: python3 -I collect/prep_retracted.py
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

items = json.load(open(HERE / "work" / "retracted_items_raw.json", encoding="utf-8"))
rng = random.Random(bh.SEED * 10 + 2)
out = []
for n, rec in enumerate(items, 1):
    rec = dict(rec)
    rec["n"] = n
    t = rec["meta"]["title"]
    if t.lower().startswith("rectracted:"):
        rec["overrides"] = {"title": t.split(":", 1)[1].strip()}
    elif t.startswith("N -("):
        rec["overrides"] = {"title": "N-(" + t[4:]}
    style = []
    if len(rec["meta"]["authors"]) > 4 and rng.random() < 0.5:
        style.append("and_others")
    if rng.random() < 0.3:
        style.append("initials")
    m = rec["meta"]
    if m.get("short_container") and bh.norm(m["short_container"]) != bh.norm(m["container"]) and rng.random() < 0.3:
        style.append("abbrev_journal")
    rec["style"] = style
    out.append(rec)
doc = {"description": "Retracted papers for the held-out set: Retraction Watch rows (RetractionNature 'Retraction') whose "
                      "Crossref record lists the same notice in updated-by. 'meta' is the Crossref metadata; 'overrides' "
                      "are curated fixes applied at build time; 'rw' copies facts from the Retraction Watch row.",
       "retrieved": "2026-10-24", "rw_snapshot": "Retraction Watch data generated 2026-10-22",
       "items": out}
(HERE / "raw" / "retracted.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(out), [r.get("overrides") for r in out if r.get("overrides")])
