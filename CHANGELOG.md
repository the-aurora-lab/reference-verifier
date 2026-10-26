# Changelog

## Unreleased

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

The benchmark in the README ("How well it works") was measured on 0.1.0.

## 0.1.0

First release: checks that every reference in a `.bib` file or a LaTeX paper exists, against Crossref, doi.org,
OpenAlex, DBLP, arXiv and PubMed (and Semantic Scholar with a key).
