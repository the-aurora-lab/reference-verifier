"""Decide whether a registry record is the work a reference describes."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from .model import Record, Reference, Score

FOUND_TITLE = 0.90  # at or above: same title (allowing typos, punctuation, a dropped subtitle)
CLOSE_TITLE = 0.80  # at or above: worth showing as the closest candidate

_FORMAT_CMD = re.compile(r"\\(?:emph|textit|textbf|textsc|textrm|texttt|mathrm|mathbf|mathit|mathcal|url|text)\b")
_LATEX_CMD = re.compile(r"\\[a-zA-Z]+\*?")
_SUBTITLE = re.compile(r"[:?!]|\s[-\u2013\u2014]\s")
# Registries prefix retracted works and notices: "RETRACTED ARTICLE: ...", "Retraction Note: ...".
_NOTICE = re.compile(r"^\s*(?:retracted(?: article)?|retraction(?: note)?|withdrawn|expression of concern)\s*[:.\-]\s*",
                     re.IGNORECASE)
_GROUP_AUTHOR = re.compile(r"collaborat|consortium|group|network|initiative|investigators|committee", re.IGNORECASE)


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def normalize_title(s: str) -> str:
    s = _NOTICE.sub("", s)
    s = s.replace("\\&", " and ").replace("&", " and ")
    s = _FORMAT_CMD.sub(" ", s)  # keep the argument of formatting commands, drop the command
    s = _LATEX_CMD.sub(" ", s).replace("{", "").replace("}", "")  # braces only protect case: "{R}eview"
    s = re.sub(r"[^a-z0-9]+", " ", _ascii(s).lower())
    return " ".join(s.split())


def _main_title(s: str) -> str:
    return normalize_title(_SUBTITLE.split(_NOTICE.sub("", s), maxsplit=1)[0])


def title_similarity(a: str, b: str) -> float:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    score = SequenceMatcher(None, na, nb, autojunk=False).ratio()
    # One side often lacks the subtitle ("Deep learning" vs "Deep learning: a review"; registries
    # sometimes store only "BLEU" for "BLEU: a method for ..."). A short main title like "BLEU"
    # scores exactly the found threshold, so the authors (or year) must also agree.
    ma, mb = _main_title(a), _main_title(b)
    for main, other in ((ma, nb), (mb, na)):
        if main and main == other:
            score = max(score, 0.95 if len(main.split()) >= 3 else FOUND_TITLE)
    # The registry title may wrap the cited one in a series heading: JSTOR lists Quine's paper as
    # "Main Trends in Recent Philosophy: Two Dogmas of Empiricism". Only this direction counts: an
    # entry that adds words to a real title ("Attention is all you need for graphs") must not pass.
    if len(na.split()) >= 3 and f" {na} " in f" {nb} ":
        score = max(score, FOUND_TITLE)
    return score


def name_tokens(name: str) -> list[str]:
    s = re.sub(r"[^a-z ]", " ", _ascii(name).lower().replace("-", " "))
    return [t for t in s.split() if len(t) > 1]


def family_key(name: str) -> str:
    """The comparable part of a family name: 'van der Berg' -> 'berg'."""
    toks = name_tokens(name)
    return toks[-1] if toks else ""


def author_match(ref_authors: list[str], rec: Record) -> tuple[bool | None, bool | None, float | None]:
    """Return (authors_ok, first_author_matches, overlap)."""
    keys = [k for k in (family_key(a) for a in ref_authors) if k]
    if not keys or not rec.authors:
        return None, None, None
    if rec.full_names:
        rec_sets = [set(name_tokens(n)) for n in rec.authors]
    else:
        rec_sets = [{family_key(n)} for n in rec.authors]
    rec_sets = [s for s in rec_sets if s]
    if not rec_sets:
        return None, None, None

    def hit(k: str) -> bool:
        return any(k in s for s in rec_sets)

    first = hit(keys[0])
    overlap = sum(hit(k) for k in keys) / min(len(keys), len(rec_sets))
    if not first and overlap < 0.5 and any(_GROUP_AUTHOR.search(n) for n in rec.authors):
        # "GBD 2019 Collaborators" cannot be compared with named authors: let the year decide.
        return None, None, None
    return first or overlap >= 0.5, first, overlap


def score(ref: Reference, rec: Record) -> Score:
    ok, first, overlap = author_match(ref.authors, rec)
    delta = rec.year - ref.year if ref.year and rec.year else None
    return Score(title_similarity(ref.title, rec.title), ok, first, overlap, delta)


def is_found(s: Score) -> bool:
    if s.title < FOUND_TITLE:
        return False
    if s.authors_ok is None:
        # No authors to compare: also require a plausible year so a generic title alone can't pass.
        return s.year_delta is None or abs(s.year_delta) <= 1
    return s.authors_ok


def rank(s: Score) -> tuple[bool, float]:
    return is_found(s), s.title + (0.05 if s.authors_ok else 0.0)
