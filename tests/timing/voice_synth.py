"""Synthetic voice stems for the timing tests.

A "sung" burst is a buzzy tone with a slow wobble in level, so it has the
shape of a held vowel without being a flat sine. Levels are given as the
burst's RMS in dBFS.
"""

from __future__ import annotations

import numpy as np

RATE = 16000


def tone(seconds: float, rms_db: float, pitch: float = 220.0, rate: int = RATE) -> np.ndarray:
    t = np.arange(int(round(seconds * rate))) / rate
    wave = sum(np.sin(2 * np.pi * pitch * k * t) / k for k in range(1, 6))
    wave = wave * (1.0 + 0.15 * np.sin(2 * np.pi * 4.0 * t))
    rms = np.sqrt(np.mean(wave ** 2)) + 1e-12
    return wave * (10 ** (rms_db / 20.0) / rms)


def voice(total: float, bursts, rate: int = RATE) -> np.ndarray:
    """Silence of `total` seconds with bursts placed as (start, end, rms_db)."""
    out = np.zeros(int(round(total * rate)))
    for start, end, level in bursts:
        piece = tone(end - start, level, rate=rate)
        a = int(round(start * rate))
        out[a:a + len(piece)] += piece[: len(out) - a]
    return out
