"""Hand sung phrases to lyric lines, keeping both in song order; the cheapest hand-out is found exactly.

Only the choir uses this, and only inside one stretch bounded by the lead
lines either side, so a mistake cannot leak past that stretch. The lead is
handled by the song-wide search in `align`.

A line owns a contiguous group of phrases, or nothing, in which case it is
reported as unplaced. Some phrases may belong to no line (stray stem sounds,
ad libs, breaths). Price of a line: the squared log ratio between its voiced
seconds and its syllable count times the pace (wordless vowels are treated
as long held notes and carry less weight), plus any silence between its
phrases. Price of an unused phrase: its voiced seconds, discounted when it
is quiet, so faint strays are cheap to drop.

Pace (seconds per syllable) starts as a guess; after one hand-out it is
re-measured from the result and the hand-out is repeated.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from .lyric import LyricLine
from .phrases import Phrase

PACE_WEIGHT = 1.0
WORDLESS_PACE_WEIGHT = 0.3
WORDLESS_STRETCH = 2.0
GAP_WEIGHT = 1.0
SKIP_WEIGHT = 1.5
UNPLACED_COST = 3.0
MAX_PHRASES_PER_LINE = 10
MAX_LINE_SPAN_S = 16.0
FIRST_PACE_S = 0.32
PACE_LIMITS_S = (0.12, 1.0)
PACE_ROUNDS = 3


def _expected(lines: Sequence[LyricLine]) -> tuple[np.ndarray, np.ndarray]:
    """Syllables scaled for held vocalises, and each line's weight on pace."""
    sylls = np.array([ln.syllables for ln in lines], dtype=np.float64)
    stretch = np.array([WORDLESS_STRETCH if ln.wordless else 1.0 for ln in lines])
    weight = np.array([WORDLESS_PACE_WEIGHT if ln.wordless else PACE_WEIGHT for ln in lines])
    return sylls * stretch, weight


def _span_costs(vocal_spans: Sequence[Phrase], lines: Sequence[LyricLine], pace: float) -> np.ndarray:
    """cost[j, s, k]: line k taking phrases j .. j+s (inclusive); inf where not allowed."""
    m, n = len(vocal_spans), len(lines)
    beats, weight = _expected(lines)
    cost = np.full((m, MAX_PHRASES_PER_LINE, n), np.inf)
    for j in range(m):
        vocal_on, silence = 0.0, 0.0
        for s in range(MAX_PHRASES_PER_LINE):
            e = j + s
            if e >= m or vocal_spans[e].end - vocal_spans[j].start > MAX_LINE_SPAN_S:
                break
            vocal_on += vocal_spans[e].vocal_on
            if s:
                silence += max(0.0, vocal_spans[e].start - vocal_spans[e - 1].end)
            ratio = np.log(max(vocal_on, 0.05) / (beats * pace))
            cost[j, s] = weight * ratio ** 2 + GAP_WEIGHT * silence
    return cost


def _skip_costs(vocal_spans: Sequence[Phrase], sung_db: float) -> np.ndarray:
    loudness = np.array([min(1.0, 10 ** ((ph.peak_db - sung_db) / 20.0)) for ph in vocal_spans])
    return SKIP_WEIGHT * np.array([ph.vocal_on for ph in vocal_spans]) * loudness


def _deal(vocal_spans, lines, pace, sung_db) -> list[tuple[int, int] | None]:
    m, n = len(vocal_spans), len(lines)
    cost = _span_costs(vocal_spans, lines, pace)
    skip = _skip_costs(vocal_spans, sung_db)
    best = np.full((n + 1, m + 1), np.inf)
    best[0, 0] = 0.0
    back: dict[tuple[int, int], tuple[int, int, int]] = {}

    def offer(state, value, came_from):
        if value < best[state]:
            best[state] = value
            back[state] = came_from

    for k in range(n + 1):
        for j in range(m + 1):
            here = best[k, j]
            if not np.isfinite(here):
                continue
            if j < m:
                offer((k, j + 1), here + skip[j], (k, j, -1))
            if k == n:
                continue
            offer((k + 1, j), here + UNPLACED_COST, (k, j, -2))
            for s in range(MAX_PHRASES_PER_LINE if j < m else 0):
                if not np.isfinite(cost[j, s, k]):
                    break
                offer((k + 1, j + s + 1), here + cost[j, s, k], (k, j, s))
    dealt: list[tuple[int, int] | None] = [None] * n
    state = (n, m)
    while state != (0, 0):
        k, j, how = back[state]
        if how >= 0:
            dealt[k] = (j, j + how + 1)
        state = (k, j)
    return dealt


def _measured_pace(vocal_spans, lines, dealt) -> float | None:
    beats, _ = _expected(lines)
    paces = [sum(ph.vocal_on for ph in vocal_spans[got[0]:got[1]]) / beats[k]
             for k, got in enumerate(dealt) if got is not None and not lines[k].wordless]
    if not paces:
        return None
    return float(np.clip(np.median(paces), *PACE_LIMITS_S))


def deal_vocal_spans(vocal_spans: Sequence[Phrase], lines: Sequence[LyricLine], sung_db: float,
                 pace: float | None = None) -> list[tuple[int, int] | None]:
    """For each line, the [first, stop) range of phrase indices it takes, or None.

    Give `pace` (seconds per syllable) to use a known pace instead of
    measuring one from these phrases.
    """
    if not lines:
        return []
    if not vocal_spans:
        return [None] * len(lines)
    if pace is not None:
        return _deal(vocal_spans, lines, pace, sung_db)
    pace = FIRST_PACE_S
    dealt = _deal(vocal_spans, lines, pace, sung_db)
    for _ in range(PACE_ROUNDS - 1):
        measured = _measured_pace(vocal_spans, lines, dealt)
        if measured is None or abs(measured - pace) < 0.01:
            break
        pace = measured
        dealt = _deal(vocal_spans, lines, pace, sung_db)
    return dealt
