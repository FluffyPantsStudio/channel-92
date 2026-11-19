"""Lyric lines to pieces of singing, chosen for the whole song at once.

Why global: the old way dealt phrases to lines run by run, and on the first
film one legato join it missed early in the song (a wordless intro line run
into "She slipped out the back") shifted every later line by one. Here one
dynamic programme over every line and every piece (`units.find_units`)
chooses where each line starts and ends, so an error costs what it costs
where it happens and has no reason to travel.

Each lead line takes a run of neighbouring pieces, or none (reported
unplaced). Pieces may be left over (ad libs, breaths, other sounds). The cost
of a choice is the sum of:

* length: squared log ratio of the line's voiced seconds to what it should
  take (syllables at the song's pace; vocalises count double and weigh
  less; after the first pass, a line whose text is sung more than once also
  leans towards the length its copies took);
* silence spanned inside the line;
* the join it starts on (`units`: nothing after a pause, more at a shallow
  dip, most at a grid cut with no evidence), paid once per join;
* a pause longer than 3 s between two lines of one section (long gaps sit
  between sections: an instrumental break belongs between verse and chorus);
* labels, when given: a line should start before its first heard word ends
  and no more than 0.6 s before that word's trusted start (its label start,
  but never more than 0.5 s before the label's end, because a recogniser
  can pull a post-silence opening word up to 2 s early), and end no earlier than 0.3 s
  before its last heard word ends; each second outside costs 10. Where the
  labels put the join between two labelled lines (spec step 4) is offered as
  a cut of its own;
* left-over pieces: their voiced seconds, scaled down when they are quiet;
* an unplaced line: a fixed 3.

Confidence: with the forward and backward passes, the cheapest whole-song
choice is known for every possible start of every line. A line's margin is
how much more the best choice costs if the line starts more than 0.25 s away
from where it was put (or is left unplaced). Confidence is
1 - exp(-margin), and a line under 0.5 is flagged uncertain with that
alternative named.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .bounds import trusted_start
from .labels import Label
from .units import Unit

UNPLACED_COST = 3.0
LENGTH_WEIGHT = 1.0
SKIP_WEIGHT = 1.5
GAP_WEIGHT = 1.0
LINE_GAP_FREE_S = 3.0
LINE_GAP_WEIGHT = 0.3
MAX_UNITS_PER_LINE = 64
MAX_LINE_SPAN_S = 16.0
LABEL_WEIGHT = 10.0
LABEL_EARLY_OK_S = 0.6
LABEL_INSIDE_S = 0.05
LABEL_END_SLACK_S = 0.3
LABELLED_GRID_COST = 1.0
ALTERNATIVE_APART_S = 0.25
MIN_VOICED_S = 0.05


@dataclass(frozen=True)
class LineCue:
    """What one lead line should look like: its length and, when heard, its words."""

    expected_s: float
    weight: float
    joins_previous: bool
    first_label: Label | None = None
    last_label: Label | None = None


@dataclass(frozen=True)
class Placement:
    """Pieces [first, stop) for one line (None: unplaced), and how sure the choice is."""

    first: int | None
    stop: int | None
    clearance: float
    alternative: float | None

    @property
    def confidence(self) -> float:
        return float(1.0 - np.exp(-max(0.0, self.clearance)))


class _Song:
    """The pieces as arrays, and the costs of moving from one line to the next."""

    def __init__(self, units: Sequence[Unit], sung_db: float):
        m = len(units)
        self.m = m
        self.starts = np.array([u.start for u in units])
        self.finishes = np.array([u.end for u in units])
        self.cut_cost = np.array([u.cut_cost for u in units])
        self.is_grid = np.array([u.cut == "grid" for u in units])
        contiguous = np.array([u.cut != "pause" for u in units] + [False])
        self.end_cut = np.where(contiguous[1:], np.append(self.cut_cost[1:], 0.0), 0.0)
        self.cum_voiced = np.concatenate([[0.0], np.cumsum([u.vocal_on for u in units])])
        self.cum_pause = np.concatenate([[0.0], np.cumsum([u.pause_before for u in units])])
        loud = np.array([min(1.0, 10 ** ((u.peak_db - sung_db) / 20.0)) for u in units])
        skip = SKIP_WEIGHT * np.array([u.vocal_on for u in units]) * loud
        self.cum_skip = np.concatenate([[0.0], np.cumsum(skip)])
        x = np.arange(m + 1)[:, None]
        s = np.arange(m)[None, :]
        self.base = np.where(s >= x, self.cum_skip[s] - self.cum_skip[x], np.inf)
        refund = np.zeros((m + 1, m))
        refund[np.arange(1, m + 1)[:-1], np.arange(1, m)] = self.end_cut[:-1]
        self.base = self.base - refund
        prev_end = np.concatenate([[np.inf], self.finishes])[:, None]
        gap = np.where(x >= 1, np.maximum(0.0, self.starts[s] - prev_end - LINE_GAP_FREE_S), 0.0)
        self.gap = np.where(s >= x, LINE_GAP_WEIGHT * np.nan_to_num(gap, posinf=0.0), 0.0)
        self.width = max(1, min(MAX_UNITS_PER_LINE, m))
        d = np.arange(self.width)[None, :]
        self.span_end = np.arange(m)[:, None] + d
        finishes = np.arange(m + 1)[:, None]
        self.start_of = finishes - 1 - d

    def entry(self, before: np.ndarray, cue: LineCue) -> np.ndarray:
        """(m+1, m): cost of going from state x (pieces used so far) to a line starting on piece s."""
        table = before[:, None] + self.base
        return table + self.gap if cue.joins_previous else table

    def by_end(self, table: np.ndarray) -> np.ndarray:
        """(m+1, width): table[s, d] re-indexed by the state after the line, s + d + 1."""
        ok = self.start_of >= 0
        return np.where(ok, table[np.clip(self.start_of, 0, None), np.arange(self.width)[None, :]], np.inf)

    def after(self, state_cost: np.ndarray) -> np.ndarray:
        """(m, width): state_cost at s + d + 1, the state a line on pieces s..s+d leaves."""
        t = self.span_end + 1
        return np.where(t <= self.m, state_cost[np.clip(t, 0, self.m)], np.inf)


def _label_cost(cue: LineCue, starts: np.ndarray, finishes: np.ndarray) -> np.ndarray:
    cost = np.zeros_like(starts)
    if cue.first_label is not None:
        first = cue.first_label
        cost += np.maximum(0.0, trusted_start(first) - LABEL_EARLY_OK_S - starts)
        cost += np.maximum(0.0, starts - (first.end - LABEL_INSIDE_S))
    if cue.last_label is not None:
        cost += np.maximum(0.0, cue.last_label.end - LABEL_END_SLACK_S - finishes)
    cost = LABEL_WEIGHT * cost
    return cost


def _start_cost(song: _Song, cue: LineCue) -> np.ndarray:
    """What starting on each piece costs this line; heard words make a split inside a held run cheaper."""
    if cue.first_label is None:
        return song.cut_cost
    return np.where(song.is_grid, np.minimum(song.cut_cost, LABELLED_GRID_COST), song.cut_cost)


def span_costs(song: _Song, cue: LineCue) -> np.ndarray:
    """(m, width): the cost of the line taking pieces s .. s + d; inf where not allowed."""
    s = np.arange(song.m)[:, None]
    t = song.span_end
    tc = np.clip(t, 0, song.m - 1)
    starts, finishes = song.starts[s] * np.ones_like(tc), song.finishes[tc]
    ok = (t < song.m) & (finishes - starts <= MAX_LINE_SPAN_S)
    vocal_on = song.cum_voiced[tc + 1] - song.cum_voiced[s]
    silence = song.cum_pause[tc + 1] - song.cum_pause[s + 1]
    extent = LENGTH_WEIGHT * cue.weight * np.log(np.maximum(vocal_on, MIN_VOICED_S) / cue.expected_s) ** 2
    cost = (extent + GAP_WEIGHT * silence + _start_cost(song, cue)[s] + song.end_cut[tc]
            + _label_cost(cue, starts, finishes))
    return np.where(ok, cost, np.inf)


def _forward(song: _Song, cues: Sequence[LineCue], costs: Sequence[np.ndarray]):
    states = [np.full(song.m + 1, np.inf)]
    states[0][0] = 0.0
    logged, starts_from, widths, placed = [], [], [], []
    for cue, cost in zip(cues, costs):
        table = song.entry(states[-1], cue)
        entry = table.min(axis=0)
        reached = song.by_end(entry[:, None] + cost)
        here = reached.min(axis=1)
        left_out = states[-1] + UNPLACED_COST
        logged.append(entry)
        starts_from.append(table.argmin(axis=0))
        widths.append(reached.argmin(axis=1))
        placed.append(here < left_out)
        states.append(np.minimum(here, left_out))
    return states, logged, starts_from, widths, placed


def _backward(song: _Song, cues: Sequence[LineCue], costs: Sequence[np.ndarray]) -> list[np.ndarray]:
    """rest[k][x]: the cheapest cost of lines after k (and trailing pieces) from state x."""
    n = len(cues)
    rest = [np.empty(0)] * n
    rest[n - 1] = song.cum_skip[song.m] - song.cum_skip
    for k in range(n - 1, 0, -1):
        onward = (costs[k] + song.after(rest[k])).min(axis=1)
        table = song.base + (song.gap if cues[k].joins_previous else 0.0) + onward[None, :]
        rest[k - 1] = np.minimum(rest[k] + UNPLACED_COST, table.min(axis=1))
    return rest


def _trace(song, states, starts_from, widths, placed) -> list[tuple[int, int] | None]:
    n = len(placed)
    trailing = song.cum_skip[song.m] - song.cum_skip
    x = int(np.argmin(states[n] + trailing))
    out: list[tuple[int, int] | None] = [None] * n
    for k in range(n - 1, -1, -1):
        if not placed[k][x]:
            continue
        first = x - 1 - int(widths[k][x])
        out[k] = (first, x)
        x = int(starts_from[k][first])
    return out


def _margins(song, states, logged, rest, costs, picked) -> list[tuple[float, float | None]]:
    out = []
    for k, cost in enumerate(costs):
        by_start = (logged[k][:, None] + cost + song.after(rest[k])).min(axis=1)
        unplaced = float((states[k] + UNPLACED_COST + rest[k]).min())
        if picked[k] is None:
            best_other = float(by_start.min()) if np.isfinite(by_start).any() else np.inf
            here = unplaced
            other_at = float(song.starts[int(np.argmin(by_start))]) if np.isfinite(best_other) else None
        else:
            here = float(by_start[picked[k][0]])
            far = np.abs(song.starts - song.starts[picked[k][0]]) > ALTERNATIVE_APART_S
            masked = np.where(far, by_start, np.inf)
            best_far = float(masked.min()) if far.any() else np.inf
            if best_far <= unplaced:
                best_other, other_at = best_far, float(song.starts[int(np.argmin(masked))])
            else:
                best_other, other_at = unplaced, None
        out.append((best_other - here, other_at))
    return out


def align(units: Sequence[Unit], cues: Sequence[LineCue], sung_db: float) -> list[Placement]:
    """Place every line on the pieces in one global choice; see the module text for the costs."""
    if not cues:
        return []
    if not units:
        return [Placement(None, None, np.inf, None) for _ in cues]
    song = _Song(units, sung_db)
    costs = [span_costs(song, cue) for cue in cues]
    states, logged, starts_from, widths, placed = _forward(song, cues, costs)
    picked = _trace(song, states, starts_from, widths, placed)
    rest = _backward(song, cues, costs)
    margins = _margins(song, states, logged, rest, costs, picked)
    return [Placement(c[0] if c else None, c[1] if c else None, float(mg), alt)
            for c, (mg, alt) in zip(picked, margins)]
