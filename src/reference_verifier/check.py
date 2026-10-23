"""Does each reference exist? Identifiers first, then title search across registries."""

from __future__ import annotations

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from .match import CLOSE_TITLE, FOUND_TITLE, is_found, rank, score
from .model import Record, Reference, Result, Score, Status
from .sources import LABELS, Sources

# Entry types that registries do not index; checked only when they carry a DOI.
WEB_TYPES = {"online", "www", "webpage", "software", "electronic"}
# Code and model releases cited as @misc with a link: no registry lists them either.
_CODE_HOSTS = re.compile(r"github\.com|gitlab\.com|bitbucket\.org|huggingface\.co|pypi\.org|cran\.r-project\.org")
# DOIs of versioned records (Zenodo software, datasets) keep resolving while their title changes per release.
_VERSIONED_KINDS = {"software", "dataset"}
_OTHER_WORK = 0.6  # a DOI whose work has a title this far from the entry's is someone else's paper


def _join(names: list[str]) -> str:
    names = list(dict.fromkeys(names))
    if not names:
        return "any registry"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def _skip_reason(ref: Reference) -> str | None:
    if ref.doi:
        return None
    if ref.entry_type in WEB_TYPES:
        return "web page or software entry: registries do not index these"
    link = " ".join(x for x in (ref.url or "", ref.venue) if x)
    if ref.entry_type in ("misc", "manual") and _CODE_HOSTS.search(link):
        return "code, model or package release: registries do not index these"
    if not (ref.title or ref.arxiv_id or ref.pmid):
        return "no title or identifier to check"
    return None


def check_reference(ref: Reference, src: Sources) -> Result:
    reason = _skip_reason(ref)
    if reason:
        return Result(ref, Status.SKIPPED, note=reason)

    answered: list[str] = []     # registries that gave an answer
    unreachable: list[str] = []  # registries that could not be asked
    best: tuple[Score, Record] | None = None
    doi_problem: str | None = None  # "missing" or "other"
    doi_rec: Record | None = None
    renamed: tuple[str, Record] | None = None  # an identifier that resolves to the same authors under a new title
    id_notes: list[str] = []

    def consider(rec: Record) -> Score:
        nonlocal best
        s = score(ref, rec)
        if best is None or rank(s) > rank(best[0]):
            best = (s, rec)
        return s

    if ref.doi:
        rec, resolved, tried = src.doi(ref.doi)
        if resolved and rec:
            answered.append(tried[-1])
            doi_rec = rec
            if not ref.title:
                return Result(ref, Status.FOUND, rec, sources_tried=answered, note="DOI resolves; the entry has no title to compare")
            s = consider(rec)
            if is_found(s):
                return Result(ref, Status.FOUND, rec, s, sources_tried=answered)
            if rec.kind in _VERSIONED_KINDS and s.first_author:
                renamed = (f"DOI {ref.doi}", rec)
            elif s.title < _OTHER_WORK:
                doi_problem = "other"
        elif resolved is False:
            answered.append("doi.org")
            doi_problem = "missing"
        else:
            unreachable.append("the DOI resolver")

    for ident, lookup, label in ((ref.arxiv_id, src.arxiv_id, "arXiv"), (ref.pmid, src.pmid, "PubMed")):
        if not ident:
            continue
        rec, resolved = lookup(ident)
        if resolved and rec:
            answered.append(label)
            if not ref.title:
                return Result(ref, Status.FOUND, rec, sources_tried=answered, note=f"{label} identifier resolves")
            s = consider(rec)
            if is_found(s) and not doi_problem:
                return Result(ref, Status.FOUND, rec, s, sources_tried=answered)
            # Same authors and year under a new title (arXiv versions get retitled). A shared first
            # surname alone is not enough: Wang or Li citing a random real identifier must not pass.
            same_year = s.year_delta is None or abs(s.year_delta) <= 1
            if s.first_author and (s.author_overlap or 0) >= 0.5 and same_year and not renamed:
                renamed = (f"{label} {ident}", rec)
        elif resolved is False:
            answered.append(label)
            id_notes.append(f"{label} identifier {ident} does not exist")
        else:
            unreachable.append(label)

    if ref.title and not (best and is_found(best[0])):
        for name in src.search_order:
            recs = src.search(name, ref)
            if recs is None:
                unreachable.append(LABELS[name])
                continue
            answered.append(LABELS[name])
            for rec in recs:
                consider(rec)
            if best and is_found(best[0]):
                break

    found = best is not None and is_found(best[0])
    s, rec = best if best else (None, None)
    where = f" (found in {rec.source})" if found and rec else ""
    missing = f"; {_join(unreachable)} could not be reached" if unreachable else ""

    if doi_problem == "other" and doi_rec:
        tail = f"; the cited work itself exists{where}" if found else "; no work with the entry's title was found either"
        return Result(ref, Status.DOI_OTHER_WORK, rec if found else None, s, doi_rec, answered,
                      f'DOI {ref.doi} belongs to a different work: "{doi_rec.title}"{tail}')
    if doi_problem == "missing":
        tail = f"; the work itself exists{where}, so the DOI is wrong" if found else "; no work with this title was found either"
        return Result(ref, Status.DOI_NOT_FOUND, rec if found else None, s, None, answered, f"DOI {ref.doi} is not registered{tail}")
    if found:
        return Result(ref, Status.FOUND, rec, s, doi_rec, answered, "; ".join(id_notes))
    if renamed:
        ident, rec = renamed
        return Result(ref, Status.FOUND, rec, score(ref, rec), doi_rec, answered,
                      f'{ident} resolves to the same authors, now titled "{rec.title}"')
    if s and rec and s.title >= CLOSE_TITLE:
        why = "authors differ" if s.title >= FOUND_TITLE else f"title similarity {s.title:.2f}"
        return Result(ref, Status.UNCERTAIN, rec, s, doi_rec, answered, f'closest: "{rec.title}" in {rec.source} ({why})')
    if answered:
        return Result(ref, Status.NOT_FOUND, None, s, doi_rec, answered,
                      "; ".join(id_notes + [f"no matching work in {_join(answered)}{missing}"]))
    return Result(ref, Status.ERROR, sources_tried=answered, note="no registry could be reached (offline, or a network error)")


def check_all(refs: list[Reference], src: Sources, workers: int = 4,
              progress: Callable[[int, int], None] | None = None) -> list[Result]:
    src.prefetch_arxiv([r.arxiv_id for r in refs if r.arxiv_id])
    results: list[Result | None] = [None] * len(refs)
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(check_reference, ref, src): i for i, ref in enumerate(refs)}
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
            done += 1
            if progress:
                progress(done, len(refs))
    return [r for r in results if r is not None]
