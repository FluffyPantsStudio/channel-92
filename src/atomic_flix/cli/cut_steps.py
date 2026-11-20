"""Film steps after the renders: `cut` (assemble on the plan's cuts, audit, flash check), `review` (sheets for a cold
reviewer) and `compare` (the film against the first one).

`cut` writes the edit it renders as `cuts/vNN.edit.json`, so a person can read exactly what went in: each shot's
pick, its placement map, and the song. Picks come from film.json `chosen` (the person's); a shot with exactly one
placed render uses it and says so; a shot with several and no pick stops the cut.

The cut stays clean: no logo, no look, no intro. `finish` lays those on after `grade`, so the grade never sees
them (`finish_steps.py`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from ..compare.__main__ import main as compare_main
from ..cut import CutError, EditError, check_flashes, load_edit, render_cut
from ..cut.audit import HIDDEN_HEAD_FRAMES
from ..cut.media import MediaError
from ..review import make_review
from .common import Film, StepError, film_argument, parser, read_json, relative_to, write_json

VERSION = re.compile(r"v(\d{2,})\.edit\.json")


def _placed(film: Film, key: str) -> list[int]:
    numbers = []
    for fit in sorted(film.path(f"renders/{key}").glob("r[0-9][0-9][0-9].fit.json")):
        if fit.with_name(fit.name.replace(".fit.json", ".mp4")).is_file():
            numbers.append(int(fit.name[1:4]))
    return numbers


def pick(film: Film, key: str) -> tuple[int, str]:
    """(render number, why) for one shot: the person's pick, else the only placed render."""
    picked = (film.data.get("picks") or {}).get(key)
    placed = _placed(film, key)
    if picked is not None:
        if int(picked) not in placed:
            raise StepError(f"{key}: the chosen render r{int(picked):03d} is not there or not placed "
                            "(run `atomic-flix place`)")
        return int(picked), "picks"
    if len(placed) == 1:
        return placed[0], "the only placed render"
    if not placed:
        raise StepError(f"{key} has no placed render; run `atomic-flix shoot` and `atomic-flix place`")
    raise StepError(f"{key} has {len(placed)} placed renders and no pick: the person picks one by watching them "
                    f"(film.json chosen {{\"{key}\": N}})")


def _crop_keep(film: Film, shot) -> float | None:
    """The shot's crop size, as lint rule C1 reads it: the shot list's crop, else its still's record."""
    if shot.crop is not None:
        return float(shot.crop)
    record = film.path(f"stills/{shot.key}.json")
    value = read_json(record).get("crop_keep") if record.is_file() else None
    return None if value is None else float(value)


def edit_spec(film: Film, cuts_dir: Path, size: tuple[int, int] | None = None) -> tuple[dict, list[str]]:
    """The edit for the plan's cuts, with paths relative to CUTS_DIR, and a note per pick."""
    shots = {shot.key: shot for shot in film.shots()}
    tasks = film.tasks()
    cuts = film.cuts()
    stems = film.data.get("stems") or {}
    if film.stem("mix") is None:
        raise StepError("the cut lays the mix back over the picture: audio for stems.mix is missing")
    takes, notes = [], []
    for cut in cuts:
        key = cut["key"]
        number, why = pick(film, key)
        clip = film.path(f"renders/{key}/r{number:03d}.mp4")
        fit = read_json(clip.with_suffix(".fit.json"))
        mapping = fit.get("map") or [[float(tasks[key]["slice_start"]), 0.0]]
        shot = shots[key]
        takes.append({"key": key, "file": relative_to(clip, cuts_dir), "map": mapping,
                      "shift": float((film.data.get("shift") or {}).get(key, 0.0)), "setup": shot.setup,
                      "type": shot.kind, "crop": (film.data.get("crops") or {}).get(key),
                      "crop_keep": _crop_keep(film, shot), "cam_move": shot.cam_move})
        notes.append(f"{key}: r{number:03d} ({why}, placed {fit.get('how', '?')})")
    # A render's first frames are never shown. The plan starts each slice before its shot comes on, but a film
    # that opens at song time 0 has no time before it: the film then starts once those frames have passed.
    first = tasks[cuts[0]["key"]]
    start = max(float(cuts[0]["at"]), float(first["slice_start"]) + HIDDEN_HEAD_FRAMES / film.fps)
    if start > float(cuts[0]["at"]):
        notes.append(f"the film starts at {start:.3f} s, not {float(cuts[0]['at']):.3f} s: the first render's first "
                     f"{HIDDEN_HEAD_FRAMES} frames are not shown")
    spec = {"fps": film.fps, "size": list(size or film.data.get("final_size") or film.frame),
            "song": relative_to(film.path(stems["mix"]), cuts_dir), "start": round(start, 6),
            "end": float(tasks[cuts[-1]["key"]]["shown_at"][1]), "cuts": relative_to(film.path("plan/cuts.json"),
                                                                                      cuts_dir),
            "downbeat_slot": film.data.get("downbeat_slot"), "takes": takes}
    if film.stem("voice") is not None:
        spec["voice"] = relative_to(film.path(stems["voice"]), cuts_dir)
    for key, name in (("pulse", "pulse.json"), ("lines", "voice-lines.json")):
        if film.path(f"analysis/{name}").is_file():
            spec[key] = relative_to(film.path(f"analysis/{name}"), cuts_dir)
    return spec, notes


def _versions(film: Film) -> list[int]:
    folder = film.path("cuts")
    return sorted(int(m.group(1)) for p in folder.glob("v*.edit.json") if (m := VERSION.fullmatch(p.name)))


def _size(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    width, _, height = text.lower().partition("x")
    return int(width), int(height)


def _cut(argv: Sequence[str]) -> int:
    p = parser("cut", "Assemble the next numbered cut on the plan's bar-line cuts: write cuts/vNN.edit.json, render\n"
                      "cuts/vNN.mp4 in one encode with the song at -14 LUFS, audit every cut (cuts/vNN.audit.json)\n"
                      "and run the flash check (cuts/vNN-strobe.json). Exit code 1 on an audit error or a failed\n"
                      "flash check. (`atomic-flix cut audit|encode|flash ...` runs the cut module itself.)")
    film_argument(p)
    p.add_argument("--size", help="WxH instead of film.json deliver (a smaller size for a quick look)")
    p.add_argument("--speed", default="medium", help="x264 preset (slow for delivery, veryfast for a look)")
    p.add_argument("--crf", type=int, default=16)
    args = p.parse_args(argv)
    film = Film.open(args.film)
    version = (_versions(film) or [0])[-1] + 1
    cuts_dir = film.path("cuts")
    spec, notes = edit_spec(film, cuts_dir, _size(args.size))
    edit_path = write_json(cuts_dir / f"v{version:02d}.edit.json", spec, "edit")
    out = cuts_dir / f"v{version:02d}.mp4"
    print("\n".join(notes))
    try:
        result = render_cut(load_edit(edit_path), out, crf=args.crf, x264_speed=args.speed)
    except (CutError, EditError, MediaError) as problem:
        raise StepError(f"the cut was not rendered: {problem}") from None
    print(result.audit.text())
    write_json(cuts_dir / f"v{version:02d}.audit.json", {**result.audit.to_dict(), "audio": result.audio,
                                                          "warnings_all": result.warnings}, "audit")
    flashes = check_flashes(out)
    write_json(cuts_dir / f"v{version:02d}-strobe.json", flashes.to_dict(), "strobe")
    print(flashes.text())
    print(f"wrote {film.folder.relative(out)}")
    return 0 if flashes.passed and not result.audit.errors else 1


def _review(argv: Sequence[str]) -> int:
    p = parser("review", "Review sheets of a cut for a cold reviewer who never read the prompts: per shot a strip, a\n"
                         "motion strip, the first and last half second and bursts; bar and cut sheets; MANIFEST.txt\n"
                         "with each shot's measures and flags, in review/vNN/. Uses cuts/vNN-toned.mp4 when there\n"
                         "is one. (`atomic-flix review boards|frames ...` runs the review module itself.)")
    film_argument(p)
    p.add_argument("--version", type=int, help="the cut's number (default: the newest)")
    args = p.parse_args(argv)
    film = Film.open(args.film)
    versions = _versions(film)
    if not versions:
        raise StepError("no cut yet; run `atomic-flix cut`")
    version = args.version or versions[-1]
    stem = film.path(f"cuts/v{version:02d}")
    picture = stem.with_name(stem.name + "-toned.mp4")
    picture = picture if picture.is_file() else stem.with_suffix(".mp4")
    result = make_review(load_edit(stem.with_suffix(".edit.json")), picture, film.path(f"review/v{version:02d}"))
    flagged = [shot for shot in result.shots if shot["flags"]]
    for shot in flagged:
        print(f"{shot.get('key')}: " + "; ".join(shot["flags"]))
    print(f"{len(flagged)} of {len(result.shots)} shots flagged; start with {film.folder.relative(result.manifest)}")
    return 0


def _compare(argv: Sequence[str]) -> int:
    return compare_main(list(argv))


COMMANDS = {
    "cut": ("assemble the next cut on the plan's cuts, audit it and check it for flashes", _cut),
    "review": ("review boards of a cut for a cold reviewer (review/vNN/)", _review),
    "compare": ("the film against the first film's baseline (Markdown)", _compare),
}
