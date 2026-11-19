"""Sung phrases: spans of the voice stem louder than the quiet line.

A phrase opens once the smoothed level crosses the quiet line and holds above
it for MIN_RUN_S, and closes when a silence lasting MIN_PAUSE_S begins. A
long phrase is also divided at a deep valley (DIP_DB below the level on each
side), the place where a legato line flows into its successor.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .level import FRAME_S

MIN_RUN_S = 0.10
MIN_PAUSE_S = 0.12
DIP_DB = 8.0
DIP_REACH_S = 0.5
MIN_PIECE_S = 0.15
SPLIT_LONGER_THAN_S = 0.6


@dataclass(frozen=True)
class Phrase:
    """Frames [first, stop) of the level track; `voiced` counts seconds above quiet."""

    first: int
    stop: int
    vocal_on: float
    peak_db: float

    @property
    def start(self) -> float:
        return round(self.first * FRAME_S, 3)

    @property
    def end(self) -> float:
        return round(self.stop * FRAME_S, 3)


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[first, stop) frame ranges where `mask` is true."""
    if len(mask) == 0:
        return []
    edges = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


def _frames(seconds: float) -> int:
    return int(round(seconds / FRAME_S))


def _phrase(level: np.ndarray, mask: np.ndarray, first: int, stop: int) -> Phrase:
    return Phrase(first, stop, float(mask[first:stop].sum()) * FRAME_S, float(level[first:stop].max()))


def _dip_splits(level: np.ndarray, first: int, stop: int) -> list[int]:
    """Frames inside [first, stop) where the level dips 8 dB under both sides."""
    reach, edge = _frames(DIP_REACH_S), _frames(MIN_PIECE_S)
    candidates = []
    for i in range(first + edge, stop - edge):
        left = level[max(first, i - reach):i].max()
        right = level[i + 1:min(stop, i + 1 + reach)].max()
        if left - level[i] >= DIP_DB and right - level[i] >= DIP_DB:
            candidates.append(i)
    splits: list[int] = []
    group: list[int] = []
    for i in candidates + [None]:
        if group and (i is None or i != group[-1] + 1):
            values = level[group]
            lowest = [g for g, v in zip(group, values) if v == values.min()]
            middle = (lowest[0] + lowest[-1] + 1) / 2.0
            splits.append(int(round(middle)))
            group = []
        if i is not None:
            group.append(i)
    return splits


def sung_runs(level: np.ndarray, floor_db: float) -> list[tuple[int, int]]:
    """Frame ranges that are sung: above quiet for 0.10 s or more, joined across pauses under 0.12 s."""
    held = np.zeros(len(level), dtype=bool)
    for first, stop in runs(level > floor_db):
        if stop - first >= _frames(MIN_RUN_S):
            held[first:stop] = True
    joined: list[list[int]] = []
    for first, stop in runs(held):
        if joined and first - joined[-1][1] < _frames(MIN_PAUSE_S):
            joined[-1][1] = stop
        else:
            joined.append([first, stop])
    return [(a, b) for a, b in joined]


def find_vocal_spans(level: np.ndarray, floor_db: float) -> list[Phrase]:
    """Phrases of a smoothed level track (dB per 10 ms frame) against `floor_db`."""
    mask = level > floor_db
    vocal_spans: list[Phrase] = []
    for first, stop in sung_runs(level, floor_db):
        cuts = _dip_splits(level, first, stop) if stop - first > _frames(SPLIT_LONGER_THAN_S) else []
        bounds = [first] + cuts + [stop]
        for a, b in zip(bounds[:-1], bounds[1:]):
            vocal_spans.append(_phrase(level, mask, a, b))
    return vocal_spans


def vocal_spans_within(vocal_spans: list[Phrase], first: int, stop: int, level: np.ndarray, floor_db: float) -> list[Phrase]:
    """The phrases overlapping frames [first, stop), cut to that window."""
    mask = level > floor_db
    out = []
    for ph in vocal_spans:
        a, b = max(ph.first, first), min(ph.stop, stop)
        if b - a >= _frames(MIN_RUN_S):
            out.append(_phrase(level, mask, a, b))
    return out
