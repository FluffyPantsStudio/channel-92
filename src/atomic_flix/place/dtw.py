"""Subsequence dynamic time warping: the whole query (rows) against any stretch of the target (columns).

Steps are diagonal (both advance), down (the target holds while the query goes on) and right (the query holds while
the target goes on); a hold costs `hold` on top of the cell. The path may start at any column of the first row and
end at any column of the last. Each row is solved with numpy in one pass: a run of right steps from column k to j
costs the prefix sum of (cell + hold) between them, so the best entry point is a running minimum.
"""

from __future__ import annotations

import numpy as np

_RTOL = 1e-12
_ATOL = 1e-9


def subsequence_path(cost: np.ndarray, hold: float) -> tuple[np.ndarray, float]:
    """The cheapest path through `cost` (rows x columns); returns (pairs of row, column, in order) and its total."""
    rows, cols = cost.shape
    if rows == 0 or cols == 0:
        raise ValueError("an empty cost matrix has no path")
    total = np.empty_like(cost, dtype=np.float64)
    total[0] = cost[0]
    for i in range(1, rows):
        previous = total[i - 1]
        diagonal = np.concatenate([[np.inf], previous[:-1]])
        entry = cost[i] + np.minimum(diagonal, previous + hold)
        stepped = np.cumsum(cost[i] + hold)
        total[i] = stepped + np.minimum.accumulate(entry - stepped)
    end = int(np.argmin(total[-1]))
    return _trace(cost, total, hold, end), float(total[-1, end])


def _trace(cost: np.ndarray, total: np.ndarray, hold: float, end: int) -> np.ndarray:
    """Walk back from the end; the first row is always a fresh start, so the walk stops there."""
    i, j = cost.shape[0] - 1, end
    path = [(i, j)]
    while i > 0:
        here = total[i, j]
        if j > 0 and np.isclose(here, cost[i, j] + total[i - 1, j - 1], rtol=_RTOL, atol=_ATOL):
            i, j = i - 1, j - 1
        elif np.isclose(here, cost[i, j] + hold + total[i - 1, j], rtol=_RTOL, atol=_ATOL):
            i -= 1
        else:
            j -= 1
        path.append((i, j))
    return np.array(path[::-1], dtype=np.int64)
