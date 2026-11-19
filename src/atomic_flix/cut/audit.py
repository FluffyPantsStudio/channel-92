"""The cut audit: one row per cut, saying what a viewer will get at that cut and over the shot it brings on.

Per cut: the count of the bar it lands on, the take's length against the seconds shown, the take seconds used, the
slowest and fastest playback rate, whether the take is played slower than 1x, whether a take's first two frames
show, whether the take runs out and holds its last frame, whether the cut falls inside a held note, and whether it
is a jump cut.

Rates are read over windows of the shown shot and judged against the placement's own uncertainty (`rate`), so
placement noise between neighbouring map points is not mistaken for a slowed take; the point-to-point extremes are
kept in the row for reading. Jump cuts are decided by `atomic_flix.setups`, the decision lint rule C1 makes: one setup
and crop sizes under 20 % apart.

Errors (the cut is refused): a take played slower than 1x (any window under 0.97x, whatever the placement noise), a
take that runs out and holds its last frame (that stretch plays at 0x), a take's first two frames shown, a jump cut.
Warnings (printed, kept in the report): off the bar's one and three, a held note cut through, a shot under 1.6 s,
two neighbouring shots that look alike, one setup with a crop size not recorded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import numpy as np

from ..setups import reads_as_jump, shown_size
from ..wav import read_wav
from .bars import beat_count
from .edit import Edit, Placed, Shot
from .media import ClipInfo, iter_frames, probe
from .rate import read_rates

HIDDEN_HEAD_FRAMES = 2
SHORTEST_SHOT = 1.6
LEVEL_FRAME = 0.010
HELD_WINDOW = 0.040
QUIET_BELOW_WORKING_DB = 18.0
FLOOR_DB = -60.0
WORKING_PERCENTILE = 95
LINE_EDGE = 0.05
LOOKALIKE_SIZE = (64, 36)
LOOKALIKE_LIMIT = 0.05
GOOD_COUNTS = (1, 3)

TakeInfo = ClipInfo


@dataclass
class AuditReport:
    rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"cuts": self.rows, "errors": self.errors, "warnings": self.warnings}

    def text(self) -> str:
        head = (f"{'#':>3} {'key':<8} {'song s':>8} {'film s':>7} {'count':>5} {'take s':>6} {'shown s':>7} "
                f"{'used take s':>13} {'rate':>11} {'held note':>9} {'hold s':>6} jump")
        lines = [head]
        for row in self.rows:
            count = "OFF" if row["count"] is None else str(row["count"])
            used = f"{row['used'][0]:.2f}-{row['used'][1]:.2f}"
            rate = f"{row['slowest_rate']:.2f}-{row['fastest_rate']:.2f}"
            held = {True: "YES", False: "no", None: "-"}[row["held_note"]]
            if row["held_note"] is None and row["mid_line"]:
                held = "in line"
            lines.append(f"{row['order']:>3} {row['key']:<8} {row['at']:>8.3f} {row['film_at']:>7.3f} {count:>5} "
                         f"{row['take_seconds']:>6.2f} {row['shown_seconds']:>7.2f} {used:>13} {rate:>11} "
                         f"{held:>9} {row['held_at_end']:>6.2f} {'JUMP' if row['jump_from_previous'] else ''}")
        lines += [f"ERROR {message}" for message in self.errors]
        lines += [f"WARN  {message}" for message in self.warnings]
        if not self.errors and not self.warnings:
            lines.append("clean: no errors, no warnings")
        return "\n".join(lines)


class VoiceLevel:
    """The voice stem's RMS level in 10 ms frames, with its working level and quiet line."""

    def __init__(self, path) -> None:
        samples, rate = read_wav(path)
        mono = samples.mean(axis=1)
        hop = int(round(rate * LEVEL_FRAME))
        count = len(mono) // hop
        frames = mono[:count * hop].reshape(count, hop)
        rms = np.sqrt((frames ** 2).mean(axis=1))
        self.db = 20 * np.log10(np.maximum(rms, 1e-10))
        loud = self.db[self.db > FLOOR_DB]
        working = float(np.percentile(loud, WORKING_PERCENTILE)) if loud.size else FLOOR_DB
        self.quiet_line = working - QUIET_BELOW_WORKING_DB

    def around(self, at: float) -> tuple[float, float]:
        """Mean level (dB) in the 40 ms before and the 40 ms after a time."""
        width = max(1, int(round(HELD_WINDOW / LEVEL_FRAME)))
        centre = int(round(at / LEVEL_FRAME))
        before = self.db[max(0, centre - width):centre]
        after = self.db[centre:centre + width]
        mean = lambda part: float(part.mean()) if part.size else FLOOR_DB
        return mean(before), mean(after)

    def held_through(self, at: float) -> bool:
        before, after = self.around(at)
        return before > self.quiet_line and after > self.quiet_line


def take_indices(edit: Edit, shot: Shot, placed: Placed, take_fps: float) -> np.ndarray:
    """The take frame shown on each film frame of a shot (nearest frame to the mapped take time)."""
    times = [placed.take_time(edit.song_time_of(n)) for n in range(shot.frame_in, shot.end_frame)]
    return np.floor(np.asarray(times) * take_fps + 0.5 + 1e-9).astype(int)


def _probe_all(edit: Edit, take_info: Mapping[str, ClipInfo] | None) -> dict[str, ClipInfo]:
    if take_info is not None:
        return dict(take_info)
    return {key: probe(placed.file) for key, placed in edit.takes.items()}


def _continues(prev_placed: Placed, prev_last: int, placed: Placed, first: int) -> bool:
    same_file = Path(str(prev_placed.file)) == Path(str(placed.file))
    return same_file and abs(first - (prev_last + 1)) <= 1


def _count_and_offset(edit: Edit, at: float) -> tuple[int | None, float | None]:
    if not edit.pulse or not edit.pulse.get("beats"):
        return None, None
    tolerance = max(0.03, 0.5 / edit.fps)
    count, offset = beat_count(at, edit.pulse["beats"], int(edit.pulse.get("downbeat_slot", 0)), tolerance)
    return count, offset


def _mid_line(edit: Edit, at: float) -> bool | None:
    if not edit.sung:
        return None
    return any(start + LINE_EDGE < at < end - LINE_EDGE for start, end in edit.sung)


def _row(edit: Edit, shot: Shot, placed: Placed, info: ClipInfo, voice: VoiceLevel | None) -> dict:
    indices = take_indices(edit, shot, placed, info.fps)
    rates = placed.rates_between(shot.start, shot.end)
    reading = read_rates(placed, shot.start, shot.end)
    held_frames = int(np.count_nonzero(indices > info.frames - 1))
    count, offset = _count_and_offset(edit, shot.start)
    return {
        "order": shot.order, "key": shot.key, "file": str(placed.file), "setup": placed.setup,
        "at": round(shot.start, 4), "film_at": round(shot.start - edit.start, 4),
        "grid": next((c.grid for c in edit.cuts if c.key == shot.key), None),
        "count": count, "beat_offset": None if offset is None or math.isnan(offset) else round(offset, 4),
        "take_seconds": round(info.seconds, 4), "shown_seconds": round(shot.seconds, 4),
        "used": [round(placed.take_time(shot.start), 4), round(placed.take_time(edit.song_time_of(shot.end_frame - 1)), 4)],
        "first_take_frame": int(indices[0]), "last_take_frame": int(indices[-1]),
        "slowest_rate": round(reading.slowest, 4), "fastest_rate": round(reading.fastest, 4),
        "rate_window": round(reading.slowest_window, 3), "rate_tolerance": round(reading.tolerance(), 4),
        "slowest_point_rate": round(min(rates), 4), "fastest_point_rate": round(max(rates), 4),
        "slower": reading.slower,
        "size": shown_size(placed.crop_keep, placed.crop[2] if placed.crop else None, info.width),
        "held_at_end": round(held_frames / edit.fps, 4),
        "held_note": None if voice is None else voice.held_through(shot.start),
        "voice_db": None if voice is None else [round(v, 1) for v in voice.around(shot.start)],
        "mid_line": _mid_line(edit, shot.start),
        "jump_from_previous": False,
    }


def _judge(row: dict, account: AuditReport, first_shot: bool) -> None:
    key, at = row["key"], row["at"]
    if row["slower"]:
        account.errors.append(f"{key} at {at:.3f} s plays its take slower than 1x (rate {row['slowest_rate']:.3f} over "
                             f"{row['rate_window']:.2f} s, beyond the placement's tolerance of "
                             f"{row['rate_tolerance']:.3f}); never slow a take, move the cut or speed it up")
    if row["first_take_frame"] < HIDDEN_HEAD_FRAMES:
        account.errors.append(f"{key} at {at:.3f} s shows take frame {row['first_take_frame']}: never show a take's "
                             "first two frames")
    if row["held_at_end"] > 0:
        account.errors.append(f"{key} runs past its take's end and holds its last frame for "
                             f"{row['held_at_end']:.2f} s: the take is slowed to 0x there; move the cut earlier or "
                             "use a longer take")
    if row["shown_seconds"] < SHORTEST_SHOT:
        account.warnings.append(f"{key} is on screen {row['shown_seconds']:.2f} s, under {SHORTEST_SHOT} s")
    if not first_shot and row["count"] is not None and row["count"] not in GOOD_COUNTS:
        account.warnings.append(f"cut to {key} at {at:.3f} s lands on count {row['count']}, not the bar's one or three")
    if not first_shot and row["count"] is None and row["beat_offset"] is not None:
        account.warnings.append(f"cut to {key} at {at:.3f} s is OFF GRID ({row['beat_offset'] * 1000:+.0f} ms from "
                               "the nearest beat)")
    if not first_shot and row["held_note"]:
        account.warnings.append(f"cut to {key} at {at:.3f} s falls inside a held note "
                               f"(voice {row['voice_db'][0]} dB before, {row['voice_db'][1]} dB after)")


def _lookalike(edit: Edit, prev: dict, row: dict) -> float:
    """Mean grey difference (0 to 1) between the last frame shown before a cut and the first after it."""
    pictures = []
    for file, index in ((prev["file"], prev["last_take_frame"]), (row["file"], row["first_take_frame"])):
        frames = dict(iter_frames(file, size=LOOKALIKE_SIZE, grey=True, wanted={max(0, index)}))
        if not frames:
            return 1.0
        pictures.append(next(iter(frames.values())).astype(float) / 255)
    return float(np.abs(pictures[0] - pictures[1]).mean())


def audit_edit(edit: Edit, *, take_info: Mapping[str, ClipInfo] | None = None,
               compare_frames: bool = False) -> AuditReport:
    """Audit every cut of an edit. `take_info` skips probing (tests); `compare_frames` decodes frames across cuts."""
    infos = _probe_all(edit, take_info)
    voice = VoiceLevel(edit.voice) if edit.voice else None
    account = AuditReport()
    previous: dict | None = None
    for shot in edit.shots():
        placed = edit.takes[shot.key]
        row = _row(edit, shot, placed, infos[shot.key], voice)
        if previous is not None:
            prev_placed = edit.takes[previous["key"]]
            continuing = _continues(prev_placed, previous["last_take_frame"], placed, row["first_take_frame"])
            jump = None if continuing else reads_as_jump(prev_placed.setup, previous["size"], placed.setup, row["size"])
            row["jump_from_previous"] = jump is True
            if jump:
                account.errors.append(f"jump cut: {previous['key']} and {shot.key} on setup '{placed.setup}' at sizes "
                                     f"{previous['size']:g} and {row['size']:g} side by side at {row['at']:.3f} s")
            elif jump is None and not continuing:
                account.warnings.append(f"{previous['key']} and {shot.key} are on setup '{placed.setup}' but a crop "
                                       "size is not recorded: cannot tell whether the cut reads as a jump")
            if compare_frames and not continuing:
                difference = _lookalike(edit, previous, row)
                row["difference_from_previous"] = round(difference, 4)
                if difference < LOOKALIKE_LIMIT and not row["jump_from_previous"]:
                    account.warnings.append(f"{previous['key']} and {shot.key} look alike across the cut at "
                                           f"{row['at']:.3f} s (difference {difference:.3f}): it may read as a jump")
        _judge(row, account, previous is None)
        account.rows.append(row)
        previous = row
    return account
