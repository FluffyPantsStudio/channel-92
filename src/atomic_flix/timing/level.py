"""A stem's level, frame by frame.

The timing stage uses a single yardstick: RMS level in dBFS, frames 10 ms
long. A sine at full scale measures -3.0 dBFS. Discard frames at or under
-60 dBFS; the WORKING_PERCENTILE of what remains is the stem's working level.
Thresholds are set as offsets from it, which makes a quiet mix and a loud
mix answer alike.
"""

from __future__ import annotations

import numpy as np

FRAME_S = 0.01
FLOOR_DB = -120.0
AUDIBLE_DB = -60.0
WORKING_PERCENTILE = 95.0
QUIET_BELOW_WORKING_DB = 18.0


def frame_db(samples: np.ndarray, rate: int, frame_s: float = FRAME_S) -> np.ndarray:
    """RMS level in dBFS of each whole frame of `frame_s` seconds.

    The mean square is taken over every sample of every channel. Folding a
    wide stereo stem to mono first would read it up to 3 dB low, because
    the channels partly cancel.
    """
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim == 1:
        data = data[:, None]
    if data.ndim != 2:
        raise ValueError("audio must be 1-D or (frames, channels)")
    hop = int(round(rate * frame_s))
    count = data.shape[0] // hop
    if count == 0:
        return np.zeros(0)
    chunks = data[: count * hop].reshape(count, hop, data.shape[1])
    power = np.mean(chunks * chunks, axis=(1, 2))
    with np.errstate(divide="ignore"):
        db = 10.0 * np.log10(power)
    return np.maximum(db, FLOOR_DB)


def working_level(db: np.ndarray) -> float:
    """95th percentile of the audible frames; raises when nothing is audible."""
    audible = db[db > AUDIBLE_DB]
    if audible.size == 0:
        raise ValueError("the stem has no frame above -60 dBFS")
    return float(np.percentile(audible, WORKING_PERCENTILE))


def quiet_line(sung_db: float) -> float:
    """Level under which a vocal stem counts as not singing."""
    return sung_db - QUIET_BELOW_WORKING_DB


def running_median(values: np.ndarray, width: int = 5) -> np.ndarray:
    """Median over a centred window of `width` frames, edges padded by repetition."""
    if width < 2 or len(values) == 0:
        return np.asarray(values, dtype=np.float64).copy()
    half = width // 2
    padded = np.pad(np.asarray(values, dtype=np.float64), half, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, width)
    return np.median(windows, axis=1)[: len(values)]
