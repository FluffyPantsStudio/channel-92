"""Where a time falls in the bar: the count (1 to 4) of the nearest beat, from a beat list and the index of a one."""

from __future__ import annotations

from typing import Sequence

import numpy as np

BEATS_PER_BAR = 4
ON_BEAT_SECONDS = 0.03


def beat_count(at: float, beats: Sequence[float], downbeat_slot: int,
               tolerance: float = ON_BEAT_SECONDS) -> tuple[int | None, float]:
    """(count, seconds from the nearest beat). The count is None when no beat lies within `tolerance`."""
    grid = np.asarray(beats, dtype=float)
    if grid.size == 0:
        return None, float("nan")
    index = int(np.argmin(np.abs(grid - at)))
    offset = float(at - grid[index])
    if abs(offset) > tolerance:
        return None, offset
    return (index - int(downbeat_slot)) % BEATS_PER_BAR + 1, offset
