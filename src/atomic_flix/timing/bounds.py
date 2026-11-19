"""Where word labels put the join between two lines (spec step 4).

For two neighbouring lines that both have labels, look at the lowest point of
the smoothed level between the end of the first line's last word and the end
of the second line's first word.

* Under the quiet line (a real pause): the first line ends where its voice
  falls into quiet before that point, and the second starts where the level
  next rises and stays up for 0.10 s.
* Not under it (legato): both lines meet at the level dip nearest the
  midpoint between the two words, searched within 0.25 s either side. The
  nearest dip, not the deepest: over a wide stretch the deepest is often a
  consonant inside a word.

These joins are offered to the global choice (`align`) as cuts; they do not
decide line times by themselves. `trusted_start` is the spec's guard for a
recogniser that drags the opening word of a phrase back toward the silence before it.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from .labels import Label
from .level import FRAME_S
from .lyric import LyricLine
from .phrases import runs

ANCHOR_BEFORE_END_S = 0.05
FIRST_WORD_S = 0.5
LEGATO_SEARCH_S = 0.25
LEGATO_DIP_DB = 3.0
LEGATO_DIP_REACH_S = 0.1
MIN_HELD_S = 0.10


def _frame(seconds: float) -> int:
    return int(round(seconds / FRAME_S))


def anchor(label: Label) -> float:
    """A time safely inside the labelled word: just before its end."""
    return label.end - ANCHOR_BEFORE_END_S


def trusted_start(label: Label) -> float:
    """The start of a word's label, but never more than 0.5 s before its end."""
    return max(label.start, label.end - FIRST_WORD_S)


def nearest_dip(level: np.ndarray, lo: int, hi: int, aim: float) -> int:
    """The local minimum in [lo, hi) closest to frame `target`; the lowest frame if none."""
    reach = _frame(LEGATO_DIP_REACH_S)
    lo, hi = max(lo, 1), min(hi, len(level) - 1)
    if hi <= lo:
        return int(np.clip(round(aim), 0, len(level) - 1))
    dips = []
    for i in range(lo, hi):
        around = level[max(0, i - reach):i + reach + 1]
        if level[i] <= level[i - 1] and level[i] <= level[i + 1] and around.max() - level[i] >= LEGATO_DIP_DB:
            dips.append(i)
    if not dips:
        return lo + int(np.argmin(level[lo:hi]))
    return min(dips, key=lambda i: abs(i - aim))


def _dip_near(level: np.ndarray, seconds: float) -> int:
    reach = _frame(LEGATO_SEARCH_S)
    centre = _frame(seconds)
    return nearest_dip(level, centre - reach, centre + reach + 1, centre)


class _Level:
    """The smoothed level with its held runs (0.10 s and up)."""

    def __init__(self, level: np.ndarray, floor_db: float):
        self.level = level
        self.floor_db = floor_db
        self.held = [(a, b) for a, b in runs(level > floor_db) if b - a >= _frame(MIN_HELD_S)]

    def pause_edges(self, lowest: int) -> tuple[int, int]:
        """(end of voice before `lowest`, start of voice after it)."""
        before = [b for a, b in self.held if b <= lowest]
        after = [a for a, b in self.held if a > lowest]
        return (before[-1] if before else lowest), (after[0] if after else lowest)


def _between(track: _Level, last: Label, first: Label) -> tuple[int, int]:
    """(end of the earlier line, start of the later line) for two labelled neighbours."""
    a, b = sorted((_frame(anchor(last)), _frame(anchor(first))))
    b = max(b, a + 1)
    lowest = a + int(np.argmin(track.level[a:b]))
    if track.level[lowest] < track.floor_db:
        return track.pause_edges(lowest)
    middle = (last.end + max(trusted_start(first), last.end)) / 2.0
    cut = _dip_near(track.level, middle)
    return cut, cut


def label_joins(level: np.ndarray, floor_db: float, lines: Sequence[LyricLine],
                found: Mapping[str, list[int]], labels: Sequence[Label]) -> dict[str, float]:
    """Start (seconds) by the rule above for each line whose line before it also has labels."""
    track = _Level(level, floor_db)
    out = {}
    for before, line in zip(lines[:-1], lines[1:]):
        if before.id in found and line.id in found:
            _, start = _between(track, labels[found[before.id][-1]], labels[found[line.id][0]])
            out[line.id] = round(start * FRAME_S, 3)
    return out
