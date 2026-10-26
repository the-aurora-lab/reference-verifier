"""Find cited keys and bibliography files in LaTeX sources."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# \cite, \citep, \citet*, \parencite, \textcite, \autocite, \footcite, \citeauthor, \nocite, and the capitalised
# forms that start a sentence (\Citet, \Parencite, \Textcite) ...
_CITE = re.compile(r"\\(?:[a-zA-Z]*[cC]ite[a-zA-Z]*|nocite)\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}")
_BIB = re.compile(r"\\(?:bibliography|addbibresource|addglobalbib)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
_INPUT = re.compile(r"\\(?:input|include|subfile)\s*\{([^}]+)\}")
_COMMENT = re.compile(r"(?<!\\)%.*")


@dataclass
class TexScan:
    cited: list[str] = field(default_factory=list)  # in order of first citation
    bib_files: list[Path] = field(default_factory=list)
    cites_everything: bool = False  # \nocite{*}
    # Where each key is cited: "intro.tex:12" (paths relative to the main file's folder).
    locations: dict[str, list[str]] = field(default_factory=dict)
    missing_inputs: list[str] = field(default_factory=list)  # \input targets that do not exist: their citations are unseen


def scan_tex(path: str | Path) -> TexScan:
    scan, seen_files, seen_keys = TexScan(), set(), set()
    root = Path(path).resolve().parent

    def where(p: Path, text: str, pos: int) -> str:
        try:
            name = p.relative_to(root).as_posix()
        except ValueError:
            name = p.as_posix()
        return f"{name}:{text.count(chr(10), 0, pos) + 1}"

    def visit(p: Path) -> None:
        if p in seen_files or not p.exists():
            return
        seen_files.add(p)
        text = _COMMENT.sub("", p.read_text(encoding="utf-8", errors="replace"))  # keeps line breaks
        for m in _CITE.finditer(text):
            for key in (k.strip() for k in m.group(1).split(",")):
                if key == "*":
                    scan.cites_everything = True
                elif key:
                    scan.locations.setdefault(key, []).append(where(p, text, m.start()))
                    if key not in seen_keys:
                        seen_keys.add(key)
                        scan.cited.append(key)
        for m in _BIB.finditer(text):
            for name in (n.strip() for n in m.group(1).split(",")):
                if name:
                    bib = root / (name if name.endswith(".bib") else f"{name}.bib")
                    if bib not in scan.bib_files:
                        scan.bib_files.append(bib)
        for m in _INPUT.finditer(text):
            name = m.group(1).strip()
            target = root / (name if name.endswith(".tex") else f"{name}.tex")
            if target.exists():
                visit(target)
            elif Path(name).suffix in ("", ".tex") and not (root / name).exists() and name not in scan.missing_inputs:
                scan.missing_inputs.append(name)

    visit(Path(path).resolve())
    return scan
