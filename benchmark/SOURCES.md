# Benchmark sources, licences and labels

`data/benchmark.jsonl` holds 342 bibliography entries with a known label. Each check in Reference Verifier is scored against it for precision and recall. This file covers where every item came from, the terms each source sets, how each label was decided, and what the labels cannot tell you.

## Contents

| label | cs | biomed | physics | math | social | humanities | other | total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| real | 37 | 18 | 18 | 25 | 16 | 13 | 13 | 140 |
| fabricated | 45 | 18 | 3 | 1 | 3 | 0 | 11 | 81 |
| wrong_doi | 6 | 7 | 7 | 5 | 5 | 1 | 5 | 36 |
| metadata_error | 13 | 6 | 4 | 9 | 4 | 1 | 3 | 40 |
| retracted | 6 | 8 | 6 | 6 | 7 | 6 | 6 | 45 |

Each line is one JSON object. Its fields are `id`, `label`, `bibtex`, `field`, `entry_type`, `source`, `source_url`, `licence`, `constructed` and `notes`. The ID prefix shows the label: `real-`, `fab-`, `wdoi-`, `meta-` or `retr-`. IDs are stable as long as the inputs in `data/raw/` stay the same. Every BibTeX key is unique across the whole file, so all entries can be written into one `.bib` file. The `field` value is our classification of the cited work's subject: `other` covers chemistry, materials, earth and environmental science, energy, agriculture and engineering. The `notes` value says what is wrong with the entry, or what we checked.

## Sources

| source (`source` value) | URL | licence or terms | items |
|---|---|---|---:|
| Crossref REST API (`crossref`) | https://api.crossref.org | Crossref metadata is factual and free to reuse without restriction (CC0) | 118 real; metadata for all 45 retracted items; most constructed items are derived from these |
| dblp, through its SPARQL endpoint (`dblp`) | https://dblp.org, https://sparql.dblp.org | CC0 1.0 | 12 real |
| arXiv API (`arxiv`) | https://export.arxiv.org/api | arXiv metadata is CC0 1.0 | 10 real |
| OpenAlex | https://openalex.org | CC0 1.0 | existence checks only (see below) |
| HalluCitation, ACL 2026 (`hallucitation-acl2026`) | https://aclanthology.org/2026.acl-long.2189/ | CC BY 4.0 (ACL Anthology) | 22 fabricated |
| CiteTracer ICLR 2026 set (`citetracer-iclr2026`) | https://huggingface.co/datasets/Afrostnova/Hallucinated_Citation | MIT. It quotes the ICLR 2026 desk-reject comments on OpenReview, which are CC BY 4.0 | 53 fabricated |
| Ansari 2026, arXiv:2602.05930 (`ansari2026-neurips2025`) | https://arxiv.org/abs/2602.05930 | CC BY 4.0 | 6 fabricated |
| Retraction Watch data, published by Crossref (`retraction-watch`) | https://gitlab.com/crossref/retraction-watch-data | Crossref made it a free public resource in 2023 and states no licence; we copy only facts (DOIs, dates, record IDs, reason codes) | 45 retracted |
| Constructed (`constructed`) | the `source_url` of each item points at the real record it was derived from | `constructed`; released with this repository under MIT | 36 wrong_doi, 40 metadata_error |

From the three hallucination compilations we copy only reference metadata: the reference string as printed, plus the location where it appeared. We copy no article text.

- **HalluCitation** (Sakai, Kamigaito and Watanabe, ACL 2026, pages 47295–47376). Table 9 lists one example of a hallucinated citation for each of the 301 affected ACL, NAACL and EMNLP 2024–2025 papers. Table 10 adds 140 from AACL 2025 and EACL 2026. We parsed both tables from the Anthology PDF. Each item's notes give the table, the row and the Anthology ID of the citing paper.
- **CiteTracer ICLR 2026 set** (Li, Lin and Ma, 2026, arXiv:2605.08583). The file is `iclr2026_hallucinated/hallucinated_refs_structured.json`. It holds 647 ICLR 2026 submissions that the program chairs desk-rejected with the comment "The following references in this submission do not refer to real documents and/or have major errors in bibliographic information", followed by the references themselves. We split those comments into 1,323 reference lines. Each item's notes give the OpenReview submission ID.
- **Ansari 2026** studies 100 fabricated citations in NeurIPS 2025 papers. We took the 7 examples quoted in its text and kept 6. The seventh was dropped because a real book chapter, "Power System Stability Controls", contains its title.

## Sources we did not use

- **GPTZero's tables of hallucinated citations in ICLR 2026 submissions and NeurIPS 2025 papers** (gptzero.me/news/iclr-2026, gptzero.me/news/neurips). GPTZero's Terms of Use forbid access "through automated or non-human means" and forbid copying or republishing site content for commercial purposes without written permission. This benchmark is published with a tool that also has a paid version, so we used nothing from those pages. The NeurIPS 2025 material is covered only through the CC BY examples in Ansari 2026.
- **The Columbia audit of PubMed Central published in The Lancet** (Topaz et al., 2026). No item-level data has been published. The CITADEL project site reports aggregate figures only.
- **Retraction Watch blog posts listing fabricated references.** We did not need them, and the posts are copyrighted text.
- **dblp's search API and web pages.** During the build they served an anti-bot challenge to scripts, so we used the public SPARQL endpoint instead and did not try to get past the challenge.
- **OpenAlex for bulk checks.** Without an API key, OpenAlex shares one free daily budget across a whole network. That budget ran out after about 100 searches. OpenAlex was therefore used on about 100 candidates only, 7 of which are in the final fabricated set. `build_dataset.py` uses OpenAlex only when `OPENALEX_API_KEY` is set.

## How labels were decided

**real (140).** Each entry is written by `build_dataset.py` from one registry record: a Crossref DOI record, a dblp record or an arXiv record. The compact metadata it is built from is cached in `data/raw/real.json`. We picked well-known works on purpose, so they are spread across fields: 100 journal articles, 15 conference papers, 10 arXiv-only preprints, 11 books and 4 book chapters. 12 of them (10 NeurIPS, ICML and ICLR papers and 2 JMLR articles) come from dblp and have no DOI.

65 entries use messy forms that are still valid and still describe the right work. The notes of each entry say which:

| form | entries | what it looks like |
|---|---:|---|
| `and_others` | 24 | the author list is cut after three names and ends with "and others" |
| `initials` | 17 | first names are abbreviated to initials |
| `no_doi` | 8 | the DOI is left out; 30 entries have no DOI in total |
| `latex_accents` | 7 | accents are written as LaTeX, e.g. `{\"o}`, `{\v Z}`, `$\Delta$` |
| `abbrev_journal` | 7 | the journal or venue name is abbreviated |
| `double_brace` | 4 | the title is wrapped in `{{...}}` |
| `arxiv_journal` | 2 | written as `journal = {arXiv preprint arXiv:...}` |
| `with_url` | 2 | a `url` field is included |
| `first_last` | 1 | names are written "First Last" |

Words with inner capitals are always brace-protected, e.g. `{BERT}`.

In 8 records the registry metadata is itself odd. Crossref stores some titles in capitals, prefixes others ("I.—COMPUTING MACHINERY AND INTELLIGENCE"), or lists 1,030 individual names where the article prints a corporate author. For these the entry uses the form a careful author would write, and the notes quote the registry form. These entries test whether a checker tolerates registry noise.

**fabricated (81).** An item is labelled `fabricated` only when two things hold:

1. A public compilation lists it as a hallucinated reference that appeared in a real paper or submission.
2. Our own searches on 2026-10-23 found no record of the work. We searched by title in Crossref (top 5 bibliographic matches, with the first author's name added), in arXiv (titles containing the five longest title words) and in dblp (full-text search on the title). Every hit scored below 0.70 in normalised title similarity. No hit's title contained the cited title, or was contained in it. No hit shared its first five words with it.

Where the reference gives an arXiv ID or a DOI, we resolved it. Candidates were rejected if the identifier pointed to a paper with a similar title (similarity 0.5 or more) or with a shared author surname. In the 14 items that kept an identifier, it points to an unrelated paper or does not resolve. This is identifier hijacking: the link works but describes something else. The notes name the paper the identifier actually belongs to.

All candidates that passed the automatic filter were then reviewed by hand. 56 were rejected. Most garbled a specific real work, such as a known model, dataset or paper cited under the wrong title (for example a GPT-1 report cited with an arXiv ID, or HarmBench). Others cited workshops, books or regional proceedings too poorly indexed for absence to mean much, or repeated the same citing paper too often.

34 of the kept items got a second check, recorded in their notes. We searched Crossref by first author plus title, arXiv by author surname plus title keywords, and dblp by the two longest title words. For journal citations with a volume and page, we also looked up what Crossref has at that location. In 5 cases the cited location holds a different, unrelated article. For example, Biochemical Society Transactions 47:1209 is "Targeting centrosome amplification, an Achilles' heel of cancer".

The BibTeX is our transcription of the printed reference string. In 7 items the source string was damaged by line breaks (a split DOI, a lost page-range dash). There we repaired the field, or dropped it when it was truncated, and each item notes which. The kept items' best title similarity in any registry is 0.697.

**wrong_doi (36, constructed).** A real entry from Crossref keeps all its metadata, but its DOI is replaced with the DOI of a different real entry in the set. Half the donors come from the same field and half from a different field. The notes give the entry's true DOI and the title, author and year of the paper the substituted DOI belongs to.

**metadata_error (40, constructed).** A real entry with exactly one field corrupted, 10 entries of each kind:

- year moved by 2 to 6 years
- first author replaced by the first author of a real paper from another field
- journal or booktitle replaced by a dissimilar venue from the set
- two or more title words replaced, leaving title similarity below 0.85

The DOI, where present, is kept, so a checker can detect the mismatch from the DOI record. The notes give the field, the old value and the new value.

**retracted (45).** These are rows of the Retraction Watch CSV (snapshot generated 2026-10-22) with RetractionNature "Retraction", for which Crossref's own record of the paper also lists the same retraction notice in `updated-by`. We sampled with a fixed seed, by field (from the Retraction Watch subject codes), taking at most one random pick per journal. We excluded withdrawals and records without authors. Nine well-known cases were added on purpose, among them the 1998 Lancet MMR paper, a STAP paper in Nature, the two Nature room-temperature superconductivity papers and the 2014 Science canvassing study.

Titles are given without the "RETRACTED:" prefix that publishers add, because authors cite the original title. The notes give the notice DOI, the retraction date, the Retraction Watch record ID and the recorded reasons. Most picks from the random sample are paper-mill-style retractions from large publishers, because that is what most of the database holds.

## Reproducing

```
python build_dataset.py                    # rebuild data/benchmark.jsonl from data/raw/ offline, then validate
python build_dataset.py --validate         # validate only: JSON, BibTeX syntax and brace balance, unique ids and keys, label targets
python build_dataset.py --refresh          # re-fetch every real and retracted record and report drift
python build_dataset.py --refresh --update-cache
python build_dataset.py --check-fabricated # repeat the title searches for every fabricated item
```

The script uses the standard library only. Constructed items come from `random.Random(20261023)`, so the output is identical byte for byte across runs. Network use is read-only and throttled per host:

- Crossref and OpenAlex: at most 5 requests per second. Crossref is called through its polite pool with a `mailto` parameter.
- dblp SPARQL: 1 request per second.
- arXiv: 1 request every 3 seconds.

`data/raw/` holds the curated inputs: `real.json`, `fabricated.json` and `retracted.json`. Each keeps the compact registry metadata, the original reference strings and the check results. Together they are under 400 KB. The Retraction Watch CSV and the source PDFs are not redistributed.

## Known limitations

- **Absence is evidence, not proof.** A fabricated title could still exist somewhere we did not search, such as Semantic Scholar, Google Scholar, publisher sites or non-English indexes. The manual review removed every case we could tie to a real work, but no list of this kind is perfect.
- **The fabricated set is skewed** towards entirely invented titles and towards CS and NLP. All three compilations come from AI and NLP venues. The non-CS items are references those papers cited from medical, chemistry or physics journals; there are no humanities items and only one math item. Hallucinations that keep a real title but change its authors or venue were excluded from `fabricated`, because those papers exist. `metadata_error` covers that case with constructed items only.
- **Fabricated items vary in how hard they are to catch.** Some are trivially fake ("A. A. Author", "Firstname Lastname"). Others name real researchers and real journals.
- **Some real entries copy registry quirks.** These include first-page-only page numbers from JSTOR records, Roman-numeral volumes in Mind, and article numbers in place of pages. They match the Crossref record, but other registries may record those fields differently, so a checker that compares across registries can flag them.
- **Year corruptions of 2 years** can collide with legitimate differences between online-first, print and preprint dates for a few works. We avoided shifts of 0 or 1 year for this reason.
- **First-author replacements use real researchers' names** taken from other entries in the set. The replaced name belongs to a real person, just not to an author of that paper.
- **Retraction status can change**, for example when a paper is reinstated. `--refresh` re-checks that Crossref still lists each retraction.
- **Field labels are our own judgement.** They follow the journal and topic, and some works sit between two fields.
