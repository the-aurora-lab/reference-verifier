"""refverify: check that every reference in a .bib (or a LaTeX paper's bibliography) exists."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .check import check_all
from .http import Cache, Http, default_cache_path
from .model import Status
from .parse import load_bib, scan_tex
from .report import render_text, to_json, use_color
from .sources import SEARCH_ORDER, Sources

_FAIL = {Status.NOT_FOUND, Status.DOI_NOT_FOUND, Status.DOI_OTHER_WORK}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="refverify",
        description="Check that every reference exists, against Crossref, OpenAlex, DBLP, arXiv and PubMed.",
        epilog="A .tex file brings in its \\bibliography/\\addbibresource files and limits the check to cited keys.",
    )
    p.add_argument("files", nargs="+", type=Path, help=".bib or .tex files")
    p.add_argument("--all", action="store_true", help="check every .bib entry, not only the ones the .tex cites")
    p.add_argument("--json", type=Path, metavar="PATH", help="also write the results as JSON")
    p.add_argument("--show-all", action="store_true", help="list found references too")
    p.add_argument("--strict", action="store_true", help="exit with 1 on uncertain results and on unreachable registries too")
    p.add_argument("--mailto", default=os.environ.get("REFVERIFY_MAILTO"),
                   help="your email, sent to Crossref/PubMed for their polite pools (or set REFVERIFY_MAILTO)")
    p.add_argument("--openalex-key", default=os.environ.get("OPENALEX_API_KEY"),
                   help="OpenAlex API key (or set OPENALEX_API_KEY); free keys at openalex.org")
    p.add_argument("--s2-key", default=os.environ.get("S2_API_KEY"),
                   help="Semantic Scholar API key (or set S2_API_KEY); adds Semantic Scholar to the search")
    p.add_argument("--sources", default=",".join(SEARCH_ORDER),
                   help=f"title-search order (default {','.join(SEARCH_ORDER)}; semanticscholar needs a key)")
    p.add_argument("--offline", action="store_true", help="use only cached answers")
    p.add_argument("--no-cache", action="store_true", help="do not read or write the local cache")
    p.add_argument("--workers", type=int, default=4, help="references checked in parallel (default 4)")
    p.add_argument("--version", action="version", version=f"refverify {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    order = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    unknown = [s for s in order if s not in SEARCH_ORDER]
    if unknown:
        print(f"refverify: unknown source(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    bibs: list[Path] = []
    cited: list[str] = []
    restrict = False
    for f in args.files:
        if not f.exists():
            print(f"refverify: {f}: no such file", file=sys.stderr)
            return 2
        if f.suffix.lower() == ".tex":
            scan = scan_tex(f)
            cited += [k for k in scan.cited if k not in cited]
            restrict = restrict or not scan.cites_everything
            for b in scan.bib_files:
                if b.exists() and b not in bibs:
                    bibs.append(b)
                elif not b.exists():
                    print(f"refverify: {f} names {b}, which does not exist", file=sys.stderr)
        elif f not in bibs:
            bibs.append(f)
    if not bibs:
        print("refverify: no .bib file to check", file=sys.stderr)
        return 2

    refs, seen = [], set()
    for b in bibs:
        for ref in load_bib(b):
            if ref.key not in seen:
                seen.add(ref.key)
                refs.append(ref)
    if restrict and cited and not args.all:
        wanted = set(cited)
        refs = [r for r in refs if r.key in wanted]

    cache = None if args.no_cache else Cache(default_cache_path())
    http = Http(mailto=args.mailto, cache=cache, offline=args.offline)
    src = Sources(http, mailto=args.mailto, openalex_key=args.openalex_key, s2_key=args.s2_key, search_order=order)

    progress = None
    if sys.stderr.isatty():
        def progress(done: int, total: int) -> None:
            print(f"\rChecking {done}/{total}", end="" if done < total else "\r\033[K", file=sys.stderr, flush=True)

    try:
        results = check_all(refs, src, workers=args.workers, progress=progress)
    finally:
        http.close()

    inputs = [str(p) for p in bibs]
    print(render_text(results, inputs, dict(http.calls), color=use_color(), show_all=args.show_all,
                      gave_up=sorted(src.unavailable)))
    if args.json:
        args.json.write_text(json.dumps(to_json(results, inputs), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    failing = set(_FAIL)
    if args.strict:
        failing |= {Status.UNCERTAIN, Status.ERROR}
    bad = [r for r in results if r.status in failing and (args.strict or r.severity == "high")]
    return 1 if bad else 0
