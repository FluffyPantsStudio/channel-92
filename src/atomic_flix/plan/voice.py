"""What a vocal render hears: its slice of the voice stem, gated to its own lines, and a soft copy of that.

The soft copy is what goes to the render: compressed (threshold -30 dB, ratio 6, attack 5 ms, release 120 ms) and
8 dB down. On the full vocal a long loud vowel opened into a laugh in every render of one shot of our first film; on
the soft copy none did, and placing by sound still worked. The render's own sound is thrown away.
"""

from __future__ import annotations

import numpy as np

OUT_RATE = 48000
FADE = 0.02
EDGE = 0.04
THRESHOLD_DB, RATIO, ATTACK, RELEASE, DOWN_DB = -30.0, 6.0, 0.005, 0.120, -8.0
BLOCK = 0.001


def _stereo(samples: np.ndarray) -> np.ndarray:
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim == 1:
        data = data[:, None]
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    return data[:, :2]


def _resample_window(data: np.ndarray, rate: int, slice_start: float, seconds: int) -> np.ndarray:
    count = int(seconds * OUT_RATE)
    times = slice_start + np.arange(count) / OUT_RATE
    provenance = np.arange(data.shape[0]) / rate
    out = np.zeros((count, data.shape[1]))
    for channel in range(data.shape[1]):
        out[:, channel] = np.interp(times, provenance, data[:, channel], left=0.0, right=0.0)
    return out


def gate_mask(count: int, rate: int, start: float, end: float) -> np.ndarray:
    """1 inside [start, end) (slice seconds), 0 outside, with raised-cosine fades just inside each edge."""
    times = np.arange(count) / rate
    mask = ((times >= start) & (times < end)).astype(np.float64)
    fade_in = (times >= start) & (times < start + FADE)
    fade_out = (times < end) & (times >= end - FADE)
    mask[fade_in] *= 0.5 - 0.5 * np.cos(np.pi * (times[fade_in] - start) / FADE)
    mask[fade_out] *= 0.5 - 0.5 * np.cos(np.pi * (end - times[fade_out]) / FADE)
    return mask


def gated_voice(samples: np.ndarray, rate: int, slice_start: float, seconds: int,
                gate: tuple[float, float]) -> np.ndarray:
    """Exactly `seconds` of 48 kHz stereo from `slice_start`, silent outside the gate (song seconds)."""
    taper = _resample_window(_stereo(samples), rate, slice_start, seconds)
    mask = gate_mask(taper.shape[0], OUT_RATE, gate[0] - slice_start, gate[1] - slice_start)
    return taper * mask[:, None]


def soft_copy(samples: np.ndarray, rate: int) -> np.ndarray:
    """Compressed and turned down; a quiet voice comes out 8 dB lower, a loud one much lower."""
    data = _stereo(samples)
    block = max(1, int(rate * BLOCK))
    chunks = int(np.ceil(data.shape[0] / block))
    padded = np.zeros((chunks * block, data.shape[1]))
    padded[: data.shape[0]] = data
    power = np.mean(np.square(padded).reshape(chunks, block, -1), axis=(1, 2))
    rise, fall = np.exp(-BLOCK / ATTACK), np.exp(-BLOCK / RELEASE)
    envelope = np.empty(chunks)
    level = 0.0
    for index, value in enumerate(power):
        coef = rise if value > level else fall
        level = coef * level + (1 - coef) * value
        envelope[index] = level
    env_db = 10 * np.log10(envelope + 1e-20)
    over = np.maximum(env_db - THRESHOLD_DB, 0.0)
    trim_db = -over * (1 - 1 / RATIO) + DOWN_DB
    gain = np.repeat(10 ** (trim_db / 20), block)[: data.shape[0]]
    return data * gain[:, None]


def edge_levels(samples: np.ndarray, rate: int, gate: tuple[float, float]) -> list[float]:
    """RMS dBFS of the 40 ms just outside each gate edge in the raw stem: sound there means the gate clips a word."""
    data = _stereo(samples)
    out = []
    for start, end in ((gate[0] - EDGE, gate[0]), (gate[1], gate[1] + EDGE)):
        a, b = max(0, int(start * rate)), max(0, int(end * rate))
        chunk = data[a:b]
        power = float(np.mean(np.square(chunk))) if chunk.size else 0.0
        out.append(round(10 * np.log10(power + 1e-20), 1))
    return out
