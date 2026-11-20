"""Where the lead stem sings: a per-frame on/off track and the sung regions with their tails.

The yardstick is the timing stage's own (`timing.level`): 10 ms frames, the stem's working level, and the quiet line
18 dB under it. A frame is "voice on" when the smoothed level is over the quiet line. A sung region is a run of sung
frames (`timing.phrases.sung_runs`) widened at each edge while the level, smoothed over a quarter second, stays over
a tail line 28 dB under the working level (the held note and its decay still belong to the singing), with regions
under JOIN_S apart joined into one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..timing.level import FLOOR_DB, FRAME_S, frame_db, quiet_line, running_median, working_level
from ..timing.phrases import runs, sung_runs

SMOOTH_FRAMES = 5
TAIL_BELOW_WORKING_DB = 28.0
TAIL_SMOOTH_FRAMES = 25
JOIN_S = 2.0
MIN_REGION_S = 0.3


@dataclass(frozen=True)
class LeadVoice:
    """The lead stem's voice-on frames and sung regions; `working_db` is None for a silent stem."""

    on: np.ndarray
    regions: tuple[tuple[float, float], ...]
    working_db: float | None

    def on_seconds(self, start: float, end: float) -> float:
        return float(self.on[frame_index(start):frame_index(end)].sum()) * FRAME_S

    def share(self, start: float, end: float) -> float:
        part = self.on[frame_index(start):frame_index(end)]
        return round(float(part.mean()), 3) if part.size else 0.0

    def longest_quiet(self, start: float, end: float) -> float:
        """The longest stretch in [start, end) with the voice off, in seconds."""
        part = self.on[frame_index(start):frame_index(end)]
        return max(((b - a) * FRAME_S for a, b in runs(~part)), default=0.0)


def frame_index(seconds: float) -> int:
    """The 10 ms frame a time in seconds falls on (never below 0)."""
    return max(0, int(round(seconds / FRAME_S)))


def _widen(first: int, stop: int, tail: np.ndarray, line: float) -> tuple[int, int]:
    while first > 0 and tail[first - 1] > line:
        first -= 1
    while stop < len(tail) and tail[stop] > line:
        stop += 1
    return first, stop


def _join(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    joined: list[tuple[int, int]] = []
    for first, stop in sorted(spans):
        if joined and (first - joined[-1][1]) * FRAME_S < JOIN_S:
            joined[-1] = (joined[-1][0], max(stop, joined[-1][1]))
        else:
            joined.append((first, stop))
    return joined


def lead_voice(samples: np.ndarray, rate: int, frames: int | None = None) -> LeadVoice:
    """Read the lead stem; `frames` pads (with silence) or cuts the track to the song's length in 10 ms frames."""
    db = frame_db(samples, rate)
    if frames is not None:
        db = np.concatenate([db, np.full(max(0, frames - len(db)), FLOOR_DB)])[:frames]
    try:
        working = working_level(db)
    except ValueError:
        return LeadVoice(np.zeros(len(db), dtype=bool), (), None)
    level = running_median(db, SMOOTH_FRAMES)
    tail = running_median(db, TAIL_SMOOTH_FRAMES)
    floor = quiet_line(working)
    widened = [_widen(a, b, tail, working - TAIL_BELOW_WORKING_DB) for a, b in sung_runs(level, floor)]
    regions = tuple((round(a * FRAME_S, 2), round(b * FRAME_S, 2)) for a, b in _join(widened)
                    if (b - a) * FRAME_S >= MIN_REGION_S)
    return LeadVoice(level > floor, regions, working)
