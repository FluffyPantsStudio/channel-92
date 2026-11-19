"""Review sheets for a cold reviewer, made from the cut as shown (run it on the graded film).

Per shot:
- `NN-KEY-strip.jpg`: a frame every quarter second over the whole shot;
- `NN-KEY-motion.jpg`: the difference between each pair of those frames (bright where the picture moved), so a
  frozen picture, a stiff body or a camera drift shows as dark or as an even wash;
- `NN-KEY-ends.jpg`: every frame of the first and of the last half second;
- `NN-KEY-burst-T.jpg`: every frame of half a second from a moment (the shot's named moments, else the start of her
  singing in a vocal shot, else the middle), for smiles, mouths and gestures that two frames cannot show.
For the film: `bars-AAA-BBB.jpg` (one row per bar, a frame on each beat, a red edge where a cut came in since the
beat before) and `cuts-NN.jpg` (the last frame before and the first after every cut).
`MANIFEST.txt` names every file, what it shows and the shot's measures; `review.json` has the same as data. No
prompt text goes into either, so a reviewer reads the picture, not the intent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

from ..cut.edit import Edit, Shot
from ..cut.media import iter_frames, probe, read_frames, write_image
from ..formats import tag
from .canvas import Tile, compose, heat, stack
from .motion import (LOCKED_DRIFT_LIMIT, STILL_FLAG_SECONDS, camera_drift, end_windows, jumps, mouth_energy,
                     still_ends)

THUMB_WIDTH = 320
ANALYSIS_WIDTH = 160
MOUTH_ANALYSIS_WIDTH = 640
STRIP_SECONDS = 0.25
STRIP_COLUMNS = 8
RUN_COLUMNS = 6
BURST_SECONDS = 0.5
BARS_PER_PAGE = 8
CUTS_PER_PAGE = 24
CUT_MARK = (220, 40, 40)
BEATS_PER_BAR = 4


@dataclass
class ReviewResult:
    folder: Path
    files: list[Path] = field(default_factory=list)
    shots: list[dict] = field(default_factory=list)
    manifest: Path | None = None


def _even(value: float) -> int:
    return max(2, int(round(value / 2)) * 2)


def _size_for(width: int, frame: tuple[int, int]) -> tuple[int, int]:
    return width, _even(width * frame[1] / frame[0])


def _film_seconds(edit: Edit, frame: int) -> float:
    return frame / edit.fps


def _stem(shot: Shot) -> str:
    return f"{shot.order:02d}-{shot.key}"


def _offsets(shot: Shot, fps: float, step: float) -> list[int]:
    count = shot.end_frame - shot.frame_in
    offsets, k = [], 0
    while True:
        offset = int(round(k * step * fps))
        if offset >= count:
            return offsets
        offsets.append(offset)
        k += 1


def _strip_tiles(edit: Edit, shot: Shot, thumbs: np.ndarray, offsets: list[int]) -> list[Tile]:
    return [Tile(thumbs[o], f"+{o / edit.fps:.2f}  {_film_seconds(edit, shot.frame_in + o):.2f}") for o in offsets]


def _motion_tiles(edit: Edit, thumbs: np.ndarray, offsets: list[int]) -> list[Tile]:
    grey = thumbs.mean(axis=3) / 255.0
    tiles = []
    for before, after in zip(offsets, offsets[1:]):
        difference = np.abs(grey[after] - grey[before])
        tiles.append(Tile(heat(difference), f"+{before / edit.fps:.2f}>{after / edit.fps:.2f} D{difference.mean():.3f}"))
    if not tiles:
        tiles.append(Tile(heat(np.zeros(grey.shape[1:])), "SHORTER THAN 0.25 S"))
    return tiles


def _run_tiles(edit: Edit, shot: Shot, thumbs: np.ndarray, first: int, count: int, tag: str) -> list[Tile]:
    last = min(len(thumbs), first + count)
    return [Tile(thumbs[o], f"{tag} +{o / edit.fps:.2f}  {_film_seconds(edit, shot.frame_in + o):.2f}")
            for o in range(max(0, first), last)]


def _burst_moments(edit: Edit, shot: Shot) -> list[float]:
    placed = edit.takes[shot.key]
    if placed.moments:
        return [m for m in placed.moments if 0 <= m < shot.seconds]
    if placed.kind == "vocal":
        for start, end in edit.sung:
            if end > shot.start and start < shot.end:
                return [max(0.0, start - shot.start)]
    return [max(0.0, shot.seconds / 2 - BURST_SECONDS / 2)]


def _voiced_mask(edit: Edit, shot: Shot) -> np.ndarray:
    times = np.array([edit.song_time_of(n) for n in range(shot.frame_in, shot.end_frame)])
    mask = np.zeros(len(times), bool)
    for start, end in edit.sung:
        mask |= (times >= start) & (times < end)
    return mask


def _measure(edit: Edit, film: Path, shot: Shot, grey_frames: np.ndarray) -> tuple[dict, list[str]]:
    placed = edit.takes[shot.key]
    drift = camera_drift(grey_frames, edit.fps)
    head, tail = still_ends(grey_frames, edit.fps)
    windows = end_windows(grey_frames, edit.fps)
    inner = jumps(grey_frames, edit.fps)
    measures = {"camera_drift": drift.to_dict(), "still_head": round(head, 3), "still_tail": round(tail, 3),
                "opening": windows["opening"], "closing": windows["closing"], "jumps": [round(t, 3) for t in inner]}
    flags = []
    tolerance = 0.5 / edit.fps
    if placed.cam_move and "lock" in placed.cam_move.lower() and drift.largest > LOCKED_DRIFT_LIMIT:
        flags.append(f"camera drifts {drift.largest * 100:.1f} % of the frame on a locked camera")
    if tail >= STILL_FLAG_SECONDS - tolerance:
        flags.append(f"still at the end for {tail:.2f} s: the shot settles before the cut")
    if head >= STILL_FLAG_SECONDS - tolerance:
        flags.append(f"still at the start for {head:.2f} s: nothing moves when the shot comes on")
    flags += [f"a jump inside the shot at +{t:.2f} s (film {_film_seconds(edit, shot.frame_in) + t:.2f} s)"
              for t in inner]
    if placed.kind == "vocal" and placed.mouth:
        size = _size_for(MOUTH_ANALYSIS_WIDTH, edit.size)
        frames = read_frames(film, size=size, grey=True, start_frame=shot.frame_in,
                             count=shot.end_frame - shot.frame_in).astype(np.float64) / 255
        mouth = mouth_energy(frames, placed.mouth, _voiced_mask(edit, shot), edit.fps)
        measures["mouth"] = mouth
        flags += mouth["flags"]
    elif placed.kind == "vocal":
        measures["mouth"] = None
        flags.append("vocal shot with no mouth box: mouth energy not measured")
    return measures, flags


def _shot_sheets(edit: Edit, film: Path, shot: Shot, folder: Path, thumb_size) -> tuple[dict, list[Path]]:
    count = shot.end_frame - shot.frame_in
    thumbs = read_frames(film, size=thumb_size, start_frame=shot.frame_in, count=count)
    grey_frames = read_frames(film, size=_size_for(ANALYSIS_WIDTH, edit.size), grey=True, start_frame=shot.frame_in,
                           count=count).astype(np.float64) / 255
    stem, title = _stem(shot), f"{shot.key}  FILM {_film_seconds(edit, shot.frame_in):.2f}-" \
                               f"{_film_seconds(edit, shot.end_frame):.2f} S"
    offsets = _offsets(shot, edit.fps, STRIP_SECONDS)
    run = int(round(BURST_SECONDS * edit.fps))
    written = [write_image(folder / f"{stem}-strip.jpg", compose(_strip_tiles(edit, shot, thumbs, offsets),
                                                                 STRIP_COLUMNS, title=title + "  EVERY 0.25 S")),
               write_image(folder / f"{stem}-motion.jpg", compose(_motion_tiles(edit, thumbs, offsets), STRIP_COLUMNS,
                                                                  title=title + "  CHANGE OVER 0.25 S")),
               write_image(folder / f"{stem}-ends.jpg", stack([
                   compose(_run_tiles(edit, shot, thumbs, 0, run, "IN"), RUN_COLUMNS, title=title + "  FIRST 0.5 S"),
                   compose(_run_tiles(edit, shot, thumbs, count - run, run, "OUT"), RUN_COLUMNS, title="LAST 0.5 S")]))]
    bursts = []
    for moment in _burst_moments(edit, shot):
        first = int(round(moment * edit.fps))
        path = folder / f"{stem}-burst-{moment:.2f}.jpg"
        write_image(path, compose(_run_tiles(edit, shot, thumbs, first, run, "B"), RUN_COLUMNS,
                                  title=title + f"  EVERY FRAME FROM +{moment:.2f}"))
        written.append(path)
        bursts.append(path.name)
    measures, flags = _measure(edit, film, shot, grey_frames)
    placed = edit.takes[shot.key]
    record = {"order": shot.order, "key": shot.key, "type": placed.kind, "film_from": round(shot.start - edit.start, 3),
              "film_to": round(shot.end - edit.start, 3), "slice_start": round(shot.start, 3),
              "song_to": round(shot.end, 3), "strip_times": [round(o / edit.fps, 3) for o in offsets],
              "files": {"strip": written[0].name, "movement": written[1].name, "ends": written[2].name,
                        "bursts": bursts}, "measures": measures, "flags": flags}
    return record, written


def _shot_at(shots: list[Shot], frame: int) -> Shot:
    current = shots[0]
    for shot in shots:
        if shot.frame_in <= frame:
            current = shot
    return current


def _bar_rows(edit: Edit, shots: list[Shot]) -> list[list[tuple[int, int, float]]]:
    """Per bar, (beat count, film frame, song time) of each beat that falls inside the film."""
    beats = list(edit.pulse.get("beats", [])) if edit.pulse else []
    one = int(edit.pulse.get("downbeat_slot", 0)) if edit.pulse else 0
    rows: list[list[tuple[int, int, float]]] = []
    for index, beat in enumerate(beats):
        frame = edit.frame_of(beat)
        if frame < 0 or frame >= edit.frame_count:
            continue
        count = (index - one) % BEATS_PER_BAR + 1
        if count == 1 or not rows:
            rows.append([])
        rows[-1].append((count, frame, beat))
    return rows


def _decode_wanted(film: Path, size, frames: set[int]) -> dict[int, np.ndarray]:
    return {index: frame.copy() for index, frame in iter_frames(film, size=size, wanted=frames)}


def _bar_sheets(edit: Edit, film: Path, shots: list[Shot], folder: Path, size) -> list[Path]:
    rows = _bar_rows(edit, shots)
    if not rows:
        return []
    pictures = _decode_wanted(film, size, {frame for row in rows for _, frame, _ in row})
    written = []
    previous = None
    for page_start in range(0, len(rows), BARS_PER_PAGE):
        page = rows[page_start:page_start + BARS_PER_PAGE]
        boards = []
        for number, row in enumerate(page, start=page_start + 1):
            tiles = []
            for count, frame, _ in row:
                shot = _shot_at(shots, frame)
                cut_since = previous is not None and _shot_at(shots, previous).key != shot.key
                tiles.append(Tile(pictures[frame], f"{count}  {frame / edit.fps:.2f}  {shot.key}",
                                  CUT_MARK if cut_since else None))
                previous = frame
            boards.append(compose(tiles, BEATS_PER_BAR, title=f"BAR {number}"))
        path = folder / f"bars-{page_start + 1:03d}-{page_start + len(page):03d}.jpg"
        written.append(write_image(path, stack(boards)))
    return written


def _cut_sheets(edit: Edit, film: Path, shots: list[Shot], folder: Path, size) -> list[Path]:
    pairs = list(zip(shots, shots[1:]))
    if not pairs:
        return []
    pictures = _decode_wanted(film, size, {f for a, b in pairs for f in (b.frame_in - 1, b.frame_in)})
    written = []
    for page, start in enumerate(range(0, len(pairs), CUTS_PER_PAGE), start=1):
        tiles = []
        for before, after in pairs[start:start + CUTS_PER_PAGE]:
            at = after.frame_in / edit.fps
            tiles.append(Tile(pictures[after.frame_in - 1], f"{before.key} OUT {at - 1 / edit.fps:.2f}"))
            tiles.append(Tile(pictures[after.frame_in], f"{after.key} IN {at:.2f}", CUT_MARK))
        path = folder / f"cuts-{page:02d}.jpg"
        written.append(write_image(path, compose(tiles, 8, title="LAST FRAME BEFORE AND FIRST AFTER EACH CUT")))
    return written


def _measure_line(record: dict) -> str:
    m = record["measures"]
    drift = m["camera_drift"]
    parts = [f"camera drift {drift['largest'] * 100:.1f} % of the frame (dx {drift['dx'] * 100:+.1f} %, "
             f"dy {drift['dy'] * 100:+.1f} %)",
             f"moving apart from the camera: up to {drift.get('foreground', 0.0) * 100:.0f} % of the picture",
             f"still at the start {m['still_head']:.2f} s",
             f"still at the end {m['still_tail']:.2f} s",
             f"first 0.5 s {'STILL' if m['opening']['still'] else 'moving'}",
             f"last 0.5 s {'STILL' if m['closing']['still'] else 'moving'}",
             f"jumps {', '.join(f'+{t:.2f}' for t in m['jumps']) or 'none'}"]
    mouth = m.get("mouth")
    if mouth:
        parts.append(f"mouth energy sung {mouth['sung_energy']}, silent {mouth['silent_energy']}, ratio "
                     f"{mouth['ratio']}, correlation with the voice {mouth['correlation']}")
    elif record["type"] == "vocal":
        parts.append("mouth not measured (no mouth box)")
    return "; ".join(parts)


def _manifest(film: Path, edit: Edit, records: list[dict], film_files: dict[str, list[Path]]) -> str:
    lines = [f"Review sheets for {film.name}: {len(records)} shots, {edit.fps:g} fps, film "
             f"{edit.frame_count / edit.fps:.2f} s, made {date.today().isoformat()}.",
             "Times: '+S' is seconds into the shot; the other number is seconds into the film.",
             "Strip: a frame every 0.25 s. Motion: the change between those frames, amber where the picture moved,",
             "black where it did not (judge motion from these pairs, not from frames spread over the shot).",
             "Ends: every frame of the first and last half second. Burst: every frame of half a second.",
             "Measures are plain pixel measures; a flag is a place to look, not a verdict.", ""]
    for record in records:
        files = record["files"]
        lines.append(f"Shot {record['order']:02d}  {record['key']}  {record['type']}  film {record['film_from']:.2f}-"
                     f"{record['film_to']:.2f} s  (song {record['slice_start']:.2f}-{record['song_to']:.2f} s)")
        lines.append(f"  strip   {files['strip']}")
        lines.append(f"  motion  {files['movement']}")
        lines.append(f"  ends    {files['ends']}")
        lines += [f"  burst   {name}" for name in files["bursts"]]
        lines.append(f"  measures: {_measure_line(record)}")
        lines += [f"  FLAG {flag}" for flag in record["flags"]] or ["  flags: none"]
        lines.append("")
    lines.append("Bars: one row per bar, a frame on each beat (count, film seconds, shot); red edge = a cut came in "
                 "since the beat before.")
    lines += [f"  {path.name}" for path in film_files["bars"]] or ["  none (no beat grid given)"]
    lines.append("Cuts: the last frame before and the first frame after each cut (red edge on the incoming shot).")
    lines += [f"  {path.name}" for path in film_files["cuts"]] or ["  none (one shot)"]
    lines.append("Full-size frames of any shot: python -m atomic_flix.review frames EDIT FILM KEY OUT --at SECONDS")
    return "\n".join(lines) + "\n"


def make_review(edit: Edit, film, folder, *, thumb_width: int = THUMB_WIDTH) -> ReviewResult:
    """Write every sheet, `MANIFEST.txt` and `review.json` for a cut into `folder`."""
    film, folder = Path(film), Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    info = probe(film)
    if info.frames < edit.frame_count - 1:
        raise ValueError(f"{film.name} has {info.frames} frames; the edit needs {edit.frame_count}: is this its cut?")
    thumb_size = _size_for(thumb_width, (info.width, info.height))
    shots = edit.shots()
    result = ReviewResult(folder=folder)
    for shot in shots:
        record, written = _shot_sheets(edit, film, shot, folder, thumb_size)
        result.shots.append(record)
        result.files += written
    film_files = {"bars": _bar_sheets(edit, film, shots, folder, thumb_size),
                  "cuts": _cut_sheets(edit, film, shots, folder, thumb_size)}
    result.files += film_files["bars"] + film_files["cuts"]
    result.manifest = folder / "MANIFEST.txt"
    result.manifest.write_text(_manifest(film, edit, result.shots, film_files), encoding="utf-8")
    data = {"format": tag("review"), "film": film.name, "fps": edit.fps, "shots": result.shots,
            "bars": [p.name for p in film_files["bars"]], "cuts": [p.name for p in film_files["cuts"]]}
    (folder / "review.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    result.files += [result.manifest, folder / "review.json"]
    return result


def extract_full_frames(edit: Edit, film, key: str, folder, *, times=None, every: float | None = None) -> list[Path]:
    """Full-size PNG frames of one shot as shown, at shot seconds `times` or every `every` seconds."""
    shot = next((s for s in edit.shots() if s.key == key), None)
    if shot is None:
        raise KeyError(f"no shot {key} in the edit")
    if times is None:
        step = every or STRIP_SECONDS
        times = [k * step for k in range(int(np.ceil(shot.seconds / step - 1e-9)))]
    wanted = {}
    for t in times:
        frame = shot.frame_in + int(round(float(t) * edit.fps))
        if not shot.frame_in <= frame < shot.end_frame:
            raise ValueError(f"{key} is on screen for {shot.seconds:.2f} s; +{t} s is outside it")
        wanted[frame] = float(t)
    folder = Path(folder)
    pictures = dict(iter_frames(film, wanted=set(wanted)))
    return [write_image(folder / f"{key}-{wanted[frame]:.3f}.png", pictures[frame]) for frame in sorted(wanted)]
