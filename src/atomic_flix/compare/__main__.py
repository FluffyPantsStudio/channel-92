"""Compare a film with the first film and print or save the report.

  python -m atomic_flix.compare FILM_FOLDER --baseline BASELINE.json [--out REPORT.md]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from ..project import FilmFolder, ProjectError, load_standing
from .baseline import baseline_name, load_baseline
from .ledger import JobLogError
from .measure import measure_film
from .report import compare_film, render_report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m atomic_flix.compare", description=__doc__.splitlines()[0])
    parser.add_argument("film", type=Path, help="the film's folder")
    parser.add_argument("--baseline", type=Path, required=True, help="the first film's baseline JSON")
    parser.add_argument("--out", type=Path, help="write the Markdown here instead of printing it")
    args = parser.parse_args(argv)
    try:
        baseline = load_baseline(args.baseline)
        first = baseline_name(args.baseline)
    except (OSError, ValueError) as problem:
        print(f"compare: cannot read the baseline {args.baseline}: {problem}", file=sys.stderr)
        return 2
    folder = FilmFolder(args.film)
    try:
        standing = load_standing(folder)
        measured = measure_film(folder)
    except (ProjectError, JobLogError) as problem:
        print(f"compare: {problem}", file=sys.stderr)
        return 2
    text = render_report(compare_film(baseline, measured), film_name=standing.film, baseline_name=first)
    if args.out:
        args.out.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
