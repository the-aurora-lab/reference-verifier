"""Data types shared by the parsers, the registry clients and the checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass
class Reference:
    """One entry from the user's bibliography."""

    key: str
    entry_type: str
    title: str = ""
    authors: list[str] = field(default_factory=list)  # family names, as written in the entry
    year: int | None = None
    venue: str = ""
    doi: str | None = None
    arxiv_id: str | None = None
    pmid: str | None = None
    url: str | None = None
    source_file: str = ""


@dataclass
class Record:
    """A work as a registry describes it."""

    source: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str | None = None
    url: str | None = None
    # True when `authors` holds display names ("Kaiming He") rather than family names.
    full_names: bool = False
    kind: str = ""  # the registry's work type, e.g. "journal-article", "software", "dataset"


class Status(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNCERTAIN = "uncertain"
    DOI_NOT_FOUND = "doi_not_found"
    DOI_OTHER_WORK = "doi_other_work"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class Score:
    """How well a registry record matches a reference."""

    title: float
    authors_ok: bool | None  # None when either side lists no authors
    first_author: bool | None
    author_overlap: float | None
    year_delta: int | None


# Registries cover journal and conference papers well; books, theses, reports and
# web pages are often missing, so a miss on those is a weaker signal.
_PAPER_TYPES = {"article", "inproceedings", "conference", "incollection"}
_GREY_VENUE = ("technical report", "tech. rep", "white paper", "whitepaper", "blog", "preprint", "manuscript",
               "unpublished", "in preparation", "openai", "github")


def looks_grey(ref: Reference) -> bool:
    """Reports, white papers and blog posts filed as @article: registries often miss these."""
    venue = ref.venue.lower()
    return any(g in venue for g in _GREY_VENUE)


@dataclass
class Result:
    ref: Reference
    status: Status
    match: Record | None = None
    score: Score | None = None
    doi_record: Record | None = None
    sources_tried: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def severity(self) -> str:
        if self.status in (Status.FOUND, Status.SKIPPED):
            return "ok"
        if self.status in (Status.DOI_NOT_FOUND, Status.DOI_OTHER_WORK):
            return "high"
        if self.status is Status.NOT_FOUND:
            return "high" if self.ref.entry_type in _PAPER_TYPES and not looks_grey(self.ref) else "low"
        return "medium"
