"""Turn the files a user names (.bib and .tex) into the references to check."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .model import Reference
from .parse import load_bib, scan_tex


class InputError(Exception):
    """The inputs cannot be checked at all (a missing file, no .bib to read)."""


@dataclass
class Inputs:
    bibs: list[Path] = field(default_factory=list)
    tex_files: list[Path] = field(default_factory=list)
    entries: list[Reference] = field(default_factory=list)  # every entry of every .bib, repeated keys included
    refs: list[Reference] = field(default_factory=list)  # what gets checked: first entry per key, cited keys only
    cited: list[str] = field(default_factory=list)  # keys the .tex files cite, in order of first citation
    cites_everything: bool = False  # some .tex has \nocite{*}
    restricted: bool = False  # refs were limited to the cited keys
    locations: dict[str, list[str]] = field(default_factory=dict)  # key -> ["main.tex:12", ...]
    warnings: list[str] = field(default_factory=list)


def load_inputs(files: list[Path], include_uncited: bool = False) -> Inputs:
    """A .tex file brings in its bibliography files and limits the check to the keys it cites,
    unless `include_uncited` is set or the paper cites everything with \\nocite{*}."""
    out = Inputs()
    restrict = False
    for f in files:
        if not f.exists():
            raise InputError(f"{f}: no such file")
        if f.suffix.lower() == ".tex":
            out.tex_files.append(f)
            scan = scan_tex(f)
            out.cited += [k for k in scan.cited if k not in out.cited]
            out.cites_everything = out.cites_everything or scan.cites_everything
            restrict = restrict or not scan.cites_everything
            for name in scan.missing_inputs:
                out.warnings.append(f"{f} inputs {name}, which does not exist; citations in it are not seen")
            for key, places in scan.locations.items():
                out.locations.setdefault(key, []).extend(places)
            for b in scan.bib_files:
                if b.exists() and b not in out.bibs:
                    out.bibs.append(b)
                elif not b.exists():
                    out.warnings.append(f"{f} names {b}, which does not exist")
        elif f not in out.bibs:
            out.bibs.append(f)
    if not out.bibs:
        raise InputError("no .bib file to check")

    seen = set()
    for b in out.bibs:
        for ref in load_bib(b):
            out.entries.append(ref)
            if ref.key not in seen:
                seen.add(ref.key)
                out.refs.append(ref)
    if restrict and out.cited and not include_uncited:
        wanted = set(out.cited)
        out.refs = [r for r in out.refs if r.key in wanted]
        out.restricted = True
    return out
