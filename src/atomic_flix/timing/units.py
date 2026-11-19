"""The pieces of singing a line may start on: sung runs cut at every plausible join.

A sung run (louder than the quiet line for at least MIN_RUN_S, with silences
shorter than MIN_PAUSE_S bridged over) is cut at

* every dip of 3 dB or more under the louder side's peak within 0.5 s
  (deeper dips are likelier joins between two lines), and
* where word labels put the join between two lines (spec step 4), and
* where a stretch between cuts is longer than 1 s, a cut every 0.25 s.
  These "grid" cuts carry no evidence at all; they exist so that a line run
  together with the next one (legato with no dip) can still be split off by
  its length instead of shifting every later line by one.

Each piece knows what a line starting on it costs: nothing after a pause, a
little at a deep dip, more at a shallow one, most at a grid cut. A quiet
piece inside a run (peak under 6 dB below the working level) costs more
again: in a legato valley the quiet part is the tail of the line before, and
the next line starts where the voice rises out of it. After a real pause a
quiet first piece is normal (a consonant, a soft attack) and costs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .level import FRAME_S
from .phrases import sung_runs

CUT_DIP_DB = 3.0
DIP_SCALE_DB = 8.0
DIP_REACH_S = 0.5
MIN_PIECE_S = 0.15
GRID_S = 0.25
GRID_LONGER_S = 1.0
DIP_CUT_COST = 1.0
GRID_CUT_COST = 2.8
LABEL_CUT_COST = 0.5
TAIL_OVER_QUIET_DB = 12.0
TAIL_COST = 0.6
SAME_CUT_S = 0.05
SONG_START_PAUSE_S = 99.0


@dataclass(frozen=True)
class Unit:
    """Frames [first, stop) of the level track, and how a line starting here begins."""

    first: int
    stop: int
    vocal_on: float
    peak_db: float
    pause_before: float
    cut: str
    depth_db: float
    cut_cost: float

    @property
    def start(self) -> float:
        return round(self.first * FRAME_S, 3)

    @property
    def end(self) -> float:
        return round(self.stop * FRAME_S, 3)


def _frames(seconds: float) -> int:
    return int(round(seconds / FRAME_S))


def _dips(level: np.ndarray, first: int, stop: int) -> list[tuple[int, float]]:
    """(frame, depth in dB) of the local minima at least 3 dB deep, thinned to 0.15 s apart."""
    reach, edge = _frames(DIP_REACH_S), _frames(MIN_PIECE_S)
    found = []
    for i in range(first + edge, stop - edge):
        if level[i] > level[i - 1] or level[i] > level[i + 1]:
            continue
        left = level[max(first, i - reach):i].max()
        right = level[i + 1:min(stop, i + 1 + reach)].max()
        depth = float(min(left, right) - level[i])
        if depth >= CUT_DIP_DB:
            found.append((i, depth))
    kept: list[tuple[int, float]] = []
    for frame, depth in sorted(found, key=lambda fd: -fd[1]):
        if all(abs(frame - other) >= edge for other, _ in kept):
            kept.append((frame, depth))
    return sorted(kept)


def _grid(ties: list[int]) -> list[int]:
    """Evenly spaced cuts inside every stretch between `points` longer than 1 s."""
    step, edge = _frames(GRID_S), _frames(MIN_PIECE_S)
    out = []
    for lo, hi in zip(ties[:-1], ties[1:]):
        if (hi - lo) * FRAME_S <= GRID_LONGER_S:
            continue
        frame = lo + step
        while frame <= hi - edge:
            out.append(frame)
            frame += step
    return out


def dip_cost(depth_db: float) -> float:
    """Cost of a line starting at a dip: full at 3 dB, falling by e for every 5 dB deeper.

    It never reaches zero, so of two deep dips close together the deeper is
    the likelier join.
    """
    return DIP_CUT_COST * float(np.exp(-(depth_db - CUT_DIP_DB) / DIP_SCALE_DB))


def _run_cuts(level: np.ndarray, first: int, stop: int, extra: list[int]) -> list[tuple[int, str, float, float]]:
    dips = _dips(level, first, stop)
    edge, same = _frames(MIN_PIECE_S), _frames(SAME_CUT_S)
    known = [first, stop] + [f for f, _ in dips]
    joins = [f for f in extra if first + edge <= f <= stop - edge and all(abs(f - k) > same for k in known)]
    grid = _grid(sorted([first] + [f for f, _ in dips] + joins + [stop]))
    cuts = ([(f, "dip", d, dip_cost(d)) for f, d in dips] + [(f, "label", 0.0, LABEL_CUT_COST) for f in joins]
            + [(f, "grid", 0.0, GRID_CUT_COST) for f in grid if all(abs(f - j) > _frames(GRID_S) / 2 for j in joins)])
    return sorted(cuts)


def find_units(level: np.ndarray, floor_db: float, joins: tuple[float, ...] = ()) -> list[Unit]:
    """Every piece of every sung run, in time order.

    `joins` are extra cut times (seconds), such as where word labels put the
    join between two lines; they are kept unless a dip already sits there.
    """
    extra = sorted(_frames(t) for t in joins)
    mask = level > floor_db
    out: list[Unit] = []
    previous_stop = None
    for first, stop in sung_runs(level, floor_db):
        pause = SONG_START_PAUSE_S if previous_stop is None else (first - previous_stop) * FRAME_S
        heads = [(first, "pause", np.inf, 0.0)] + _run_cuts(level, first, stop, extra)
        tails = [h[0] for h in heads[1:]] + [stop]
        for (a, kind, depth, cost), b in zip(heads, tails):
            peak = float(level[a:b].max())
            if kind != "pause" and peak < floor_db + TAIL_OVER_QUIET_DB:
                cost += TAIL_COST
            out.append(Unit(a, b, float(mask[a:b].sum()) * FRAME_S, peak,
                            pause if kind == "pause" else 0.0, kind, float(depth), cost))
        previous_stop = stop
    return out
