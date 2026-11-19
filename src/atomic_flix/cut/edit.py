"""The edit: cuts on the song's time line and the placed take each cut brings on.

A placed take carries a map from song seconds to take seconds (points from placing by sound; one point means the
take runs at 1x from there). Outside the map's first and last points the take runs at 1x. The film starts at song
time `start` and ends at `end`; output frame n shows song time start + n / fps.

The edit file (UTF-8 JSON, paths relative to its folder):

    {"fps": 24, "size": [1920, 1080], "song": "audio/mix.wav", "voice": "audio/voice.wav",
     "start": 16.0, "end": 200.0, "pulse": "analysis/pulse.json", "lines": "analysis/voice-lines.json",
     "cuts": "plan/cuts.json",
     "takes": [{"key": "S02", "file": "renders/S02/r016.mp4", "map": [[17.08, 0.40]], "shift": 0.0,
                "setup": "salt-desert-chest", "crop_keep": 1.0, "type": "vocal",
                "mouth": [0.42, 0.30, 0.16, 0.12]}]}

`cuts` is a list of {"key", "at", "grid"} or a path to a file holding {"cuts": [...]}. `crop_keep` is the shot's
crop size (the share of its setup's widest still it keeps); with `setup` it decides jump cuts (`atomic_flix.setups`).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

SAME_TIME = 1e-6


class EditError(ValueError):
    """The edit cannot be cut as written."""


@dataclass(frozen=True)
class Cut:
    key: str
    at: float
    grid: str | None = None


@dataclass(frozen=True)
class Placed:
    key: str
    file: Path | str
    map: tuple[tuple[float, float], ...]
    shift: float = 0.0
    setup: str | None = None
    kind: str = "cutaway"
    crop: tuple[int, int, int, int] | None = None
    crop_keep: float | None = None
    mouth: tuple[float, float, float, float] | None = None
    cam_move: str | None = None
    moments: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        ties = tuple((float(song), float(take)) for song, take in self.map)
        if not ties:
            raise EditError(f"{self.key}: a placed take needs at least one map point")
        for (s0, t0), (s1, t1) in zip(ties, ties[1:]):
            if s1 <= s0 or t1 < t0:
                raise EditError(f"{self.key}: map points must run forward in song and take time")
        object.__setattr__(self, "map", ties)

    def take_time(self, song_time: float) -> float:
        """Take seconds shown at a song time: linear between map points, 1x before the first and after the last."""
        ties = self.map
        first_song, first_take = ties[0]
        if len(ties) == 1 or song_time <= first_song:
            return first_take + (song_time - first_song) + self.shift
        last_song, last_take = ties[-1]
        if song_time >= last_song:
            return last_take + (song_time - last_song) + self.shift
        for (s0, t0), (s1, t1) in zip(ties, ties[1:]):
            if s0 <= song_time <= s1:
                return t0 + (t1 - t0) * (song_time - s0) / (s1 - s0) + self.shift
        raise AssertionError("unreachable")

    def rates_between(self, slice_start: float, song_to: float) -> list[float]:
        """Playback rates (take seconds per song second) of every map stretch that overlaps the interval."""
        ties = self.map
        rates = []
        if slice_start < ties[0][0] or len(ties) == 1:
            rates.append(1.0)
        for (s0, t0), (s1, t1) in zip(ties, ties[1:]):
            if s1 > slice_start and s0 < song_to:
                rates.append((t1 - t0) / (s1 - s0))
        if len(ties) > 1 and song_to > ties[-1][0]:
            rates.append(1.0)
        return rates


@dataclass(frozen=True)
class Shot:
    order: int
    key: str
    frame_in: int
    end_frame: int
    start: float
    end: float

    @property
    def seconds(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class Edit:
    fps: float
    size: tuple[int, int]
    song: Path | str | None
    start: float
    end: float
    cuts: tuple[Cut, ...]
    takes: Mapping[str, Placed]
    pulse: Mapping | None = None
    voice: Path | str | None = None
    sung: tuple[tuple[float, float], ...] = ()
    target_lufs: float = -14.0
    fade_in: float = 1.0
    fade_out: float = 1.5
    folder: Path | None = field(default=None, compare=False)

    def frame_of(self, song_time: float) -> int:
        return int(math.floor((song_time - self.start) * self.fps + 0.5))

    def song_time_of(self, frame: int) -> float:
        return self.start + frame / self.fps

    @property
    def frame_count(self) -> int:
        return self.frame_of(self.end)

    def shots(self) -> list[Shot]:
        """Shots in order, each from its cut's frame to the next cut's frame (the last to the film's end)."""
        cuts = sorted(self.cuts, key=lambda cut: cut.at)
        if not cuts:
            raise EditError("the edit has no cuts")
        for before, after in zip(cuts, cuts[1:]):
            if after.at - before.at < SAME_TIME:
                raise EditError(f"two cuts at one time: {before.key} and {after.key} at {after.at:.3f} s")
        for cut in cuts:
            if cut.key not in self.takes:
                raise EditError(f"cut {cut.key} at {cut.at:.3f} s has no placed take")
            if cut.at >= self.end:
                raise EditError(f"cut {cut.key} at {cut.at:.3f} s is at or after the film's end ({self.end:.3f} s)")
        if cuts[0].at > self.start + SAME_TIME:
            raise EditError(f"the film starts at {self.start:.3f} s but its first cut is at {cuts[0].at:.3f} s")
        total = self.frame_count
        shots = []
        for order, cut in enumerate(cuts):
            first = max(0, self.frame_of(cut.at))
            last = self.frame_of(cuts[order + 1].at) if order + 1 < len(cuts) else total
            if last <= first:
                raise EditError(f"shot {cut.key} at {cut.at:.3f} s is shorter than one frame")
            shots.append(Shot(order=order + 1, key=cut.key, frame_in=first, end_frame=last,
                              start=self.song_time_of(first), end=self.song_time_of(last)))
        return shots


def sung_intervals(lines_data: Mapping) -> list[tuple[float, float]]:
    """Sung stretches in song seconds from a voice-lines table: each line from start to end, minus its gaps."""
    spans: list[tuple[float, float]] = []
    for line in lines_data.get("lines", []):
        start, end = line.get("start"), line.get("end")
        if start is None or end is None:
            continue
        cursor = float(start)
        for gap_from, gap_to in sorted(line.get("gaps") or []):
            if gap_from > cursor:
                spans.append((cursor, float(gap_from)))
            cursor = max(cursor, float(gap_to))
        if float(end) > cursor:
            spans.append((cursor, float(end)))
    return sorted(spans)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(folder: Path, value) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else folder / path


def _cuts_from(value, folder: Path) -> tuple[Cut, ...]:
    data = _read_json(_resolve(folder, value)) if isinstance(value, str) else {"cuts": value}
    return tuple(Cut(key=str(item["key"]), at=float(item["at"]), grid=item.get("grid")) for item in data["cuts"])


def _placed_from(item: Mapping, folder: Path) -> Placed:
    return Placed(key=str(item["key"]), file=_resolve(folder, item["file"]),
                  map=tuple(tuple(point) for point in item["map"]), shift=float(item.get("shift", 0.0)),
                  setup=item.get("setup"), kind=item.get("type", "cutaway"),
                  crop=tuple(item["crop"]) if item.get("crop") else None,
                  crop_keep=float(item["crop_keep"]) if item.get("crop_keep") is not None else None,
                  mouth=tuple(item["mouth"]) if item.get("mouth") else None,
                  cam_move=item.get("cam_move"), moments=tuple(float(m) for m in item.get("moments", ())))


def edit_from_dict(spec: Mapping, folder: Path) -> Edit:
    pulse = spec.get("pulse")
    if isinstance(pulse, str):
        pulse = _read_json(_resolve(folder, pulse))
    if pulse is not None and spec.get("downbeat_slot") is not None:
        pulse = {**pulse, "downbeat_slot": int(spec["downbeat_slot"])}
    lines = spec.get("lines")
    sung: Sequence = ()
    if isinstance(lines, str):
        sung = sung_intervals(_read_json(_resolve(folder, lines)))
    elif isinstance(lines, Mapping):
        sung = sung_intervals(lines)
    elif spec.get("sung"):
        sung = [tuple(span) for span in spec["sung"]]
    takes = {placed.key: placed for placed in (_placed_from(item, folder) for item in spec["takes"])}
    cuts = _cuts_from(spec["cuts"], folder)
    return Edit(fps=float(spec.get("fps", 24)), size=tuple(int(v) for v in spec["size"]),
                song=_resolve(folder, spec.get("song")), start=float(spec.get("start", min(c.at for c in cuts))),
                end=float(spec["end"]), cuts=cuts, takes=takes, pulse=pulse, voice=_resolve(folder, spec.get("voice")),
                sung=tuple(tuple(span) for span in sung), target_lufs=float(spec.get("target_lufs", -14.0)),
                fade_in=float(spec.get("fade_in", 1.0)), fade_out=float(spec.get("fade_out", 1.5)), folder=folder)


def edit_from_project(folder, *, start: float | None = None, end: float | None = None) -> Edit:
    """Build the edit from a project folder: film.json's picks and shifts, plan/cuts.json, each pick's fit map
    (renders/<key>/rNNN.fit.json), analysis/pulse.json and analysis/voice-lines.json when present.

    The film runs from the first cut (or `start`) to `end`, else to where the last shot's take runs out.
    """
    folder = Path(folder)
    film = _read_json(folder / "film.json")
    shots = {shot["key"]: shot for shot in film.get("lineup", [])}
    takes = []
    for key, number in film.get("picks", {}).items():
        clip = folder / "renders" / key / f"r{int(number):03d}"
        fit_path = clip.with_suffix(".fit.json")
        if not fit_path.is_file():
            raise EditError(f"{key}: no placement at {fit_path}")
        shot = shots.get(key, {})
        takes.append({"key": key, "file": str(clip.with_suffix(".mp4")), "map": _read_json(fit_path)["map"],
                      "shift": film.get("shift", {}).get(key, 0.0), "setup": shot.get("setup"),
                      "type": shot.get("type", "cutaway"), "crop": film.get("crops", {}).get(key),
                      "crop_keep": shot.get("crop"),
                      "mouth": shot.get("mouth"), "cam_move": shot.get("cam_move")})
    cuts = _cuts_from("plan/cuts.json", folder)
    spec = {"fps": film.get("fps", 24), "size": film.get("final_size") or film["frame"], "song": film["stems"]["mix"],
            "voice": film["stems"].get("voice"), "cuts": [c.__dict__ for c in cuts], "takes": takes,
            "downbeat_slot": film.get("downbeat_slot"), "start": start if start is not None else min(c.at for c in cuts)}
    for name, key in (("pulse.json", "pulse"), ("voice-lines.json", "lines")):
        if (folder / "analysis" / name).is_file():
            spec[key] = f"analysis/{name}"
    if end is None:
        from .media import probe  # local: probing needs ffprobe, building the rest does not
        last = max(cuts, key=lambda c: c.at)
        placed = _placed_from(next(t for t in takes if t["key"] == last.key), folder)
        end = last.at + probe(placed.file).seconds - placed.take_time(last.at)
    spec["end"] = end
    return edit_from_dict(spec, folder)


def load_edit(path) -> Edit:
    path = Path(path)
    return edit_from_dict(_read_json(path), path.parent)
