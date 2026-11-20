"""What each gate's packet carries (docs/desk.md has the table). Each builder adds files to the sink in send order
and returns the facts its card states."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..barmap.click import RATE, mix_over, render_clicks, to_rate
from ..cut.media import MediaError, probe, read_frames
from ..plan import PlanError, parse_shot_list
from ..project.layout import PULSE_FILE as PULSE
from ..project.layout import STRUCTURE_FILE as STRUCTURE
from ..project.layout import STRUCTURE_PAGE_FILE as STRUCTURE_PAGE
from ..project.layout import VOICE_LINES_FILE as VOICE_LINES
from ..wav import WavError, read_wav
from .pictures import (SCREEN_LONG_SIDE, SHEET_LONG_SIDE, SHOTS_PER_SHEET, THUMB_WIDTH, BoardShot, clock,
                       contact_sheet, fit_size, placeholder, tile_boxes, tile_names, timeline_strip)
from .reply import DeskError
from .sink import Sink, inside

BUDGET = "plan/budget.json"
LOOK_SAMPLE = "plan/look-sample.png"
CONCEPT_SUFFIXES = (".md", ".txt")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
MUSIC_GAIN_DB = -6.0
_CUT_NAME = re.compile(r"cuts/v(\d+)")


@dataclass(frozen=True)
class GateContext:
    """One film at one asked gate: its folder, film.json, the gate's record and title."""

    root: Path
    data: dict
    shown: tuple[str, ...]
    title: str

    def file(self, relative: str) -> Path:
        return inside(self.root, relative)

    def json(self, relative: str, why: str) -> Any:
        path = self.file(relative)
        if not path.is_file():
            raise DeskError(f"{relative} is missing: {why}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as problem:
            raise DeskError(f"{relative} cannot be read: {problem}") from None


def _still(path: Path, size: tuple[int, int] | None = None) -> np.ndarray:
    try:
        return read_frames(path, size=size, count=1)[0]
    except MediaError as problem:
        raise DeskError(f"{path.name}: {problem}") from None


def _scaled(path: Path, long_side: int) -> np.ndarray:
    """The picture at PATH brought down (never up) to LONG_SIDE."""
    try:
        info = probe(path)
    except MediaError as problem:
        raise DeskError(f"{path.name}: {problem}") from None
    return _still(path, fit_size(info.width, info.height, long_side))


def _strip(ctx: GateContext, sink: Sink) -> None:
    structure = ctx.json(STRUCTURE, "run `atomic-flix structure FILM` first")
    try:
        picture = timeline_strip(structure, ctx.title)
    except (ValueError, KeyError, TypeError) as problem:
        raise DeskError(f"{STRUCTURE}: {problem}") from None
    gaps = len((structure.get("pacing") or {}).get("story_gaps") or [])
    sink.picture("timeline", picture, f"the song's timeline: sections sung, mixed and instrumental, with times; "
                 f"{gaps} story gap{'' if gaps == 1 else 's'} outlined (stretches the pictures carry)",
                 "the song's timeline", png=True)


def concept(ctx: GateContext, sink: Sink) -> list[str]:
    _strip(ctx, sink)
    page = inside(ctx.root, STRUCTURE_PAGE)
    documents = [item for item in ctx.shown if Path(item).suffix.lower() in CONCEPT_SUFFIXES
                 and inside(ctx.root, item) != page]
    if not documents:
        raise DeskError("gate 1 was asked without a concept document (a .md or .txt in --shown): ask it again with "
                        "the pitches or the plot")
    for item in documents:
        path = ctx.file(item)
        if not path.is_file():
            raise DeskError(f"{item} was shown at gate 1 but is missing")
        sink.text("concept", path.read_text(encoding="utf-8"), f"the concept as asked ({item}): send its text as "
                  "a message", "the concept text, sent as a message")
    return []


def _mix(ctx: GateContext) -> tuple[np.ndarray, int]:
    relative = (ctx.data.get("stems") or {}).get("mix")
    if not relative:
        raise DeskError("film.json names no mix (stems.mix); the song gate plays the finished song")
    try:
        samples, rate = read_wav(ctx.file(relative))
    except (OSError, WavError) as problem:
        raise DeskError(f"{relative} cannot be read: {problem}") from None
    return (samples.mean(axis=1) if samples.ndim == 2 else samples), rate


def song(ctx: GateContext, sink: Sink) -> list[str]:
    pulse = ctx.json(PULSE, "run `atomic-flix bars FILM` first")
    slot, beats = pulse.get("downbeat_slot"), pulse.get("beats") or []
    if slot not in (0, 1, 2, 3) or not beats:
        raise DeskError(f"{PULSE} has no bar's one (downbeat_slot): set film.json downbeat_slot to the slot to try "
                        "and run `atomic-flix bars FILM` again")
    music, rate = _mix(ctx)
    music = to_rate(music, rate, RATE)
    mixed = mix_over(render_clicks(beats, slot, RATE, extent=len(music)), music, MUSIC_GAIN_DB)
    first = beats[slot]
    where = f"the loud high click is the bar's one: beat slot {slot}, every fourth beat from {first:.2f} s"
    sink.audio("song-click", mixed, RATE, f"the finished song with a click; {where} (analysis/pulse.json); count "
               "ONE two three four along", "the song with the click")
    _strip(ctx, sink)
    return [f"The loud high click marks the bar's one (slot {slot}, first at {first:.2f} s)."]


def _image_items(ctx: GateContext) -> list[tuple[str, Path]]:
    found = [(item, ctx.file(item)) for item in ctx.shown if Path(item).suffix.lower() in IMAGE_SUFFIXES]
    missing = [item for item, path in found if not path.is_file()]
    if missing or not found:
        raise DeskError(f"gate 3 shows stills; {', '.join(missing) or 'none was named in --shown'} "
                        f"{'is missing' if missing else ''}".strip())
    return found


def looks(ctx: GateContext, sink: Sink) -> list[str]:
    stills = [(item, path, _still(path)) for item, path in _image_items(ctx)]
    for item, path, full in stills:
        height, width = full.shape[:2]
        sink.picture(f"{path.stem}-screen", _scaled(path, SCREEN_LONG_SIDE),
                     f"{item} at screen size ({width}x{height} at full size)", "stills at screen size")
    for item, path, full in stills:
        height, width = full.shape[:2]
        for number, ((left, top, right, bottom), name) in enumerate(zip(tile_boxes(width, height),
                                                                        tile_names(width, height)), 1):
            sink.picture(f"{path.stem}-tile{number}", full[top:bottom, left:right],
                         f"{item}, zoom tile {number} of 6 ({name}) at native pixels, x {left} to {right}, "
                         f"y {top} to {bottom}: faces, collar, hands", "zoom tiles at native pixels, six per still")
    sample = ctx.file(LOOK_SAMPLE)
    if sample.is_file():
        sink.picture("look-sample", _scaled(sample, SCREEN_LONG_SIDE),
                     f"the era look sample ({LOOK_SAMPLE}): one frame with the film's era look and logo",
                     "the era look sample")
    return []


def _shot_time(root: Path, shot, lines: dict) -> float | None:
    task = inside(root, f"plan/{shot.key}.task.json", f"shot {shot.key}'s plan task")
    if task.is_file():
        try:
            shown_at = json.loads(task.read_text(encoding="utf-8")).get("shown_at")
            if shown_at:
                return float(shown_at[0])
        except (OSError, ValueError, TypeError, AttributeError) as problem:
            raise DeskError(f"plan/{shot.key}.task.json cannot be read: {problem}") from None
    starts = [lines[key]["start"] for key in shot.sings if lines.get(key, {}).get("start") is not None]
    if starts:
        return float(min(starts))
    try:
        return float(shot.at) if shot.at else None
    except ValueError:
        return None


def _board_shots(ctx: GateContext) -> list[BoardShot]:
    lineup = ctx.file(ctx.data.get("lineup_rows") or "shots.txt")
    if not lineup.is_file():
        raise DeskError("gate 4 shows the board, and there is no shot list")
    try:
        shots = parse_shot_list(lineup.read_text(encoding="utf-8"))
    except PlanError as problem:
        raise DeskError(f"the shot list: {problem}") from None
    lines = ({row["id"]: row for row in ctx.json(VOICE_LINES, "").get("lines", [])}
             if ctx.file(VOICE_LINES).is_file() else {})
    board = []
    for number, shot in enumerate(shots, 1):
        still = ctx.file(shot.still or f"stills/{shot.key}.png")
        text = " / ".join(lines[key]["text"] for key in shot.sings if key in lines)
        board.append(BoardShot(number, shot.key, _shot_time(ctx.root, shot, lines), text, _thumb(still)))
    return board


def _thumb(still: Path) -> np.ndarray:
    """A shot's first frame at contact-sheet width, or a marked blank when it has none yet."""
    if not still.is_file():
        return placeholder(THUMB_WIDTH, THUMB_WIDTH * 9 // 16 // 2 * 2, "NO STILL")
    try:
        info = probe(still)
    except MediaError as problem:
        raise DeskError(f"{still.name}: {problem}") from None
    return _still(still, (THUMB_WIDTH, max(2, int(round(THUMB_WIDTH * info.height / info.width / 2)) * 2)))


def board(ctx: GateContext, sink: Sink) -> list[str]:
    shots = _board_shots(ctx)
    pages = [shots[at:at + SHOTS_PER_SHEET] for at in range(0, len(shots), SHOTS_PER_SHEET)]
    for page_number, page in enumerate(pages, 1):
        listed = "; ".join(f"{s.number} {s.key} at {clock(s.at, tenths=True) if s.at is not None else 'no time'}"
                           + (f" \"{s.lines}\"" if s.lines else "") for s in page)
        sink.picture(f"board-{page_number}", contact_sheet(page, page_number, len(pages)),
                     f"sheet {page_number} of {len(pages)}: shots {page[0].number} to {page[-1].number}: {listed}",
                     "contact sheets, six shots each, numbered by shot")
    return []


def spend(ctx: GateContext, sink: Sink) -> list[str]:
    budget = ctx.json(BUDGET, "run `atomic-flix budget FILM` first")
    try:
        takes, (width, height) = int(budget["takes"]), budget["size"]
        hours = float(budget.get("gpu_hours") or float(budget["busy_s"]) / 3600)
    except (KeyError, TypeError, ValueError) as problem:
        raise DeskError(f"{BUDGET} cannot be read: {problem}") from None
    prompts = len(list((ctx.root / "plan").glob("*.prompt.txt")))
    basis = f" ({budget['basis']})" if budget.get("basis") else ""
    return [f"The batch: {prompts} render prompts, {takes} renders at {width}x{height}, {hours:.2f} GPU hours"
            f"{basis}, from {BUDGET}."]


def _cut_version(ctx: GateContext) -> int:
    for item in ctx.shown:
        found = _CUT_NAME.search(item.replace("\\", "/"))
        if found:
            return int(found.group(1))
    versions = [int(m.group(1)) for p in (ctx.root / "cuts").glob("v*.mp4")
                if (m := _CUT_NAME.search(f"cuts/{p.name}"))]
    if not versions:
        raise DeskError("gate 6 shows the cut, and cuts/ has none")
    return max(versions)


def _film_source(ctx: GateContext, version: int) -> tuple[str, list[str]]:
    """The cut gate 6 shows: the final, unless the toned cut or the cut is newer (a re-grade or a re-cut after
    `finish`), then the toned cut, then the cut; with a card fact when a stale final was passed over."""
    final, *masters = [f"cuts/v{version:02d}-final.mp4", f"cuts/v{version:02d}-toned.mp4", f"cuts/v{version:02d}.mp4"]
    there = [name for name in masters if ctx.file(name).is_file()]
    if ctx.file(final).is_file():
        newer = [name for name in there if ctx.file(name).stat().st_mtime > ctx.file(final).stat().st_mtime]
        if not newer:
            return final, []
        return there[0], [f"{final} is older than {newer[0]}, so the phone film is {there[0]}: run `finish` again."]
    if not there:
        raise DeskError(f"none of {final}, {', '.join(masters)} is there")
    return there[0], []


def _sheets(ctx: GateContext, sink: Sink, version: int) -> list[Path]:
    """The review sheets of review/vNN: pictures of the film's own, never a link and never one leading out."""
    folder = ctx.file(f"review/v{version:02d}")
    found = sorted(p for p in folder.glob("*") if p.suffix.lower() in IMAGE_SUFFIXES) if folder.is_dir() else []
    kept = []
    for sheet in found:
        if sheet.is_symlink() or not sheet.resolve().is_relative_to(ctx.root):
            sink.notes.append(f"review/v{version:02d}/{sheet.name} skipped: a link or outside the film folder")
        elif sheet.is_file():
            kept.append(sheet)
    return kept


def v1(ctx: GateContext, sink: Sink) -> list[str]:
    version = _cut_version(ctx)
    source, facts = _film_source(ctx, version)
    sink.video(f"film-v{version:02d}-phone", ctx.file(source), f"the film for a phone (720p), from {source}",
               "the film for a phone")
    sheets = _sheets(ctx, sink, version)
    if not sheets:
        sink.notes.append(f"no review sheets in review/v{version:02d}")
    for number, sheet in enumerate(sheets, 1):
        sink.picture(f"sheet-{number:02d}", _scaled(sheet, SHEET_LONG_SIDE),
                     f"sheet {number} of {len(sheets)}: review/v{version:02d}/{sheet.name}", "review sheets")
    return facts


BUILDERS: dict[str, Callable[[GateContext, Sink], list[str]]] = {
    "concept": concept, "song": song, "looks": looks, "board": board, "spend": spend, "v1": v1}
NOUNS = {"concept": "part", "song": "bar or time", "looks": "file", "board": "shot", "spend": "item",
         "v1": "shot or sheet"}
