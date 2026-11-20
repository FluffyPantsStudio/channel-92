"""Film step `finish`: the last step on the picture, after `grade`. The masters stay clean; the look is only here.

It takes the graded cut (cuts/vNN-toned.mp4, else the cut, cuts/vNN.mp4) and writes cuts/vNN-final.mp4: the
logo (the era's, else the channel's own; `--no-logo` or film.json `brand.logo: false` leave it off), then the
era's look (the film's year picks it, and a year between two eras' first years blends their looks; `--year YYYY`
sets another year for one run, `--era ID` lays that era's own look on; ntsc-rs from `--ntsc-rs PATH`, else
CHANNEL92_NTSC_RS, else the PATH), then the intro in front (film.json `brand.intro`: "era" for the era's own, a
path in the film folder for a clip of yours, nothing for none). The flash check runs on the final
(cuts/vNN-final-strobe.json). `--sample STILL` makes plan/look-sample.png instead, one frame of the look and logo on
a still, so the director can approve the era by eye before the batch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..aspects import FIRST_YEAR, LAST_YEAR, AspectError
from ..brand.era_intro import era_intro
from ..brand.intro import IntroError
from ..brand.logo import DEFAULT_LOGO
from ..cut import check_flashes
from ..cut.media import MediaError, probe
from ..desk.reply import DeskError
from ..desk.sink import inside
from ..eras import ERAS, Era, EraError, YearLook, resolve_look
from ..finish import NtscError, Treatment, find_ntsc_rs, finish_cut, missing_sentence, sample_still
from .common import Film, StepError, film_argument, parser, write_json
from .cut_steps import _versions

SAMPLE = "plan/look-sample.png"


def brand_of(film: Film) -> dict:
    """film.json's `brand` block: `logo` (default true) and `intro` ("era", a clip's path, or none)."""
    brand = film.data.get("brand") or {}
    if not isinstance(brand, dict):
        raise StepError('film.json brand must be an object, like {"logo": true, "intro": "era"}')
    return brand


def logo_for(film: Film, chosen: Era | None, wanted: bool = True) -> Path | None:
    """The logo `finish` lays on: the era's, else the channel's own; None when the verb or film.json leaves it off."""
    if not wanted or brand_of(film).get("logo", True) is False:
        return None
    return chosen.logo if chosen is not None else DEFAULT_LOGO


def intro_for(film: Film, chosen: Era | None, size: tuple[int, int], fps: float) -> Path | None:
    """The intro film.json names: the era's own (made once at SIZE), a clip in the film folder, or None."""
    named = brand_of(film).get("intro")
    if not named:
        return None
    if str(named).strip().lower() == "era":
        if chosen is None:
            raise StepError('film.json brand.intro is "era", and the film has no era: set its year (atomic-flix '
                            'choose FILM year YYYY) or pass --era ID')
        return era_intro(film.root, chosen, size, fps)
    clip = _inside(film, str(named), f"film.json brand.intro {named}")
    if not clip.is_file():
        raise StepError(f"film.json brand.intro names {named}, and there is no file there")
    return clip


def _inside(film: Film, relative: str | Path, what: str) -> Path:
    """FILM/RELATIVE resolved, refused (StepError) when it leads outside the film folder."""
    try:
        return inside(film.root, relative, what)
    except DeskError as problem:
        raise StepError(str(problem)) from None


def _look(film: Film, override: str | None, year: str | None) -> YearLook | None:
    try:
        return resolve_look(film.data, override, year)
    except (EraError, AspectError) as problem:
        raise StepError(str(problem)) from None


def _how(film: Film, args) -> str:
    if args.era:
        return "chosen with --era"
    if args.year is not None:
        return f"from --year {args.year}, this run only"
    return f"from the film's year {(film.data.get('setup') or {}).get('year')}"


def treatment_for(film: Film, args) -> tuple[Treatment, list[str]]:
    """What `finish` lays on, and a plain line for each choice it made."""
    look = _look(film, args.era, args.year)
    chosen = look.era if look is not None else None
    logo = logo_for(film, chosen, not args.no_logo)
    lines = [f"logo: {logo.name if logo else 'none'}"]
    if chosen is None:
        lines.append("no era: the film has no year and no --era was given, so it is finished without an era look "
                     "(atomic-flix choose FILM year YYYY)")
        return Treatment(logo=logo), lines
    lines.append(f"era {chosen.id} ({_how(film, args)}): {chosen.medium}")
    lines.append(f"look: {look.describe()}")
    if args.no_look:
        lines.append("look left off (--no-look)")
        return Treatment(logo=logo, era=chosen, year_look=look), lines
    try:
        program = find_ntsc_rs(args.ntsc_rs)
    except NtscError as problem:
        raise StepError(str(problem)) from None
    if program is None:
        lines.append(missing_sentence(chosen.id))
    return Treatment(logo=logo, era=chosen, ntsc=program, year_look=look), lines


def finish_parser():
    p = parser("finish", "Finish a cut for delivery: the logo top right, then the era's look (ntsc-rs with the era's\n"
                         "preset), then the intro in front, into cuts/vNN-final.mp4. Takes cuts/vNN-toned.mp4 when\n"
                         "there is one, else cuts/vNN.mp4; neither is ever changed. Runs the flash check on the\n"
                         "final. Without ntsc-rs the film is finished without the look and the step says where\n"
                         f"to get it. `--sample STILL` writes {SAMPLE} instead: the look and logo on one still.")
    film_argument(p)
    p.add_argument("--version", type=int, help="the cut's number (default: the newest)")
    when = p.add_mutually_exclusive_group()
    when.add_argument("--era", help=f"that era's own look, whatever the film's year: "
                                    f"{', '.join(row.id for row in ERAS)}")
    when.add_argument("--year", help=f"a year ({FIRST_YEAR} to {LAST_YEAR}) instead of the film's, for this run "
                                     "only (film.json keeps its own); a year between two eras' first years "
                                     "(1950, 1960 ... 2000) blends them")
    p.add_argument("--no-look", action="store_true", help="leave the era's look off")
    p.add_argument("--no-logo", action="store_true", help="leave the logo off (film.json brand.logo: false too)")
    p.add_argument("--ntsc-rs", help="the ntsc-rs-cli program (else CHANNEL92_NTSC_RS, else the PATH)")
    p.add_argument("--sample", type=Path, help=f"a still: write {SAMPLE}, one frame of the look and logo on it")
    p.add_argument("--crf", type=int, default=16)
    p.add_argument("--speed", default="slow", help="x264 preset (veryfast for a look)")
    return p


def _source(film: Film, version: int | None) -> tuple[int, Path]:
    versions = _versions(film)
    if not versions:
        raise StepError("no cut yet; run `atomic-flix cut` (and `atomic-flix grade`) first")
    number = version or versions[-1]
    stem = film.path(f"cuts/v{number:02d}")
    for candidate in (stem.with_name(stem.name + "-toned.mp4"), stem.with_suffix(".mp4")):
        if candidate.is_file():
            return number, candidate
    raise StepError(f"cuts/v{number:02d}.mp4 is missing; run `atomic-flix cut` again")


def _sample(film: Film, still: Path, treatment: Treatment) -> int:
    if not still.is_file():
        raise StepError(f"--sample: no still at {still}")
    width, height = film.data.get("final_size") or film.frame
    out = sample_still(still, _inside(film, SAMPLE, SAMPLE), (int(width), int(height)), film.fps, treatment)
    what = treatment.style.describe() if treatment.look else "no era look"
    print(f"wrote {film.folder.relative(out)}: {what} and {'the logo' if treatment.logo else 'no logo'} on "
          f"{still.name}; look at it before the batch")
    return 0


def _finish(argv: Sequence[str]) -> int:
    args = finish_parser().parse_args(argv)
    film = Film.open(args.film)
    treatment, lines = treatment_for(film, args)
    print("\n".join(lines))
    try:
        if args.sample is not None:
            return _sample(film, args.sample, treatment)
        number, source = _source(film, args.version)
        info = probe(source)
        intro = intro_for(film, treatment.era, (info.width, info.height), info.fps)
        out = _inside(film, f"cuts/v{number:02d}-final.mp4", "the finished film's folder (cuts/)")
        finished = finish_cut(source, out, treatment, intro, crf=args.crf, speed=args.speed)
    except (MediaError, NtscError, IntroError) as problem:
        raise StepError(f"the film was not finished: {problem}") from None
    print("\n".join(finished.notes[1:]))
    flashes = check_flashes(out)
    write_json(out.with_name(out.stem + "-strobe.json"), flashes.to_dict(), "strobe")
    print(flashes.text())
    print(f"wrote {film.folder.relative(out)} from {film.folder.relative(source)}"
          f"{' with the intro in front' if intro else ''}")
    return 0 if flashes.passed else 1


COMMANDS = {
    "finish": ("the logo, the era's look (ntsc-rs) and the intro on the graded cut: cuts/vNN-final.mp4", _finish),
}
