"""What each section measures: how much of it the voice is on, how loud the rest stem is under it against the song's
own loudest second, whether that rises or falls across the section, and the swells inside it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..timing.level import FLOOR_DB, FRAME_S, frame_db
from .voice import LeadVoice, frame_index

PEAK_WINDOW_S = 1.0
TREND_DB = 2.0
MIXED_QUIET_S = 2.5


@dataclass(frozen=True)
class RestLevel:
    """The rest stem's power per 10 ms frame and the mean power of its loudest second."""

    power: np.ndarray
    peak: float

    def level(self, start: float, end: float) -> float:
        part = self.power[frame_index(start):frame_index(end)]
        if not part.size or self.peak <= 0:
            return 0.0
        return round(min(1.0, float(np.sqrt(part.mean() / self.peak))), 3)

    def change_db(self, start: float, end: float) -> float | None:
        """The mean power of the section's last third against its first third, in dB."""
        part = self.power[frame_index(start):frame_index(end)]
        third = len(part) // 3
        if third == 0:
            return None
        first, last = float(part[:third].mean()), float(part[-third:].mean())
        if first <= 0 or last <= 0:
            return None
        return round(10.0 * float(np.log10(last / first)), 1)


def rest_level(samples: np.ndarray | None, rate: int | None, frames: int) -> RestLevel:
    """The rest stem read to `frames` 10 ms frames (padded with silence); a missing stem reads as silence."""
    if samples is None or rate is None:
        return RestLevel(np.zeros(frames), 0.0)
    db = frame_db(samples, rate)
    power = np.where(db > FLOOR_DB, 10.0 ** (db / 10.0), 0.0)
    power = np.concatenate([power, np.zeros(max(0, frames - len(power)))])[:frames]
    window = max(1, min(len(power), int(round(PEAK_WINDOW_S / FRAME_S))))
    sums = np.concatenate([[0.0], np.cumsum(power)])
    peak = float(((sums[window:] - sums[:-window]) / window).max()) if len(power) else 0.0
    return RestLevel(power, peak)


def trend(change: float | None, level: float) -> str:
    if change is None:
        return "silent" if level == 0.0 else "steady"
    return "rises" if change >= TREND_DB else "falls" if change <= -TREND_DB else "steady"


def kind(sung: bool, quiet_s: float) -> str:
    if not sung:
        return "instrumental"
    return "mixed" if quiet_s >= MIXED_QUIET_S else "sung"


def measure(start: float, end: float, sung: bool, voice: LeadVoice, rest: RestLevel,
            swells: Sequence[dict]) -> dict:
    """The measured part of one section's record, over its measured span [start, end)."""
    quiet = voice.longest_quiet(start, end)
    level = rest.level(start, end)
    change = rest.change_db(start, end)
    return {"kind": kind(sung, quiet), "voice_share": voice.share(start, end), "longest_rest_s": round(quiet, 2),
            "rest_level": level, "change_db": change, "trend": trend(change, level),
            "swells": [dict(s) for s in swells if start <= float(s["t"]) < end]}
