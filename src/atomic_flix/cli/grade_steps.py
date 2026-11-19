"""Film step `grade`: the last step on the picture, after `cut` and before `review`.

It grades the newest cut (or `--version N`) into cuts/vNN-toned.mp4 with cuts/vNN-toned.tone.json, runs the film's
hooks in hooks/tone.d/ when asked with `--hooks` (they are programs in the film folder, so they are off by default
and each is named before it runs), and runs the flash check on the graded film (cuts/vNN-toned-strobe.json), since the flash
check and the review boards belong on what will be delivered. `review` uses the graded film when there is one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from ..cut import check_flashes, load_edit
from ..cut.edit import EditError
from ..cut.media import MediaError
from ..grade import DEFAULT_LOOK, Look, grade_cut, measure_cut, shots_from_edit
from ..grade.hooks import listed_hooks, run_hooks
from .common import Film, StepError, film_argument, parser, write_json
from .cut_steps import _versions

HOOKS = "hooks/tone.d"


def film_hooks(folder: Path, graded: Path, account: Path, *, enabled: bool,
               say: Callable[[str], None] = print) -> list[str]:
    """Run the film's grade hooks when ENABLED, naming each first; otherwise only say which ones were left alone."""
    if not enabled:
        found = listed_hooks(folder)
        if found:
            say(f"hooks not run: {', '.join(h.name for h in found)} in {HOOKS}/ (pass --hooks to run them; "
                "they are programs and run with your rights)")
        return []
    return run_hooks(folder, graded, account, announce=say)


def grade_parser():
    p = parser("grade", "Grade a cut: every shot toward the film's own black, white and colour strength (70 % of\n"
                        "the way, levels by at most 0.08, colour gain 0.85 to 1.2, flat shots keep their levels),\n"
                        "then one look over all; no grain. Prints the spread before and after, writes cuts/vNN-toned.mp4 and\n"
                        ".tone.json, runs the flash check on the graded film and, with --hooks, the programs in\n"
                        "hooks/tone.d/ (off by default; each is named before it runs). Exit code 1 when a hook fails\n"
                        "or the flash check fails. (`atomic-flix grade measure|apply ...` runs the module.)")
    film_argument(p)
    p.add_argument("--version", type=int, help="the cut's number (default: the newest)")
    p.add_argument("--palette", help="a look JSON file in place of the default look")
    p.add_argument("--measure", action="store_true", help="print the levels and the spread; write nothing")
    p.add_argument("--crf", type=int, default=16)
    p.add_argument("--speed", default="slow", help="x264 preset (veryfast for a look)")
    p.add_argument("--hooks", action="store_true",
                   help="run the film's own programs in hooks/tone.d/ after grading (off by default)")
    return p


def _grade(argv: Sequence[str]) -> int:
    p = grade_parser()
    args = p.parse_args(argv)
    film = Film.open(args.film)
    versions = _versions(film)
    if not versions:
        raise StepError("no cut yet; run `atomic-flix cut`")
    version = args.version or versions[-1]
    stem = film.path(f"cuts/v{version:02d}")
    cut = stem.with_suffix(".mp4")
    if not cut.is_file():
        raise StepError(f"{film.folder.relative(cut)} is missing; run `atomic-flix cut` again")
    try:
        edit = load_edit(stem.with_suffix(".edit.json"))
        shots = shots_from_edit(edit)
        if args.measure:
            print(measure_cut(cut, shots, edit.fps).text())
            return 0
        look = Look.from_file(args.palette) if args.palette else DEFAULT_LOOK
        out = stem.with_name(stem.name + "-toned.mp4")
        result = grade_cut(cut, out, shots, edit.fps, look=look, crf=args.crf, x264_speed=args.speed)
    except (EditError, MediaError, ValueError) as problem:
        raise StepError(f"the cut was not graded: {problem}") from None
    print(result.text())
    problems = film_hooks(film.path(HOOKS), out, result.account, enabled=args.hooks)
    for problem in problems:
        print(f"WARN  {problem}")
    flashes = check_flashes(out)
    write_json(stem.with_name(stem.name + "-toned-strobe.json"), flashes.to_dict(), "strobe")
    print(flashes.text())
    print(f"wrote {film.folder.relative(out)} and {film.folder.relative(result.account)}")
    return 0 if flashes.passed and not problems else 1


COMMANDS = {
    "grade": ("grade the cut: each shot toward the film's own levels, one look, no grain; flash check on it", _grade),
}
