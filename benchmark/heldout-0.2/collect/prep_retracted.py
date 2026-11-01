"""Write raw/retracted.json and raw/retracted_sampling.json from the confirmed Retraction Watch picks
(numbering, curated fixes, styles).

usage: HELDOUT_WORK=DIR python3 -I collect/prep_retracted.py
"""
import html
import json
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

WORK = Path(os.environ.get("HELDOUT_WORK", HERE / "work"))
items = json.load(open(WORK / "retracted_items_raw.json", encoding="utf-8"))
log = json.load(open(WORK / "retracted_log.json", encoding="utf-8"))
TITLE_FIX = {  # titles Crossref stores in capitals or with a retraction prefix the generic rule does not catch
    "10.1017/jsl.2017.4": "Measuring club-sequences together with the continuum large",
    "10.1111/1745-9125.12176": "Lynchings, Racial Threat, and Whites’ Punitive Views Toward Blacks",
    "10.1111/j.1477-4658.2009.00603.x": "Conscience in Renaissance moral thought: a concept in transition?",
}
VOLUME_FIX = {"10.2147/ott.s232542": "13"}  # Crossref gives the volume as 'Volume 13'
rng = random.Random(bh.SEED)


def fix_caps(name: str) -> str:
    """'ASPERÓ' -> 'Asperó': surnames that Crossref stores in capitals, written as an author would."""
    return name.title() if len(name) > 1 and name.upper() == name and any(c.isalpha() for c in name) else name


out = []
for n, rec in enumerate(items, 1):
    rec = dict(rec)
    rec["n"] = n
    m = rec["meta"]
    ov, notes = {}, []
    doi = m["doi"].lower()
    if doi in TITLE_FIX:
        ov["title"] = TITLE_FIX[doi]
    if doi in VOLUME_FIX:
        ov["volume"] = VOLUME_FIX[doi]
        notes.append(f"Registry value corrected: volume given as '{VOLUME_FIX[doi]}' (Crossref: '{m['volume']}').")
    if m.get("short_container") and html.unescape(m["short_container"]) != m["short_container"]:
        ov["short_container"] = html.unescape(m["short_container"])
    authors = [dict(a, **{k: fix_caps(a[k]) for k in ("given", "family") if a.get(k)}) for a in m["authors"]]
    if authors != m["authors"]:
        ov["authors"] = authors
        notes.append("Author names that Crossref stores in capitals are written in normal case.")
    if ov:
        rec["overrides"] = ov
    if notes:
        rec["extra_note"] = " ".join(notes)
    style = []
    if len(m["authors"]) > 4 and rng.random() < 0.5:
        style.append("and_others")
    if rng.random() < 0.3:
        style.append("initials")
    if m.get("short_container") and bh.norm(m["short_container"]) != bh.norm(m["container"]) and rng.random() < 0.3:
        style.append("abbrev_journal")
    rec["style"] = style
    out.append(rec)
doc = {"description": "Retracted papers for the 0.2 held-out set: Retraction Watch rows (RetractionNature 'Retraction') "
                      "whose Crossref record lists the same notice in updated-by. 'meta' is the Crossref metadata; "
                      "'overrides' are curated fixes applied at build time; 'rw' copies facts from the Retraction "
                      "Watch row.",
       "retrieved": "2026-11-01", "rw_snapshot": "Retraction Watch data generated 2026-10-30",
       "items": out}
(HERE / "raw" / "retracted.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
(HERE / "raw" / "retracted_sampling.json").write_text(json.dumps(
    {"description": "Retraction Watch rows tried, in sampling order, and why any were skipped (Crossref check).",
     "tried": log}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(out), [(r["meta"]["doi"], r.get("overrides")) for r in out if r.get("overrides")])
