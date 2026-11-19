"""python -m atomic_flix.lint FILM_DIR [--vet]

Preflight by default: every rule, every reviewer question, the batch's GPU hours. Writes plan/report.md (gate 5) and
plan/board.html (gate 4). Exit code 1 when anything blocks (no GPU time is to be spent), 0 when clear.
`--vet` runs the rules only and exits 1 on any block.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .book import load_book
from .engine import preflight, vet
from .report import write_reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m atomic_flix.lint", description=__doc__.split("\n\n")[1])
    parser.add_argument("film", type=Path, help="the film folder")
    parser.add_argument("--vet", action="store_true", help="rules only, no reviewer gate, no report")
    args = parser.parse_args(argv)
    try:
        book = load_book(args.film)
    except (FileNotFoundError, KeyError, ValueError) as problem:
        print(f"lint: cannot read the film: {problem}", file=sys.stderr)
        return 2
    if args.vet:
        findings = vet(book)
        for finding in findings:
            print(finding.line())
        return 1 if any(f.level == "block" for f in findings) else 0
    verdict = preflight(book)
    for finding in verdict.findings:
        print(finding.line())
    for item in verdict.open_review:
        print(f"REVIEW {item.key:<6} {item.id}: {'unanswered' if item.awaiting else item.answer}")
    account, board = write_reports(book, verdict, args.film / "plan")
    if verdict.batch is not None:
        print(f"{verdict.batch.takes} takes, about {verdict.batch.gpu_hours:.2f} GPU h")
    print(f"{'BLOCKED' if verdict.blocked else 'clear'}: {account} and {board}")
    return 1 if verdict.blocked else 0


if __name__ == "__main__":
    sys.exit(main())
