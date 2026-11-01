"""Write raw/real.json and raw/real_sampling.json from the sampled records: correct the field label where the
OpenAlex topic misleads, apply curated title fixes, keep the journal articles needed for the target field spread
(in sampling order), number the records, and assign messy-but-valid BibTeX styles with the fixed seed.

usage: HELDOUT_WORK=DIR python3 -I collect/prep_real.py
"""
import json
import os
import random
import sys
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

WORK = Path(os.environ.get("HELDOUT_WORK", HERE / "work"))
items = json.load(open(WORK / "real_items_raw.json", encoding="utf-8"))
log = json.load(open(WORK / "real_cands.json", encoding="utf-8"))
DROP = {  # ident -> reason; records left out after sampling
    "10.2307/2185952": "a book review: the Crossref title is the title of the reviewed book",
}
FIELD_FIX = {  # our reading of the work's subject where the OpenAlex primary topic misleads
    "10.1177/0954406211432066": "other",       # parametric excitation, mechanical engineering journal (was social)
    "10.1007/s11423-008-9103-8": "social",     # educational technology research (was humanities)
    "10.1108/eum0000000006755": "social",      # electronic peer review, information science (was humanities)
    "10.1016/s0022-2836(03)00322-x": "biomed",  # bacteriophage assembly, molecular biology (was other)
    "10.1016/j.gca.2021.06.026": "other",       # meteorite cosmochemistry (was physics)
    "10.1007/978-3-030-23788-2": "math",        # numerical methods for variational problems (was other)
    "1810.03192": "math",                       # statistical regression methodology, stat.ME (was physics)
    "1708.07077": "other",                      # smart materials for tactile actuators (was biomed)
}
OVERRIDES = {  # curated fixes; the registry form is quoted in the item notes
    "10.1088/0953-4075/22/4/008": {"title": r"Electron detachment in Li$^-$-He collisions: coherence study of "
                                            r"Li(2$^2$P) excitation in Li$^-$-He and Li-He collisions"},
    "10.1515/cog-2016-0139": {"title": "Where metaphors really come from: Social factors as contextual influence in "
                                       "Hungarian teenagers’ metaphorical conceptualizations of life"},
    "10.1007/s00125-003-1133-5": {"title": "Identification and purification from the plasma of Type 1 diabetic "
                                           "subjects of a proteolytically active Grp94"},
    "10.1007/bf01294172": {"container": "Zeitschrift für Physik B Condensed Matter"},
    "10.1039/d1ra05063j": {"title": "Ruthenium(IV) N-confused porphyrin μ-oxo-bridged dimers: acid-responsive "
                                    "molecular rotors"},
}
FIELD_NAMES = {"cs": "Computer Science", "biomed": "Medicine, Biochemistry, Neuroscience, Immunology, Pharmacology",
               "physics": "Physics and Astronomy", "math": "Mathematics",
               "social": "Social Sciences, Psychology, Economics, Business", "humanities": "Arts and Humanities",
               "other": "Chemistry, Materials, Earth, Environment, Energy, Engineering, Agriculture"}
rng = random.Random(bh.SEED)


def has_accents(meta):
    text = meta["title"] + " " + " ".join(a.get("given", "") + a.get("family", "") for a in meta["authors"])
    return any(ord(c) > 127 and unicodedata.category(c).startswith("L") for c in text)


# 1. drops and field corrections
recs, dropped = [], []
for rec in items:
    low = rec["ident"].lower()
    if low in {k.lower() for k in DROP}:
        dropped.append({"ident": rec["ident"], "why": next(v for k, v in DROP.items() if k.lower() == low)})
        continue
    rec = dict(rec)
    fix = next((v for k, v in FIELD_FIX.items() if k.lower() == low), None)
    if fix:
        rec["field_sampled"] = rec["field"]
        rec["field"] = fix
    recs.append(rec)

# 2. keep every book, chapter, preprint and dblp paper; fill each field with journal articles in sampling order
fixed = Counter(r["field"] for r in recs if r["stratum"] != "article")
need = {f: bh.FIELD_TARGETS["real"][f] - fixed.get(f, 0) for f in bh.FIELDS}
articles = sorted((r for r in recs if r["stratum"] == "article"),
                  key=lambda r: (bh.FIELDS.index(r.get("field_sampled", r["field"])), r["order"]))
keep_ids, spare = set(), []
for f in bh.FIELDS:
    queue = sorted((r for r in articles if r["field"] == f), key=lambda r: (r.get("field_sampled", f) != f, r["order"]))
    if len(queue) < need[f]:
        raise SystemExit(f"field {f}: {len(queue)} articles for {need[f]} places; sample more")
    keep_ids |= {r["ident"] for r in queue[: need[f]]}
    spare += [{"ident": r["ident"], "field": f, "why": "beyond the field target (sampled as a reserve)"}
              for r in queue[need[f]:]]
recs = [r for r in recs if r["stratum"] != "article" or r["ident"] in keep_ids]

# 3. numbering, curated fixes, sampling description and messy styles
out = []
for n, rec in enumerate(recs, 1):
    ident = rec["ident"]
    low = ident.lower()
    rec["n"] = n
    reg_title = rec["meta"]["title"]
    ov = next((v for k, v in OVERRIDES.items() if low == k.lower()), None)
    if ov:
        rec["overrides"] = ov
        rec["meta"] = {**rec["meta"], **ov}
        if "title" in ov:
            rec["extra_note"] = f"The registry stores the title as '{reg_title}'; the entry uses the form a careful author would write."
        else:
            rec["extra_note"] = "Registry value corrected: " + ", ".join(f"{k} given as '{v}'" for k, v in ov.items()) + "."
    if rec.get("field_sampled"):
        note = (f"Sampled under the '{FIELD_NAMES[rec['field_sampled']]}' fields; we file it under {rec['field']} "
                "because of its subject.")
        rec["extra_note"] = (rec.get("extra_note", "") + " " + note).strip()
    s = rec["stratum"]
    if s in ("article", "book", "book-chapter"):
        key = next(k for k in log if k.startswith(s + ":") and any(t.get("openalex") == rec.get("openalex")
                                                                     for t in log[k]["tried"]))
        L = log[key]
        kind = {"article": "journal articles", "book": "books", "book-chapter": "book chapters"}[s]
        rec["sampled"] = (f"OpenAlex random sample of {kind} with a DOI and more than 4 citations in the "
                          f"'{FIELD_NAMES[key.split(':')[1]]}' fields, seed {L['seed']}")
    elif s == "arxiv":
        L = next(L for k, L in log.items() if k.startswith("arxiv") and any(t.get("arxiv") == ident for t in L["tried"]))
        rec["sampled"] = (f"OpenAlex random sample of works whose only location is arXiv, seed {L['seed']}; "
                          "the arXiv record has no DOI and no journal reference")
    else:
        L = next(L for k, L in log.items() if k.startswith("dblp") and any(t.get("dblp") == ident for t in L["tried"]))
        venue = next(k for k, v in log.items() if v is L).split(":")[1]
        rec["sampled"] = f"random pick among the {L['n_keys']} DOI-less {venue} {L['year']} records in dblp"
    meta = rec["meta"]
    style = []
    na = len(meta["authors"])
    if na > 10 or (na > 4 and rng.random() < 0.5):
        style.append("and_others")
    if rng.random() < 0.3:
        style.append("initials")
    elif rng.random() < 0.08:
        style.append("first_last")
    if has_accents(meta) and rng.random() < 0.85:
        style.append("latex_accents")
    if rec["entry_type"] == "article" and meta.get("short_container") and \
            bh.norm(meta["short_container"]) != bh.norm(meta["container"]) and rng.random() < 0.45:
        style.append("abbrev_journal")
    if rec["registry"] == "crossref" and rng.random() < 0.13:
        style.append("no_doi")
    if rng.random() < 0.08:
        style.append("double_brace")
    if rec["registry"] == "arxiv" and rng.random() < 0.5:
        style.append("arxiv_journal")
    if rec["registry"] == "dblp" and rng.random() < 0.4:
        style.append("with_url")
    if rec["entry_type"] == "book" and rng.random() < 0.5:
        style.append("no_isbn")
    rec["style"] = style
    rec.pop("order", None)
    out.append(rec)

doc = {"description": "Genuine references for the 0.2 held-out set. Each was drawn at random (see 'sampled'), and "
                      "'meta' is the compact registry metadata the BibTeX is written from. 'overrides' lists curated "
                      "changes from the registry form; 'style' lists the messy-but-valid BibTeX forms used.",
       "retrieved": "2026-11-01", "items": out}
(HERE / "raw" / "real.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
sampling = {"description": "How each genuine reference was drawn: the OpenAlex filter and seed (or the dblp venue and "
                           "year), how many records the sample returned, and why records ahead of the chosen ones "
                           "were skipped. 'not_used' lists accepted records left out afterwards: reserves beyond a "
                           "field's target and records dropped by hand.",
            "strata": log, "not_used": dropped + spare}
(HERE / "raw" / "real_sampling.json").write_text(json.dumps(sampling, indent=1, ensure_ascii=False) + "\n",
                                                 encoding="utf-8")
print(len(out), Counter(r["field"] for r in out), Counter(r["entry_type"] for r in out))
print(Counter(s for r in out for s in r["style"]))
