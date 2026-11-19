"""Swells: moments where the song suddenly gets louder, and the parts between them.

The envelope is the RMS level in 10 ms frames, divided by its loudest frame
(so "full scale" is the song's own peak). At each moment the mean of the next
0.6 s is compared with the mean of the previous 1.5 s; a rise of more than
0.22 is an accent. Swells keep at least 2 s apart (the stronger wins) and
are moved onto the nearest beat. Each part between swells carries the share
of its time the lead vocal is singing, when a vocal stem is given.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..timing.level import frame_db, quiet_line, working_level

FRAME_S = 0.01
AHEAD_S = 0.6
BEHIND_S = 1.5
RISE = 0.22
APART_S = 2.0


@dataclass(frozen=True)
class Swells:
    """Accent list and parts in the shape of `analysis/swells.json`."""

    swells: tuple[dict, ...]
    parts: tuple[dict, ...]

    def to_dict(self) -> dict:
        return {"swells": list(self.swells), "parts": list(self.parts)}


def _envelope(audio: np.ndarray, rate: int) -> np.ndarray:
    data = np.asarray(audio, dtype=np.float64)
    if data.ndim == 1:
        data = data[:, None]
    hop = int(round(rate * FRAME_S))
    count = data.shape[0] // hop
    chunks = data[: count * hop].reshape(count, hop, data.shape[1])
    env = np.sqrt(np.mean(chunks ** 2, axis=(1, 2)))
    top = env.max() if env.size else 0.0
    return env / top if top > 0 else env


def _rise(env: np.ndarray) -> np.ndarray:
    """Mean of the next 0.6 s less the mean of the previous 1.5 s; NaN where a window runs off the song."""
    ahead, behind = int(round(AHEAD_S / FRAME_S)), int(round(BEHIND_S / FRAME_S))
    total = np.concatenate([[0.0], np.cumsum(env)])
    out = np.full(len(env), np.nan)
    i = np.arange(behind, len(env) - ahead + 1)
    out[i] = (total[i + ahead] - total[i]) / ahead - (total[i] - total[i - behind]) / behind
    return out


def _pick(rise: np.ndarray) -> list[tuple[int, float]]:
    valid = np.nan_to_num(rise, nan=-np.inf)
    inner = (valid[1:-1] >= valid[:-2]) & (valid[1:-1] >= valid[2:]) & (valid[1:-1] > RISE)
    candidates = sorted(((float(valid[i]), i) for i in np.flatnonzero(inner) + 1), reverse=True)
    apart = int(round(APART_S / FRAME_S))
    picked: list[tuple[int, float]] = []
    for punch, i in candidates:
        if all(abs(i - j) >= apart for j, _ in picked):
            picked.append((i, punch))
    return picked


def _singing(vocal: np.ndarray | None, rate: int | None) -> np.ndarray | None:
    """Per 10 ms frame, whether the vocal stem is above its quiet line."""
    if vocal is None or rate is None:
        return None
    db = frame_db(vocal, rate)
    try:
        return db > quiet_line(working_level(db))
    except ValueError:
        return np.zeros(len(db), dtype=bool)


def _share(singing: np.ndarray | None, start: float, end: float) -> float | None:
    if singing is None:
        return None
    part = singing[int(round(start / FRAME_S)):int(round(end / FRAME_S))]
    return round(float(part.mean()), 3) if part.size else 0.0


def find_swells(audio: np.ndarray, rate: int, beats: np.ndarray, *, vocal: np.ndarray | None = None,
                 vocal_rate: int | None = None) -> Swells:
    """Swells of `audio` snapped to `beats`, and the parts they divide the song into."""
    env = _envelope(audio, rate)
    duration = round(len(audio) / rate, 3)
    beats = np.asarray(beats, dtype=np.float64)
    swells: list[dict] = []
    for i, punch in sorted(_pick(_rise(env))):
        t = i * FRAME_S
        if len(beats):
            t = float(beats[int(np.argmin(np.abs(beats - t)))])
        if swells and t - swells[-1]["t"] < APART_S:
            if punch > swells[-1]["punch"]:
                swells[-1] = {"t": round(t, 3), "punch": round(punch, 2)}
            continue
        swells.append({"t": round(t, 3), "punch": round(punch, 2)})
    edges = [0.0] + [a["t"] for a in swells] + [duration]
    singing = _singing(vocal, vocal_rate)
    parts = tuple({"from": round(a, 3), "to": round(b, 3), "vocal_on": _share(singing, a, b)}
                  for a, b in zip(edges[:-1], edges[1:]) if b > a)
    return Swells(tuple(swells), parts)
