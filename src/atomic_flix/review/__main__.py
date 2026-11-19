"""Command line for review boards.

    python -m atomic_flix.review boards EDIT FILM OUT_DIR
    python -m atomic_flix.review frames EDIT FILM KEY OUT_DIR [--at SECONDS ...] [--every SECONDS]

EDIT is an edit file (see atomic_flix.cut.edit) or a project folder holding film.json. Run on the graded film.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..cut.edit import EditError, edit_from_project, load_edit
from ..cut.media import MediaError
from .sheets import extract_full_frames, make_review


def _edit(value: str):
    path = Path(value)
    return edit_from_project(path) if path.is_dir() else load_edit(path)


def _boards(args) -> int:
    result = make_review(_edit(args.edit), args.film, args.out)
    flagged = sum(1 for shot in result.shots if shot["flags"])
    print(f"wrote {len(result.files)} files to {result.folder}; {flagged} of {len(result.shots)} shots flagged")
    print(f"start with {result.manifest}")
    return 0


def _frames(args) -> int:
    written = extract_full_frames(_edit(args.edit), args.film, args.key, args.out, times=args.at, every=args.every)
    for path in written:
        print(path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m atomic_flix.review", description="Review sheets for a cut.")
    verbs = parser.add_subparsers(dest="verb", required=True)
    boards = verbs.add_parser("boards", help="strips, motion strips, ends, bursts, bar and cut sheets, manifest")
    for name in ("edit", "film", "out"):
        boards.add_argument(name)
    boards.set_defaults(run=_boards)
    frames = verbs.add_parser("frames", help="full-size frames of one shot as shown")
    for name in ("edit", "film", "key", "out"):
        frames.add_argument(name)
    frames.add_argument("--at", type=float, nargs="+", help="seconds into the shot")
    frames.add_argument("--every", type=float, help="a frame every this many seconds")
    frames.set_defaults(run=_frames)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except (EditError, MediaError, KeyError, ValueError, FileNotFoundError) as problem:
        print(f"ERROR {problem}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
