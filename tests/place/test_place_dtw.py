"""The row-at-a-time subsequence DTW against a plain cell-by-cell version."""

from __future__ import annotations

import numpy as np
import pytest

from atomic_flix.place.dtw import subsequence_path


def _slow(cost: np.ndarray, hold: float) -> float:
    rows, cols = cost.shape
    total = np.full((rows, cols), np.inf)
    total[0] = cost[0]
    for i in range(1, rows):
        for j in range(cols):
            best = total[i - 1, j] + hold
            if j > 0:
                best = min(best, total[i - 1, j - 1], total[i, j - 1] + hold)
            total[i, j] = cost[i, j] + best
    return float(total[-1].min())


@pytest.mark.parametrize("seed", range(6))
def test_totals_match_the_plain_version_and_the_path_adds_up(seed):
    rng = np.random.default_rng(seed)
    cost = rng.uniform(0, 1, size=(rng.integers(2, 12), rng.integers(2, 15)))
    path, total = subsequence_path(cost, 0.06)
    assert total == pytest.approx(_slow(cost, 0.06))
    rows, cols = path[:, 0], path[:, 1]
    assert rows[0] == 0 and rows[-1] == cost.shape[0] - 1
    steps = np.diff(path, axis=0)
    assert all(tuple(step) in {(1, 1), (1, 0), (0, 1)} for step in steps)
    holds = sum(1 for step in steps if tuple(step) != (1, 1))
    assert cost[rows, cols].sum() + 0.06 * holds == pytest.approx(total)


def test_a_query_inside_the_target_is_found_on_the_diagonal():
    aim = np.linspace(0, 1, 40)
    query = aim[10:25]
    cost = np.abs(query[:, None] - aim[None, :])
    path, total = subsequence_path(cost, 0.06)
    assert total == pytest.approx(0.0)
    assert list(path[:, 1]) == list(range(10, 25))
