"""How fast a placed take plays, judged against how precisely it was placed.

A placement map is a list of (song time, take time) points written every 0.1 s by placing by sound. Each point is
only as exact as the placing (the fit stage is held to 0.02 s), so the slope between two neighbouring points can read
anywhere from 0.6x to 1.4x on a take that plays at exactly 1x: on the first film, 19 of 25 sung takes read 0.87 to
0.99 that way while their whole-shot slopes were 0.997 to 1.000.

So the rate is measured over stretches of the shown shot: every 1 s, 2 s and 4 s window (step 0.05 s) that fits, and
the whole shot. Over a window of L seconds two points each off by U move the slope by at most 2U / L, which is the
tolerance: a window slower than 1 - 2U / L is a take truly played slower than 1x and is refused. A short window can
catch a strong local slowdown, a long one a mild slowdown that lasts.

The tolerance is capped at 3 %: however short the window (a 1 s window would otherwise allow 4 %, a 0.5 s shot 8 %),
a reading under 0.97x is refused. Placement noise is never a licence to show a take slowed by more than that.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .edit import Placed

PLACEMENT_UNCERTAINTY_S = 0.02
RATE_WINDOWS_S = (1.0, 2.0, 4.0)
WINDOW_STEP_S = 0.05
MOST_SLOWDOWN_LET_THROUGH = 0.03


def slow_tolerance(window_s: float) -> float:
    """How far under 1x a rate measured over `window_s` seconds may read on a take that runs at 1x: the placement's
    own uncertainty over that window, never more than 3 %."""
    if window_s <= 0:
        return MOST_SLOWDOWN_LET_THROUGH
    return min(2 * PLACEMENT_UNCERTAINTY_S / window_s, MOST_SLOWDOWN_LET_THROUGH)


@dataclass(frozen=True)
class RateReading:
    slowest: float            # slowest rate over any measured window
    fastest: float
    slowest_window: float     # its window length, seconds
    slower: bool              # a window under 1 - slow_tolerance(its length)
    worst_margin: float       # most negative (rate - (1 - tolerance)) over the windows; under 0 means slower

    def tolerance(self) -> float:
        return slow_tolerance(self.slowest_window)


def _starts(start: float, end: float, extent: float) -> np.ndarray:
    last = end - extent
    starts = np.arange(start, last + 1e-9, WINDOW_STEP_S)
    if len(starts) == 0 or starts[-1] < last - 1e-9:
        starts = np.append(starts, last)
    return starts


def read_rates(placed: Placed, start: float, end: float) -> RateReading:
    """Rates of `placed` over the windows of [start, end] (song seconds)."""
    span = end - start
    if span <= 0:
        return RateReading(1.0, 1.0, 0.0, False, 0.0)
    lengths = sorted({extent for extent in RATE_WINDOWS_S if extent < span - 1e-9} | {span})
    slowest = (np.inf, span)
    fastest = -np.inf
    worst = np.inf
    for extent in lengths:
        for at in _starts(start, end, extent):
            rate = (placed.take_time(at + extent) - placed.take_time(at)) / extent
            if rate < slowest[0]:
                slowest = (rate, extent)
            fastest = max(fastest, rate)
            worst = min(worst, rate - (1.0 - slow_tolerance(extent)))
    return RateReading(slowest=float(slowest[0]), fastest=float(fastest), slowest_window=float(slowest[1]),
                       slower=bool(worst < 0), worst_margin=float(worst))
