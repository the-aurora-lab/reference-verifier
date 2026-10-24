# Held-out test set: sources, licences and labels

`heldout.jsonl` holds 246 bibliography entries with a known label. It is the held-out test set for Reference Verifier. The development benchmark (`data/benchmark.jsonl`, 342 items) was used to tune the tool's matching rules, so its scores are optimistic. This set was built afterwards, shares nothing with the development set, and has not been run through the tool. Score it once, publish those numbers, and do not tune anything against it afterwards.

## Contents

| label | cs | biomed | physics | math | social | humanities | other | total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| real | 21 | 16 | 11 | 12 | 13 | 11 | 11 | 95 |
| fabricated | 51 | 0 | 0 | 1 | 0 | 0 | 2 | 54 |
| wrong_doi | 3 | 7 | 5 | 4 | 4 | 2 | 5 | 30 |
| metadata_error | 6 | 4 | 4 | 3 | 4 | 5 | 6 | 32 |
| retracted | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 35 |
| total | 86 | 32 | 25 | 25 | 26 | 23 | 29 | 246 |

Each line is one JSON object with the same schema as the development set: `id`, `label`, `bibtex`, `field`, `entry_type`, `source`, `source_url`, `licence`, `constructed` and `notes`. The ID prefix shows the label: `ho-real-`, `ho-fab-`, `ho-wdoi-`, `ho-meta-` or `ho-retr-`. Every BibTeX key is unique within this file and is also different from every key in the development set, so both sets can be loaded into one `.bib` file. `field` is our classification of the cited work's subject; `other` covers chemistry, materials, earth and environmental science, energy, agriculture, transport and engineering. `notes` says what is wrong with the entry, or what we checked.

## Sources

| source (`source` value) | URL | licence or terms | items |
|---|---|---|---:|
| Crossref REST API (`crossref`) | https://api.crossref.org | Crossref metadata is factual and free to reuse without restriction (CC0) | 75 real; metadata for all 35 retracted items; the wrong_doi and most metadata_error items are derived from these |
| dblp, through its SPARQL endpoint (`dblp`) | https://dblp.org, https://sparql.dblp.org | CC0 1.0 | 10 real |
| arXiv API (`arxiv`) | https://export.arxiv.org/api | arXiv metadata is CC0 1.0 | 10 real |
| OpenAlex | https://openalex.org | CC0 1.0 | random sampling of the real items; existence checks for the fabricated items |
| HalluCitation, ACL 2026 (`hallucitation-acl2026`) | https://aclanthology.org/2026.acl-long.2189/ | CC BY 4.0 (ACL Anthology) | 11 fabricated |
| CiteTracer ICLR 2026 set (`citetracer-iclr2026`) | https://huggingface.co/datasets/Afrostnova/Hallucinated_Citation | MIT. It quotes the ICLR 2026 desk-reject comments on OpenReview, which are CC BY 4.0 | 43 fabricated |
| Retraction Watch data, published by Crossref (`retraction-watch`) | https://gitlab.com/crossref/retraction-watch-data | Crossref made it a free public resource in 2023 and states no licence; we copy only facts (DOIs, dates, record IDs, reason codes) | 35 retracted |
| Constructed (`constructed`) | the `source_url` of each item points at the real record it was derived from | `constructed`; released with this repository under MIT | 30 wrong_doi, 32 metadata_error |

From the two hallucination compilations we copy only reference metadata: the reference string as printed, plus where it appeared. We copy no article text. Not used, for the same reasons as in the development set: GPTZero's pages (their terms forbid automated access and republishing), dblp's search API (it serves a bot check to scripts; we used the public SPARQL endpoint and did not try to get past the check), and Google Scholar.

## How labels were decided

**real (95).** Unlike the development set, which used well-known works, these were drawn at random so that the set looks like an ordinary bibliography rather than a list of famous papers:

- 66 journal articles: for each field, an OpenAlex `sample=` call with a fixed seed, filtered to journal articles with a DOI, more than 4 citations, not retracted and not paratext, published 1975 to 2025, with the field set through OpenAlex's topic fields. Each DOI was then fetched from Crossref, and the BibTeX is written from the Crossref record. Records were skipped in sampling order if Crossref did not hold them or if the record was unsuitable: no personal author, no journal or volume, a title under four words or in capitals, an editorial, correction or similar, a retraction or withdrawal in `updated-by`, a DOI in the Retraction Watch data, or a DOI or title in the development set. Non-English records were skipped outside the humanities.
- 9 books and chapters: the same OpenAlex sampling for books and book chapters, metadata from Crossref.
- 10 conference papers without a DOI: one random record each from ten venues that do not mint DOIs (NeurIPS, ICML, ICLR, AISTATS, COLT, UAI, LREC, CoRL, MIDL, ISMIR), for a year drawn at random from 2016 to 2023, taken from the list of that venue-year's DOI-less dblp records via SPARQL.
- 10 arXiv-only preprints: an OpenAlex `sample=` of works whose only location is arXiv (2014 to 2024, more than 2 citations), keeping records whose arXiv entry has neither a DOI nor a journal reference.

`raw/real_sampling.json` records every filter, seed and skipped record. The OpenAlex topic field was overridden by hand for 11 records where it misled (for example, a history-of-astronomy chapter filed under physics); the override list is in `collect/prep_real.py`.

The BibTeX uses the messy forms that real `.bib` files contain, chosen per entry with a fixed seed, and the notes of each entry say which:

| form | entries | what it looks like |
|---|---:|---|
| `initials` | 22 | first names are abbreviated to initials |
| `abbrev_journal` | 17 | the journal name is abbreviated (Crossref's short title) |
| `latex_accents` | 14 | accents are written as LaTeX, e.g. `{\"a}`, `{\l}`, `{\'e}` |
| `and_others` | 13 | the author list is cut after three names and ends with "and others" |
| `no_doi` | 11 | the DOI is left out; 31 real entries have no DOI in total |
| `first_last` | 8 | names are written "First Last" |
| `arxiv_journal` | 6 | written as `journal = {arXiv preprint arXiv:...}` |
| `with_url` | 6 | a `url` field is included |
| `double_brace` | 5 | the title is wrapped in `{{...}}` |
| `no_isbn` | 2 | a book's ISBN is left out |

Words with inner capitals are brace-protected, as BibTeX users do. Registry quirks are kept where a careful author might copy them: dblp's long booktitles (including its "33nd International Conference" typo), initials without full stops, "WORLD SCIENTIFIC" as a publisher, and a space in "$\beta$ -1,3-Glucanases". Four records were corrected and say so in their notes: a chapter title with a leading chapter number, two arXiv titles with broken LaTeX (`\barν`), and a publisher name with the city run on. One sampled record was dropped because its Crossref title is garbled.

**fabricated (54).** An item is labelled `fabricated` only when all of these hold:

1. A public compilation lists it as a hallucinated reference that appeared in a real paper or submission: a row of HalluCitation Tables 9 and 10, or a reference line from a CiteTracer desk-reject comment.
2. Our title searches on 2026-10-24 found no record of the work in Crossref (bibliographic search, top 5, title plus first author), dblp (SPARQL full-text search on the title's longest words), OpenAlex (title search, top 5) or arXiv (a search for titles containing the five longest title words, plus an exact-phrase title search). Every hit scored below 0.70 in normalised title similarity, no hit's title contained the cited title or was contained in it, and no hit shared its first five words.
3. Where the reference gives an arXiv ID or a DOI, we resolved it, and dropped the candidate if the identifier belongs to a paper with a similar title (similarity 0.5 or more) or a shared author surname.
4. Hand review: we dropped every candidate that garbles a specific real work, such as a known model, dataset, benchmark or paper cited under a wrong title or with a wrong subtitle (for example ShareGPT4Video, MEMIT, OlympiadBench, Crescendo), a real paper by the same authors, blog posts, forum posts and fragments.
5. A general web search for the exact title in quotes (2026-10-24), so that the label does not simply mirror the registries the tool queries. We dropped a candidate whenever the search found a document with that title, or a real paper that the reference evidently garbles (same first-author surname and a paraphrased title, a URL that points to a real paper on the same finding, or a title that is a real book's title). Pages that list the reference as hallucinated do not count as a match.

We checked 291 candidates. Of the 134 that passed the registry filter and were reviewed, 80 were rejected at steps 3 to 5 (21 more passed the filter but were not reviewed, because the target was met); `raw/fabricated.json` lists each with its reason (`rejected_after_registry_checks`). Each kept item's notes give the compilation row, the citing paper or submission, the best similarity per registry, any identifier check, and the web-search result. The BibTeX is our transcription of the printed reference string, including its errors (lower-cased acronyms, "et al." turned into "and others", missing venues, placeholder arXiv IDs).

Candidates were drawn with `random.Random(20261024)` from the 1,699 parsed reference strings of both compilations, after removing every HalluCitation row and every CiteTracer submission used in the development set, every candidate the development build had already checked or reviewed, and reference strings without a venue. A second pass put journal-style references first, to reach fields beyond computer science.

**wrong_doi (30, constructed).** A held-out real entry from Crossref keeps all its metadata, but its DOI is replaced with the DOI of a different held-out real entry. Half the donors come from the same field and half from a different field. The notes give the true DOI and the title, author and year of the paper the substituted DOI belongs to.

**metadata_error (32, constructed).** A held-out real entry with exactly one field corrupted, 8 entries of each kind: year moved by 2 to 6 years; first author replaced by the first author of a held-out real paper from another field; journal or booktitle replaced by a dissimilar venue from the held-out set; two or more title words replaced, leaving title similarity below 0.85. The DOI, where present, is kept, so a checker can find the mismatch from the DOI record. Entries without a DOI (dblp and arXiv bases) say so in their notes. The notes give the field, the old value and the new value.

**retracted (35).** Rows of the Retraction Watch CSV (snapshot generated 2026-10-22) with RetractionNature "Retraction", ArticleType "Research Article", a single subject field and an original publication year from 1990, for which Crossref's own record of the paper lists the same retraction notice in `updated-by`. Five per field, sampled with a fixed seed, at most one per journal, at most one per publisher within a field and at most five per publisher overall. No famous cases were added. Titles are given without the "RETRACTED:" prefix that publishers add (one misspelled "Rectracted:" prefix was removed by hand), because authors cite the original title. The notes give the notice DOI, the retraction date, the Retraction Watch record ID and the recorded reasons.

## Independence from the development set

`raw/dev_fingerprints.json` records what the development set contains: its 168 DOIs, 310 normalised titles (including the parsed titles of its fabricated items and the un-prefixed titles of its retracted items), 140 registry records, the 22 HalluCitation rows and 48 CiteTracer submissions it uses, the 130 candidates its build reviewed by hand, its 81 fabricated reference strings, its 45 Retraction Watch records and notice DOIs, and its 342 BibTeX keys. `build_heldout.py` checks every held-out item against all of these on every build and fails if anything is shared. The current result is 0 overlaps.

The sets also differ by construction:

- Real items were sampled at random through OpenAlex and dblp, not chosen by hand, and no DOI or title from the development set was allowed.
- Fabricated items come only from compilation rows and submissions the development build never used, checked or reviewed. A CiteTracer submission that contributed any item to the development set contributed nothing here.
- Retracted items come from Retraction Watch records not in the development set.
- Constructed items use a different seed (20261024 instead of 20261023) and draw bases and donors only from held-out real items.
- The checks behind the fabricated labels were run fresh for this set and add a general web search, which the development set did not use.
- Neither Reference Verifier nor any part of its package was run on these items.

## Reproducing

```
python3 -I build_heldout.py                     # rebuild heldout.jsonl from raw/ offline, then validate
python3 -I build_heldout.py --validate          # validate only: JSON, BibTeX syntax, unique ids and keys,
                                                #   label targets, and overlap with the development set
python3 -I build_heldout.py --refresh           # re-fetch every real and retracted record and report drift
python3 -I build_heldout.py --check-fabricated  # repeat the registry title searches for the fabricated items
```

The build uses the standard library only, and constructed items come from `random.Random(20261024)`, so the output is identical byte for byte across runs. `collect/` holds the one-off scripts that sampled the inputs and wrote `raw/` (they need network access, an `OPENALEX_API_KEY`, the Retraction Watch CSV and the parsed compilation strings from the development build, none of which are redistributed); `collect/check_bibtexparser.py` is a second syntax check with bibtexparser 1.4. Network use is read-only and throttled per host: Crossref (polite pool, with a `mailto`) and OpenAlex at most 5 requests per second, dblp SPARQL 1 per second, arXiv 1 every 3 to 5 seconds. The whole build used 161 OpenAlex searches.

`raw/` holds `real.json`, `fabricated.json`, `retracted.json`, `dev_fingerprints.json` and the two sampling logs, about 400 KB in total. The Retraction Watch CSV and the compilations' source files are not redistributed.

## Known limitations

- **Absence is evidence, not proof.** A fabricated title could exist somewhere we did not search: Semantic Scholar, Google Scholar, publisher sites, non-English indexes. The web search lowers that risk but runs one query per title. The hand review removed every case we could tie to a real work; borderline cases were rejected rather than kept.
- **The fabricated set is almost all computer science.** Both compilations come from AI and NLP venues; even with a journal-first second pass, only 3 of the 54 items (one operations-research, one control and one transport reference) fall outside computer science. Scores on `fabricated` say little about other fields.
- **Fabricated items vary in difficulty.** Some name invented journals or placeholder authors; others name real researchers and real venues. Several keep a placeholder or unrelated arXiv ID, which tests whether a checker compares the record behind an identifier with the cited title.
- **Random real items are harder than famous ones.** They include registry quirks, long dblp booktitles, initials without full stops, article numbers in place of pages and titles with Unicode hyphens. A checker that scored well on the famous development items may score lower here. That difference is part of what this set measures.
- **Year corruptions of 2 years** can collide with legitimate gaps between online-first, print and preprint dates. Shifts of 0 or 1 year were avoided for this reason.
- **First-author replacements use real researchers' names** taken from other held-out entries.
- **Retracted items are mostly paper-mill retractions** from large publishers, because that is most of the database. Retraction status can change; `--refresh` re-checks that Crossref still lists each retraction.
- **Field labels are our own judgement.** They follow the journal and topic; some works sit between two fields.
- **The set is small.** With 54 fabricated and 30 to 35 items in each other error label, a single item moves a per-label recall by about 2 to 3 points. Report confidence intervals with the scores.
