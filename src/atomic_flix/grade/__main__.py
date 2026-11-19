"""Command line for the grade.

    python -m atomic_flix.grade measure CUT.mp4 --edit EDIT.json
    python -m atomic_flix.grade apply CUT.mp4 OUT.mp4 --edit EDIT.json [--palette LOOK.json] [--crf 16] [--speed slow]

The edit (written by the cut as cuts/vNN.edit.json) says where each shot starts and ends. `apply` writes OUT.mp4 and
OUT.tone.json beside it. Run the flash check and the review boards on OUT, not on the cut.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..cut.edit import EditError, load_edit
from ..cut.media import MediaError
from . import DEFAULT_LOOK, Look, grade_cut, measure_cut, shots_from_edit


def _shots(edit_path: str):
    edit = load_edit(edit_path)
    return shots_from_edit(edit), edit.fps


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="atomic-flix grade", description=__doc__.split("\n\n")[0])
    verbs = parser.add_subparsers(dest="verb", required=True)
    measure = verbs.add_parser("measure", help="print each shot's levels, the corrections and the spread")
    measure.add_argument("cut")
    measure.add_argument("--edit", required=True, help="the edit the cut was rendered from")
    apply = verbs.add_parser("apply", help="write the graded film and its .tone.json")
    apply.add_argument("cut")
    apply.add_argument("out")
    apply.add_argument("--edit", required=True, help="the edit the cut was rendered from")
    apply.add_argument("--palette", help="a look JSON file in place of the default look")
    apply.add_argument("--crf", type=int, default=16)
    apply.add_argument("--speed", default="slow")
    args = parser.parse_args(argv)
    try:
        shots, fps = _shots(args.edit)
        if args.verb == "measure":
            print(measure_cut(args.cut, shots, fps).text())
            return 0
        look = Look.from_file(args.palette) if args.palette else DEFAULT_LOOK
        result = grade_cut(args.cut, args.out, shots, fps, look=look, crf=args.crf, x264_speed=args.speed)
    except (EditError, MediaError, ValueError, OSError) as problem:
        print(f"grade: {problem}", file=sys.stderr)
        return 2
    print(result.text())
    print(f"wrote {Path(args.out)} and {result.account}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
