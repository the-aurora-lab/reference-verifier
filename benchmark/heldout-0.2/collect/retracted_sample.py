"""Pick retracted papers for the 0.2 held-out set from the Retraction Watch CSV and confirm each in Crossref.

usage: HELDOUT_WORK=DIR python3 -I collect/retracted_sample.py RETRACTION_WATCH.csv
Writes DIR/retracted_items_raw.json and DIR/retracted_log.json. Skips every Retraction Watch record that the
development set or the 0.1 held-out set used or looked at, and every DOI, notice DOI and title in either set.
"""
import csv
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

WORK = Path(os.environ.get("HELDOUT_WORK", HERE / "work"))
bh._MIN_INTERVAL["api.crossref.org"] = 0.5
SEED = bh.SEED
csv.field_size_limit(10**9)
prior = json.load(open(HERE / "raw" / "prior_fingerprints.json", encoding="utf-8"))["sets"]


def union(name):
    return set().union(*(set(s[name]) for s in prior.values()))


prior_rw = union("retraction_watch_records") | union("retraction_watch_checked")
prior_dois, prior_titles, prior_notices = union("dois"), union("norm_titles"), union("retraction_notice_dois")
rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")))


def field_of(subjects):
    fs = set()
    for s in [x.strip() for x in subjects.split(";") if x.strip()]:
        if s.startswith(("(BLS)", "(HSC)")):
            fs.add("biomed")
        elif s.startswith(("(B/T) Computer Science", "(B/T) Data Science")):
            fs.add("cs")
        elif s.startswith(("(PHY) Physics", "(PHY) Astrophysics", "(PHY) Cosmology", "(PHY) Astronomy")):
            fs.add("physics")
        elif s.startswith(("(PHY) Mathematics", "(PHY) Statistics")):
            fs.add("math")
        elif s.startswith(("(SOC)", "(B/T) Business - Economics")):
            fs.add("social")
        elif s.startswith("(HUM)"):
            fs.add("humanities")
        elif s.startswith(("(PHY) Chemistry", "(PHY) Materials", "(PHY) Geology", "(PHY) Engineering", "(ENV)",
                           "(PHY) Energy", "(PHY) Hydrology", "(PHY) Crystallography")):
            fs.add("other")
        else:
            fs.add("mixed")
    return fs


cands = {f: [] for f in bh.FIELDS}
for r in rows:
    if r["RetractionNature"] != "Retraction" or r["Record ID"] in prior_rw:
        continue
    odoi, rdoi = r["OriginalPaperDOI"].strip().lower(), r["RetractionDOI"].strip().lower()
    if not odoi.startswith("10.") or not rdoi.startswith("10.") or odoi == rdoi:
        continue
    if odoi in prior_dois or rdoi in prior_notices or bh.norm(r["Title"]) in prior_titles:
        continue
    at = r["ArticleType"]
    if "Research Article" not in at or "Conference" in at or "Book" in at:
        continue
    fs = field_of(r["Subject"])
    if len(fs) != 1 or "mixed" in fs:
        continue
    y = re.search(r"(\d{4})", r["OriginalPaperDate"])
    if not y or int(y.group(1)) < 1990 or not r["Author"].strip():
        continue
    cands[next(iter(fs))].append(r)
print({f: len(v) for f, v in cands.items()}, flush=True)

QUOTA = 5
rng = random.Random(SEED)
picked, log, seen_j, seen_issn, pub_count = [], [], set(), set(), {}


def journal_key(name):
    """'The International Journal of X & Y' and 'International Journal of X & Y' are one journal."""
    return re.sub(r"^the ", "", bh.norm(name))


def publisher_key(name):
    """'Springer' and 'Springer - Nature Publishing Group', or 'IOS Press (bought by ...)': one key each."""
    return re.split(r"\s+-\s+|\s*\(", name.strip())[0].strip().lower()


for f in bh.FIELDS:
    pool = sorted(cands[f], key=lambda r: int(r["Record ID"]))
    rng.shuffle(pool)
    n, field_pubs = 0, {}
    for r in pool:
        if n >= QUOTA:
            break
        j, pub = journal_key(r["Journal"]), publisher_key(r["Publisher"])
        if j in seen_j or field_pubs.get(pub, 0) >= 1 or pub_count.get(pub, 0) >= 5:
            continue
        odoi, rdoi = r["OriginalPaperDOI"].strip(), r["RetractionDOI"].strip()
        try:
            m = bh.crossref_work(odoi)
        except urllib.error.HTTPError as exc:
            log.append({"record": r["Record ID"], "skip": f"Crossref HTTP {exc.code}"})
            continue
        ups = [u for u in m.get("updated-by", []) or [] if u.get("type") == "retraction"]
        match = [u for u in ups if u.get("DOI", "").lower() == rdoi.lower()]
        why = None
        if not match:
            why = "Crossref updated-by lacks this retraction notice" if not ups else "Crossref lists a different notice"
        elif not any(a.get("family") for a in m.get("author", []) or []):
            why = "no personal authors in Crossref"
        elif m.get("type") != "journal-article":
            why = "Crossref type " + str(m.get("type"))
        elif set(m.get("ISSN") or []) & seen_issn:
            why = "journal already used (same ISSN under another name)"
        elif bh.norm(bh._RETRACTED_PREFIX.sub("", bh.clean_markup((m.get("title") or [""])[0]))) in prior_titles:
            why = "title in an earlier set"
        log.append({"record": r["Record ID"], "doi": odoi, "skip": why})
        if why:
            continue
        seen_j.add(j)
        seen_issn.update(m.get("ISSN") or [])
        field_pubs[pub] = field_pubs.get(pub, 0) + 1
        pub_count[pub] = pub_count.get(pub, 0) + 1
        meta = bh.meta_from_crossref(m)
        u = match[0]
        picked.append({"registry": "crossref", "ident": meta["doi"], "field": f, "entry_type": "article",
                       "n_authors": len(meta["authors"]), "meta": meta, "notice_doi": u["DOI"],
                       "retraction_date": "-".join(f"{x:02d}" if i else str(x) for i, x in
                                                   enumerate((u.get("updated") or {}).get("date-parts", [[0]])[0])),
                       "crossref_source": u.get("source", ""),
                       "rw": {"record_id": r["Record ID"], "subject": r["Subject"], "journal": r["Journal"],
                              "publisher": r["Publisher"], "retraction_doi": rdoi,
                              "retraction_date": r["RetractionDate"], "nature": r["RetractionNature"],
                              "reasons": [x.strip().lstrip("+") for x in r["Reason"].split(";") if x.strip()]}})
        n += 1
    print(f, "picked", n, flush=True)
(WORK / "retracted_items_raw.json").write_text(json.dumps(picked, indent=1, ensure_ascii=False), encoding="utf-8")
(WORK / "retracted_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
print("total", len(picked))
