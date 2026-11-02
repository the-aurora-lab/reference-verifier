# Changelog

## 0.2.2 (2026-11-02)

- On PyPI: `pip install reference-verifier`. Each release is built, tested and uploaded by this repository's
  GitHub Actions workflow (`.github/workflows/release.yml`) through PyPI's Trusted Publishing, with signed
  attestations of where each file was built.
- The source distribution holds the package, its tests and the documents; the benchmark stays in the repository.

No change to how references are looked up or matched: the held-out scores of 0.2.0 still apply.

## 0.2.1 (2026-11-01)

- Files are named relative to the working folder (or by name alone when they lie outside it) in the report header,
  in warnings and in the JSON output (`inputs`, `source_file`). Before, a `.bib` found through a `.tex` file appeared
  with its full path, home folder included, which then went wherever the output was shared.

No change to how references are looked up or matched: the held-out scores of 0.2.0 still apply.

## 0.2.0 (2026-11-01)

- Author lists broken across lines (`and` at the end of a line, as the ACL Anthology and DBLP export them) are split
  into separate authors. Before, such an entry was read as having a single author.
- Author lists after a name with a capital dotted I ("İnce") are split in the right places. Before, every later name
  lost a letter and "and others" was read as an author called "thers".
- Capitalised citation commands (`\Citet`, `\Parencite`, `\Textcite` and the like) count as citations.
- A warning when a `.tex` file inputs a file that does not exist, since citations in it cannot be seen.
- For tools built on the engine: each entry keeps its raw BibTeX fields; registry records carry pages, volume, issue,
  arXiv journal references, Crossref relations and Crossref's notices (retractions, corrections, expressions of
  concern: `updated-by` and `update-to`) when the registry gives them; citation locations (file:line); one
  input loader and the command-line options shared through `reference_verifier.inputs` and `reference_verifier.cli`.

Scored once on a new held-out set of 246 references (`benchmark/heldout-0.2/`), built independently of the
development set and of the 0.1 held-out set; the README's "How well it works" shows those numbers.

0.1.0's held-out scores, on `benchmark/heldout/`: real references found 93 of 95, fabricated flagged 54 of 54,
wrong DOIs 30 of 30, retracted papers found 35 of 35, precision of flags 84 of 86.

## 0.1.0

First release: checks that every reference in a `.bib` file or a LaTeX paper exists, against Crossref, doi.org,
OpenAlex, DBLP, arXiv and PubMed (and Semantic Scholar with a key).
