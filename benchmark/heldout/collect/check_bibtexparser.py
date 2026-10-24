"""Second-opinion syntax check: parse every held-out BibTeX entry with bibtexparser (1.x), one file at a time
and all together, and confirm that keys are unique and every entry keeps author, title and year.

usage: <python with bibtexparser> -I collect/check_bibtexparser.py heldout.jsonl
"""
import json
import sys

import bibtexparser
from bibtexparser.bparser import BibTexParser

items = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
bad = 0
for it in items:
    db = bibtexparser.loads(it["bibtex"], parser=BibTexParser(common_strings=True))
    if len(db.entries) != 1:
        print(it["id"], "parsed into", len(db.entries), "entries")
        bad += 1
        continue
    e = db.entries[0]
    missing = [f for f in ("author", "title", "year") if not e.get(f)]
    if missing or e["ENTRYTYPE"] != it["entry_type"]:
        print(it["id"], "missing", missing, "type", e["ENTRYTYPE"])
        bad += 1
whole = bibtexparser.loads("\n\n".join(it["bibtex"] for it in items), parser=BibTexParser(common_strings=True))
keys = [e["ID"] for e in whole.entries]
print(f"bibtexparser {bibtexparser.__version__}: {len(items)} items, {len(whole.entries)} entries parsed from the "
      f"combined file, {len(set(keys))} unique keys, {bad} problem entries")
sys.exit(0 if bad == 0 and len(whole.entries) == len(items) == len(set(keys)) else 1)
