# Held-out test set 0.2: sources, licences and labels

`heldout.jsonl` holds 246 bibliography entries with a known label. It is the held-out test set for release 0.2.0 of Reference Verifier, built on 2026-11-01. The development benchmark (`../data/benchmark.jsonl`, 342 items) was used to tune the tool's matching rules, and release 0.1.0 was scored once on the 0.1 held-out set (`../heldout/heldout.jsonl`, 246 items). Parser fixes have landed since, so this set was built afresh with the same recipe. It shares nothing with either earlier set (see [Independence](#independence-from-the-development-set-and-the-01-held-out-set)) and has not been run through the tool. Score it once, publish those numbers, and do not tune anything against it afterwards.

## Contents

| label | cs | biomed | physics | math | social | humanities | other | total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| real | 21 | 16 | 11 | 12 | 13 | 11 | 11 | 95 |
| fabricated | 54 | 0 | 0 | 0 | 0 | 0 | 0 | 54 |
| wrong_doi | 3 | 7 | 5 | 4 | 4 | 2 | 5 | 30 |
| metadata_error | 6 | 4 | 4 | 3 | 4 | 5 | 6 | 32 |
| retracted | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 35 |
| total | 89 | 32 | 25 | 24 | 26 | 23 | 27 | 246 |

The labels, sizes and the field spread of the real, wrong_doi, metadata_error and retracted items are the same as in the 0.1 held-out set; `build_heldout.py` checks both on every build. Each line is one JSON object with the same schema as the development set: `id`, `label`, `bibtex`, `field`, `entry_type`, `source`, `source_url`, `licence`, `constructed` and `notes`. The ID prefix shows the label: `h2-real-`, `h2-fab-`, `h2-wdoi-`, `h2-meta-` or `h2-retr-`. Every BibTeX key is unique within this file and also differs from every key in the development set and in the 0.1 held-out set, so all three sets can be loaded into one `.bib` file. `field` is our classification of the cited work's subject; `other` covers chemistry, materials, earth and environmental science, energy, agriculture, transport and engineering. `notes` says what is wrong with the entry, or what we checked.

## Sources

| source (`source` value) | URL | licence or terms | items |
|---|---|---|---:|
| Crossref REST API (`crossref`) | https://api.crossref.org | Crossref metadata is factual and free to reuse without restriction (CC0) | 75 real; metadata for all 35 retracted items; the wrong_doi and most metadata_error items are derived from these |
| dblp, through its SPARQL endpoint (`dblp`) | https://dblp.org, https://sparql.dblp.org | CC0 1.0 | 10 real |
| arXiv API (`arxiv`) | https://export.arxiv.org/api | arXiv metadata is CC0 1.0 | 10 real |
| OpenAlex | https://openalex.org | CC0 1.0 | random sampling of the real items; existence checks for the fabricated items |
| HalluCitation, ACL 2026 (`hallucitation-acl2026`) | https://aclanthology.org/2026.acl-long.2189/ | CC BY 4.0 (ACL Anthology) | 15 fabricated |
| CiteTracer ICLR 2026 set (`citetracer-iclr2026`) | https://huggingface.co/datasets/Afrostnova/Hallucinated_Citation | MIT. It quotes the ICLR 2026 desk-reject comments on OpenReview, which are CC BY 4.0 | 39 fabricated |
| Retraction Watch data, published by Crossref (`retraction-watch`) | https://gitlab.com/crossref/retraction-watch-data | Crossref made it a free public resource in 2023 and states no licence; we copy only facts (DOIs, dates, record IDs, reason codes) | 35 retracted |
| Constructed (`constructed`) | the `source_url` of each item points at the real record it was derived from | `constructed`; released with this repository under MIT | 30 wrong_doi, 32 metadata_error |

From the two hallucination compilations we copy only reference metadata: the reference string as printed, plus where it appeared. We copy no article text. Both compilations were used in the parsed form the development build made of them (1,699 reference strings from HalluCitation Tables 9 and 10 and from the CiteTracer `iclr2026_hallucinated` files); the CiteTracer dataset has not changed since (last modified 2026-05-18), so it was not fetched again. Not used, for the same reasons as in the earlier sets: GPTZero's pages (their terms forbid automated access and republishing), dblp's search API (it serves a bot check to scripts; we used the public SPARQL endpoint and did not try to get past the check), and Google Scholar.

## How labels were decided

**real (95).** Drawn at random, as in the 0.1 set, so that the set looks like an ordinary bibliography rather than a list of famous papers. Every random draw used the seed 20261101.

- 66 journal articles: for each field, an OpenAlex `sample=` call, filtered to journal articles with a DOI, more than 4 citations, not retracted and not paratext, published 1975 to 2025, with the field set through OpenAlex's topic fields. Each DOI was then fetched from Crossref, and the BibTeX is written from the Crossref record. Records were skipped in sampling order if Crossref did not hold them or if the record was unsuitable: no personal author, no journal or volume, a title under four words or in capitals, an editorial, correction or similar, a retraction or withdrawal in `updated-by`, a DOI in the Retraction Watch data, or a DOI, title or record that either earlier set contains or that the 0.1 sampling looked at. Non-English records were skipped outside the humanities. To reproduce the 0.1 field spread exactly, each field's article quota is its 0.1 total minus its books, chapters, preprints and dblp papers, and three reserve articles per field were sampled in case a field label had to be corrected; 20 reserves were not needed.
- 9 books and chapters: the same OpenAlex sampling for books and book chapters (same fields as in 0.1), metadata from Crossref.
- 10 conference papers without a DOI: one random record each from ten venues that do not mint DOIs (NeurIPS, ICML, ICLR, AISTATS, COLT, UAI, LREC, CoRL, MIDL, ISMIR), for a year drawn at random from 2016 to 2023, taken from the list of that venue-year's DOI-less dblp records via SPARQL. dblp names NeurIPS 2017 "NIPS", so that venue was queried under both names; CoRL had no DOI-less records for the drawn year 2022, so a new year (2019) was drawn.
- 10 arXiv-only preprints: an OpenAlex `sample=` of works whose only location is arXiv (2014 to 2024, more than 2 citations), keeping records whose arXiv entry has neither a DOI nor a journal reference. OpenAlex now leaves `doi` empty for most of these works, so a top-up (`collect/real_topup.py`) drew the same samples again and read the arXiv ID from the landing-page URL.

`raw/real_sampling.json` records every filter, seed and skipped record (151 records looked at; 35 skipped, 22 of them arXiv records with a DOI or journal reference) and the 21 accepted records left out afterwards. One sampled record was dropped because it is a book review whose Crossref title is the reviewed book's. The OpenAlex topic field was overridden by hand for 8 sampled records where it misled (for example, a numerical-methods textbook filed under engineering, an arXiv statistics preprint filed under physics); 3 of them are in the set, and the override list is in `collect/prep_real.py`.

The BibTeX uses the messy forms that real `.bib` files contain, chosen per entry with the seed, and the notes of each entry say which:

| form | entries | what it looks like |
|---|---:|---|
| `initials` | 26 | first names are abbreviated to initials |
| `and_others` | 16 | the author list is cut after three names and ends with "and others" |
| `latex_accents` | 15 | accents are written as LaTeX, e.g. `{\'e}`, `{\'a}` |
| `abbrev_journal` | 13 | the journal name is abbreviated (Crossref's short title) |
| `no_doi` | 8 | the DOI is left out; 28 real entries have no DOI in total |
| `double_brace` | 4 | the title is wrapped in `{{...}}` |
| `arxiv_journal` | 4 | written as `journal = {arXiv preprint arXiv:...}` |
| `first_last` | 3 | names are written "First Last" |
| `with_url` | 3 | a `url` field is included |
| `no_isbn` | 2 | a book's ISBN is left out |

Words with inner capitals are brace-protected, as BibTeX users do. Registry quirks are kept where a careful author might copy them: dblp's long booktitles, initials without full stops, a title in Crossref with a trailing full stop and a misspelling ("imigration-branching processes."), a journal name in capitals ("MATHEMATICA SCANDINAVICA"), Unicode hyphens, and an SICI-style DOI with angle brackets. Five records were corrected and say so in their notes: four titles whose markup Crossref lost (`Li$^-$-He` and `Li(2$^2$P)`, "metaphors really come from", "Type 1", "Ruthenium(IV)") and a journal name with a broken character ("Zeitschrift für Physik").

**fabricated (54).** An item is labelled `fabricated` only when all of these hold (the same five-step rule as the 0.1 set):

1. A public compilation lists it as a hallucinated reference that appeared in a real paper or submission: a row of HalluCitation Tables 9 and 10, or a reference line from a CiteTracer desk-reject comment.
2. Our title searches on 2026-11-01 found no record of the work in Crossref (bibliographic search, top 5, title plus first author), dblp (SPARQL full-text search on the title's longest words), OpenAlex (title search, top 5) or arXiv (a search for titles containing the five longest title words, plus an exact-phrase title search). Every hit scored below 0.70 in normalised title similarity, no hit's title contained the cited title or was contained in it, and no hit shared its first five words.
3. Where the reference gives an arXiv ID or a DOI, we resolved it, and dropped the candidate if the identifier belongs to a paper with a similar title (similarity 0.5 or more) or a shared author surname.
4. Hand review: we dropped every candidate that garbles a specific real work, such as a known model, dataset, benchmark, tool or paper cited under a wrong title or with a wrong subtitle (for example MBXP, IFEval, AdaLoRA, SnapKV, LongLLMLingua, Qwen2.5-VL), a real paper by the same authors, the title of a real blog post or paper, and fragments (a reference without a year, a title run into its year).
5. A general web search for the exact title in quotes (2026-11-01), so that the label does not simply mirror the registries the tool queries. We dropped a candidate whenever the search found a document with that title, or a real paper that the reference evidently garbles (same first-author surname and a paraphrased title, a URL that points to a real paper on the same finding, the same model name for the same kind of work, or a title that paraphrases a real paper's title). Pages that list the reference as hallucinated do not count as a match.

Candidates were drawn with `random.Random(20261101)` from the 1,699 parsed reference strings, after removing everything either earlier build used, checked or reviewed (see [Independence](#independence-from-the-development-set-and-the-01-held-out-set)), reference strings without a venue, and titles under four words. That left 363 eligible candidates, and we checked all of them: 166 were found in a registry (Crossref 104, dblp 49, OpenAlex 13) and 197 passed. We reviewed all 197 by hand, in the random order: 93 were rejected at step 4, 18 at step 5 (105 quoted-title searches in all, one for every candidate kept at step 4) and 3 at step 3 (an arXiv ID belonging to an unrelated paper with a shared author surname; this mechanical rule is the 0.1 rule and was kept). Of the rest, the first 54 in the random order are the set; 3 more passed every step and 26 passed steps 4 and 5 but were not checked against arXiv because the target was already met. `raw/fabricated.json` lists every rejected candidate with its reason (`rejected_after_registry_checks`), the unused ones (`passed_not_used`), and every candidate this build checked (`registry_checked`, with its result), so that a later set can avoid all of them. Each kept item's notes give the compilation row, the citing paper or submission, the best similarity per registry, any identifier check, and the web-search result. The BibTeX is our transcription of the printed reference string, including its errors (lower-cased acronyms, "et al." turned into "and others", missing venues, placeholder arXiv IDs and placeholder author names). It follows the parser of the earlier builds; for 8 items we split the venue string by hand into booktitle, volume, pages and publisher (`FIXES` in `collect/prep_fab.py`), 2 carry a transcription note (a hyphen lost at a line break restored, a page range printed inside a stray math environment moved to the pages field), and 2 carry a hand-check note (an arXiv ID that belongs to a real paper on a related topic). The 54 items come from 15 HalluCitation rows and from 37 CiteTracer submissions.

The 0.1 build used a journal-first second pass to reach fields beyond computer science. That was not possible here: every journal-style candidate in the compilations falls inside what the 0.1 build may have checked, so none was eligible, and all 54 items are computer science (32 conference papers, 20 arXiv-style articles, 2 preprints).

**wrong_doi (30, constructed).** A real entry of this set from Crossref keeps all its metadata, but its DOI is replaced with the DOI of a different real entry of this set. Half the donors come from the same field and half from a different field. The bases were drawn per field so that the field spread matches the 0.1 set. The notes give the true DOI and the title, author and year of the paper the substituted DOI belongs to.

**metadata_error (32, constructed).** A real entry of this set with exactly one field corrupted, 8 entries of each kind: year moved by 2 to 6 years; first author replaced by the first author of a real paper of this set from another field; journal or booktitle replaced by a dissimilar venue from this set; two or more title words replaced, leaving title similarity below 0.85. The bases were drawn per field so that the field spread matches the 0.1 set. The DOI, where present, is kept, so a checker can find the mismatch from the DOI record; 6 entries have no DOI (dblp, arXiv and `no_doi` bases) and say so in their notes. The notes give the field, the old value and the new value.

**retracted (35).** Rows of the Retraction Watch CSV (snapshot generated 2026-10-30, downloaded 2026-11-01) with RetractionNature "Retraction", ArticleType "Research Article", a single subject field and an original publication year from 1990, for which Crossref's own record of the paper lists the same retraction notice in `updated-by`. Five per field, sampled with the seed, at most one per journal, at most one per publisher within a field and at most five per publisher overall. Two rules were tightened after a first draw put one journal in twice under two spellings: journals are also matched by normalised name and by ISSN, and publishers by their first name part, so that "Springer" and "Springer - Nature Publishing Group" count as one publisher. We tried 37 rows: one DOI is not in Crossref and one Crossref record lacks the notice. No famous cases were added. Titles are given without the "RETRACTED:", "RETRACTED ARTICLE:", "[Retracted]" or "THIS ARTICLE HAS BEEN RETRACTED" prefixes that publishers add, because authors cite the original title; two titles that Crossref stores in capitals are written in normal case, as are author names stored in capitals, and a volume given as "Volume 13" is written "13". The notes give the notice DOI, the retraction date, the Retraction Watch record ID, the recorded reasons and any correction. 32 of the 35 notices reached Crossref through Retraction Watch and 3 from the publisher.

## Independence from the development set and the 0.1 held-out set

`raw/prior_fingerprints.json` records, for each earlier set, what it contains or checked:

| fingerprint | development set | 0.1 held-out set |
|---|---:|---:|
| DOIs | 168 | 111 |
| normalised titles (including fabricated titles and un-prefixed retracted titles) | 310 | 218 |
| registry records of real items | 140 | 95 |
| records the real sampling looked at (DOIs, OpenAlex, arXiv and dblp IDs) | 0 (chosen by hand) | 208 |
| HalluCitation rows used or reviewed | 44 | 23 |
| CiteTracer submissions used or reviewed | 68 | 95 |
| compilation candidates reviewed by hand | 130 | 134 |
| compilation candidates checked against the registries | 746 | 393 (a superset, see below) |
| fabricated reference strings | 81 | 54 |
| Retraction Watch records used / looked at | 45 / 67 | 35 / 35 |
| retraction notice DOIs | 45 | 35 |
| BibTeX keys | 342 | 246 |

`build_heldout.py` (also with `--validate`) checks every item against both columns on every build and fails if anything is shared: DOIs, titles and keys of all 246 entries; the registry records and sampled IDs of the real items; the rows, submissions, candidate keys and reference strings of the fabricated items, and every candidate this build checked; the Retraction Watch records, notice DOIs and DOIs of the retracted items. The current result is 0 overlaps with the development set and 0 with the 0.1 held-out set.

Two choices make the exclusion stricter than the 0.1 recipe:

- A CiteTracer submission or HalluCitation row that either earlier set used or reviewed contributed nothing here, even where only another reference from that submission was reviewed (the 0.1 build excluded whole submissions only when the development set used them).
- The 0.1 build did not keep its registry-check log, only the 134 candidates it reviewed. `collect/prior_fingerprints.py` reproduces that build's candidate order from its published rules (same eligibility, `random.Random(20261024)`, a journal-first second pass) and confirms that all 134 reviewed candidates appear in it. Because both of its passes keep the non-journal candidates in the same relative order and it checked 291 candidates in all, what it checked lies within the first 300 non-journal candidates plus every journal-style candidate, 393 in total. All of these were excluded.

The sets also differ by construction:

- Real items were sampled at random through OpenAlex and dblp with a new seed, and no DOI, title or record that either earlier set contains or looked at was allowed.
- Fabricated items come only from compilation rows and submissions that neither earlier build used, checked or reviewed.
- Retracted items come from a newer Retraction Watch snapshot and from records neither earlier set used or looked at.
- Constructed items use a different seed (20261101 instead of 20261023 and 20261024) and draw bases and donors only from this set's real items.
- The checks behind the fabricated labels were run fresh for this set.
- Neither Reference Verifier nor any part of its package was run on these items, and the earlier sets' result files were not read.

## Reproducing

```
python3 -I build_heldout.py                     # rebuild heldout.jsonl from raw/ offline, then validate
python3 -I build_heldout.py --validate          # validate only: JSON, BibTeX syntax, unique ids and keys,
                                                #   label and field targets, and overlap with the development
                                                #   set and the 0.1 held-out set
python3 -I build_heldout.py --refresh           # re-fetch every real and retracted record and report drift
python3 -I build_heldout.py --check-fabricated  # repeat the registry title searches for the fabricated items
```

The build uses the standard library only, and constructed items come from `random.Random(20261101)`, so the output is identical byte for byte across runs. `collect/` holds the one-off scripts that sampled the inputs and wrote `raw/`, in this order: `prior_fingerprints.py`, `real_sample.py`, `real_topup.py`, `prep_real.py`, `retracted_sample.py`, `prep_retracted.py`, `fab_check.py` (run twice, until every eligible candidate was checked), `fab_arxiv.py` and `prep_fab.py`; the hand review and the web-search results are the inputs `prep_fab.py` reads. They need network access, an `OPENALEX_API_KEY`, the Retraction Watch CSV, the parsed compilation strings and the logs of the development build, none of which are redistributed; their working files go to the folder named by `HELDOUT_WORK`. `collect/check_bibtexparser.py` is a second syntax check with bibtexparser 1.4 (1.4.3 parses all 246 entries, alone and together, with 246 unique keys). Network use was read-only, with a User-Agent naming the project and a contact address, and throttled per host: Crossref (polite pool, with a `mailto`) at most 2 requests per second per process, with at most two processes at a time, OpenAlex at most 2.5 per second per process (5 in all), dblp SPARQL at most 1 per second in all, arXiv 1 every 6 seconds with a 60-second pause after a 429. The whole build used 236 OpenAlex requests: 26 for sampling the real items and 210 title searches for the fabricated candidates.

`raw/` holds `real.json`, `fabricated.json`, `retracted.json`, `prior_fingerprints.json` and the two sampling logs, about 650 KB in total. The Retraction Watch CSV and the compilations' source files are not redistributed.

## Known limitations

- **Absence is evidence, not proof.** A fabricated title could exist somewhere we did not search: Semantic Scholar, Google Scholar, publisher sites, non-English indexes. The web search lowers that risk but runs one query per title. The hand review removed every case we could tie to a real work; borderline cases were rejected rather than kept (111 of the 197 candidates that passed the registries were rejected by hand or by the web search).
- **The fabricated set is all computer science.** Both compilations come from AI and NLP venues, and the journal-style candidates that gave the 0.1 set its few items outside computer science were all excluded as possibly checked before. Scores on `fabricated` say nothing about other fields.
- **The compilations are being used up.** After the development set, the 0.1 set and this set, every candidate the recipe allows has been checked by one of the three builds; the rest share a row or submission with an earlier set. A further held-out set needs a new source of documented hallucinated references.
- **Fabricated items vary in difficulty.** Some name invented journals or placeholder authors ("John Smith"); others name real researchers and real venues. Twenty-one give an arXiv ID; one is a placeholder that does not resolve, and the others resolve to unrelated papers, two of them on related topics, which tests whether a checker compares the record behind an identifier with the cited title.
- **Random real items are harder than famous ones.** They include registry quirks, long dblp booktitles, initials without full stops, article numbers in place of pages and titles with Unicode hyphens or LaTeX. A checker that scored well on the famous development items may score lower here.
- **Year corruptions of 2 years** can collide with legitimate gaps between online-first, print and preprint dates. Shifts of 0 or 1 year were avoided for this reason.
- **First-author replacements use real researchers' names** taken from other entries of this set.
- **Retracted items are mostly paper-mill retractions** from large publishers, because that is most of the database. Retraction status can change; `--refresh` re-checks that Crossref still lists each retraction.
- **Field labels are our own judgement.** They follow the journal and topic; some works sit between two fields.
- **The set is small.** With 54 fabricated and 30 to 35 items in each other error label, a single item moves a per-label recall by about 2 to 3 points. Report confidence intervals with the scores.
