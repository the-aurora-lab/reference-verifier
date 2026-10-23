# Reference Verifier

Check that every reference in your paper exists before a reviewer, a venue or arXiv checks for you.

`refverify` reads your `.bib` (or your LaTeX paper and the bibliography it uses) and looks each entry up
in Crossref, OpenAlex, DBLP, arXiv and PubMed (and Semantic Scholar, if you have a key). It reports
references that no registry lists, DOIs that are not registered, and DOIs that belong to a different paper.

```
$ refverify main.tex

Reference Verifier 0.1.0: 41 references from refs.bib

  37 found · 2 not found · 1 wrong DOI · 1 uncertain

  WRONG DOI  chen2023    Scalable graph transformers for molecules (2023)
                         DOI 10.1016/j.patcog.2021.108045 belongs to a different work: "..."
  NOT FOUND  smith2024   Quantum attention for genome alignment (2024)
                         no matching work in Crossref, OpenAlex, DBLP or arXiv
  ...
```

## Install

```
pip install reference-verifier
```

Python 3.10 or newer.

## Use

```
refverify refs.bib                 # every entry in a .bib
refverify main.tex                 # only the keys main.tex cites (follows \input and \bibliography)
refverify main.tex --json out.json # machine-readable results too
```

Exit status is 1 when a journal or conference reference is not found or has a bad DOI, so `refverify`
can run in a script or CI job. `--strict` also fails on uncertain matches.

Set your email so Crossref and PubMed can contact you if something goes wrong (their "polite pool"):

```
export REFVERIFY_MAILTO=you@example.org
```

OpenAlex searches draw on a daily budget ($0.001 per search; looking a DOI up is free). Without a key
everyone on your network shares $0.10 a day; a free key from openalex.org gives you $1 a day of your own,
enough for about a thousand searches:

```
export OPENALEX_API_KEY=...
```

Semantic Scholar finds reports and preprints the other registries miss, but its anonymous pool is
usually rate-limited, so it is used only when you set a key (free on application at semanticscholar.org):

```
export S2_API_KEY=...
```

If a registry stops answering during a run (rate limits, a bot check), `refverify` skips it for the rest of
the run and says so; rerun later to include it.

## What the results mean

| Result | Meaning |
|---|---|
| found | A registry lists a work with this title and matching authors (or year, when the entry has no authors). Also: an arXiv identifier that resolves to the same authors and year under a newer title, and a software or dataset DOI (Zenodo releases change title per version) with the same first author; both carry a note. |
| NOT FOUND | No registry lists a matching work. Check it by hand: books, theses, reports and very new papers are often missing from registries. Misses on white papers, blog posts and technical reports are marked low severity and do not fail the run. |
| WRONG DOI | The DOI resolves, but to a paper with a different title. |
| BAD DOI | The DOI is not registered with any DOI agency. |
| UNCERTAIN | Something close exists (a similar title, or the same title with different authors). |
| skipped | Web pages, software entries and code or model releases (GitHub, Hugging Face, PyPI...) without a DOI, and entries with nothing to look up. |

A reference that is not found is not proof of fabrication, and a found one can still have a wrong year,
venue or author list. `refverify` checks existence.

## Privacy and etiquette

Titles, first authors, years and identifiers from your bibliography are sent to the registries listed above.
Nothing else leaves your machine. Answers are cached for 30 days in `~/.cache/reference-verifier/`, so
repeat runs are fast and light on the registries. Requests are rate-limited per registry, including the one
request every three seconds that arXiv asks for.

## Licence

MIT
