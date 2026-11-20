"""A counting click on the beats, to confirm by ear where the bar's one is.

With phase P the bar's one is every beat whose index mod 4 is P. Each count has its own pitch: the one is loud and
high, then two, three and four rise softly back toward it, so a listener can count "ONE two three four" along with
the song. `tools/click.py` writes it as a WAV; the gate-2 packet lays it over the mix (`atomic_flix.desk`).
"""

from __future__ import annotations

import numpy as np

RATE = 44100
COUNT_HZ = (1760.0, 660.0, 784.0, 988.0)   # one, two, three, four
LOUD = 0.8
SOFT = 0.25
CLICK_S = 0.06
DECAY_S = 0.015
ATTACK_S = 0.001
TAIL_S = 1.0
PEAK_LIMIT = 0.99


def _blip(freq: float, level: float, rate: int) -> np.ndarray:
    t = np.arange(int(CLICK_S * rate)) / rate
    env = np.clip(t / ATTACK_S, 0.0, 1.0) * np.exp(-t / DECAY_S)
    return level * env * np.sin(2 * np.pi * freq * t)


def render_clicks(beats, phase: int, rate: int = RATE, extent: int | None = None) -> np.ndarray:
    """Mono float clicks: loud high blip on each one, softer pitched blips on the other counts."""
    if phase not in (0, 1, 2, 3):
        raise ValueError(f"phase must be 0 to 3, got {phase}")
    times = np.asarray(beats, dtype=float)
    if times.ndim != 1 or len(times) == 0:
        raise ValueError("beats must be a non-empty list of numbers")
    if np.any(times < 0) or np.any(np.diff(times) <= 0):
        raise ValueError("beats must be non-negative and strictly increasing")
    n = extent if extent is not None else int(round((times[-1] + TAIL_S) * rate))
    out = np.zeros(n)
    blips = [_blip(COUNT_HZ[c], LOUD if c == 0 else SOFT, rate) for c in range(4)]
    for i, t in enumerate(times):
        blip = blips[(i - phase) % 4]
        start = int(round(t * rate))
        if start >= n:
            break
        end = min(n, start + len(blip))
        out[start:end] += blip[: end - start]
    return out


def to_rate(music: np.ndarray, rate: int, aim: int) -> np.ndarray:
    """Mono MUSIC at RATE resampled to AIM by linear interpolation."""
    if rate == aim:
        return music
    n_made = int(round(len(music) * aim / rate))
    src_t = np.arange(len(music)) / rate
    return np.interp(np.arange(n_made) / aim, src_t, music)


def mix_over(clicks: np.ndarray, music: np.ndarray, music_gain_db: float) -> np.ndarray:
    """Lay clicks over mono music at a gain; the whole mix is scaled down if it would clip."""
    n = max(len(clicks), len(music))
    mixed = np.zeros(n)
    mixed[: len(music)] += music * 10 ** (music_gain_db / 20)
    mixed[: len(clicks)] += clicks
    peak = float(np.max(np.abs(mixed))) if n else 0.0
    if peak > PEAK_LIMIT:
        mixed *= PEAK_LIMIT / peak
    return mixed
