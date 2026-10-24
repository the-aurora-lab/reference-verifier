"""Write raw/real.json from the sampled records: number them, fix the field label where the OpenAlex topic
is misleading, apply curated title fixes, and assign messy-but-valid BibTeX styles with a fixed seed.

usage: python3 -I collect/prep_real.py
"""
import json
import random
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_heldout as bh  # noqa: E402

items = json.load(open(HERE / "work" / "real_items_raw.json", encoding="utf-8"))
log = json.load(open(HERE / "work" / "real_cands.json", encoding="utf-8"))
DROP = {"10.1112/plms/s3-70.1.183": "Crossref title is garbled ('Stems and Series in A -Classification')"}
FIELD_FIX = {  # our reading of the work's subject where the OpenAlex primary topic misleads
    "10.1021/acs.jctc.7b00601": "biomed", "10.1088/1367-2630/aab67f": "physics",
    "10.21136/cmj.2020.0128-19": "math", "10.1007/s00894-014-2553-5": "other",
    "10.1002/2017jd026471": "other", "10.1016/j.euromechflu.2017.03.001": "physics",
    "10.3201/eid2808.220557": "biomed", "10.1016/j.comppsych.2007.10.003": "biomed",
    "10.1016/j.jml.2006.08.007": "social", "10.1080/13602360110048195": "humanities",
    "10.1007/978-3-030-62777-5_24": "humanities",
}
OVERRIDES = {  # curated fixes; the registry form is quoted in the item notes
    "10.3138/9781442602946-018": {"title": "Owning the Nation, and the Personal Nature of Nationalism: Locality and "
                                           "the Rhetoric of Nationhood in Scotland"},
    "1612.06716": {"title": r"$|V_{cb}|$ from the $\bar{B}^0 \to D^{*+} \ell^- \bar{\nu}$ zero-recoil form factor "
                            r"using $2+1+1$ flavour HISQ and NRQCD"},
    "1803.03517": {"title": r"Axion energy density, bottle neck period, and $\bar\theta$ ratios between early and late times"},
    "10.1093/oso/9780199633524.003.0004": {"publisher": "Oxford University Press"},
}
FIELD_NAMES = {"cs": "Computer Science", "biomed": "Medicine, Biochemistry, Neuroscience, Immunology, Pharmacology",
               "physics": "Physics and Astronomy", "math": "Mathematics",
               "social": "Social Sciences, Psychology, Economics, Business", "humanities": "Arts and Humanities",
               "other": "Chemistry, Materials, Earth, Environment, Energy, Engineering, Agriculture"}
rng = random.Random(bh.SEED * 10 + 1)


def has_accents(meta):
    text = meta["title"] + " " + " ".join(a.get("given", "") + a.get("family", "") for a in meta["authors"])
    return any(ord(c) > 127 and unicodedata.category(c).startswith("L") for c in text)


out = []
n = 0
for rec in items:
    ident = rec["ident"]
    low = ident.lower()
    if low in DROP:
        continue
    n += 1
    rec = dict(rec)
    rec["n"] = n
    reg_title = rec["meta"]["title"]
    if low in FIELD_FIX:
        rec["field"] = FIELD_FIX[low]
    ov = next((v for k, v in OVERRIDES.items() if low == k.lower()), None)
    if ov:
        rec["overrides"] = ov
        rec["meta"] = {**rec["meta"], **ov}
        if "title" in ov:
            rec["extra_note"] = f"The registry stores the title as '{reg_title}'; the entry uses the form a careful author would write."
        else:
            rec["extra_note"] = "Registry value corrected: " + ", ".join(f"{k} given as '{v}'" for k, v in ov.items()) + "."
    s = rec["stratum"]
    if s in ("article", "book", "book-chapter"):
        key = f"{s}:{[k for k in log if k.startswith(s + ':') and any(t.get('openalex') == rec.get('openalex') for t in log[k]['tried'])][0].split(':')[1]}"
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
    out.append(rec)

doc = {"description": "Genuine references for the held-out set. Each was drawn at random (see 'sampled'), and "
                      "'meta' is the compact registry metadata the BibTeX is written from. 'overrides' lists curated "
                      "changes from the registry form; 'style' lists the messy-but-valid BibTeX forms used.",
       "retrieved": "2026-10-24", "items": out}
(HERE / "raw" / "real.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
from collections import Counter
print(len(out), Counter(r["field"] for r in out), Counter(r["entry_type"] for r in out))
print(Counter(s for r in out for s in r["style"]))
