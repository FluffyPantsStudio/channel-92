"""Synthetic sung sounds for the placing tests: a harmonic stack with a moving formant and syllables.

Every parameter is a function of time, so a sound can be stretched in time without changing its pitch: evaluate the
parameters at t / scale and integrate the pitch for the phase.
"""

from __future__ import annotations

import numpy as np

RATE = 48_000


def _syllable_gain(t: np.ndarray, spans: list[tuple[float, float]], ramp: float = 0.02) -> np.ndarray:
    gain = np.zeros_like(t)
    for start, end in spans:
        rise = np.clip((t - start) / ramp, 0.0, 1.0)
        fall = np.clip((end - t) / ramp, 0.0, 1.0)
        gain = np.maximum(gain, np.minimum(rise, fall))
    return gain


def sung(duration: float, vocal_spans: list[tuple[float, float]], *, rate: int = RATE, scale: float = 1.0,
         voice: int = 0, env_db: float = -14.0) -> np.ndarray:
    """A mono vocal-like sound: syllables of about 0.2 to 0.45 s inside each phrase, with short dips between."""
    rng = np.random.default_rng(100 + voice)
    t = np.arange(int(round(duration * rate))) / rate
    source_t = t / scale
    spans = []
    for start, end in vocal_spans:
        cursor = start
        while cursor < end - 0.1:
            extent = rng.uniform(0.2, 0.45)
            spans.append((cursor, min(end, cursor + extent)))
            cursor += extent + rng.uniform(0.03, 0.07)
    gain = _syllable_gain(source_t, spans)
    base = (170.0, 255.0, 120.0)[voice % 3]
    f0 = base + 35 * np.sin(2 * np.pi * (0.31 + 0.05 * voice) * source_t + voice) \
        + 4 * np.sin(2 * np.pi * 5.1 * source_t)
    # the formant glides between a new vowel target every 0.12 s, so no two frames of a syllable are alike
    knots = np.arange(-0.12, duration / scale + 0.24, 0.12)
    formant = np.interp(source_t, knots, rng.uniform(450, 2400, size=len(knots)))
    phase = 2 * np.pi * np.cumsum(f0) / rate
    out = np.zeros_like(t)
    for harmonic in range(1, 40):
        freq = harmonic * f0
        weight = np.exp(-((freq - formant) / 260.0) ** 2) + 0.35 * np.exp(-((freq - 2.6 * formant) / 400.0) ** 2) \
            + 0.15 / harmonic
        weight = np.where(freq < rate / 2 - 500, weight, 0.0)
        out += weight * np.sin(harmonic * phase)
    out *= gain
    peak = np.sqrt(np.mean(out[gain > 0.5] ** 2)) if np.any(gain > 0.5) else 1.0
    return out / peak * 10 ** (env_db / 20)


def band(duration: float, rate: int = RATE, env_db: float = -14.0) -> np.ndarray:
    """Music without a voice: chords that change every second and a noise hit every half second."""
    rng = np.random.default_rng(7)
    t = np.arange(int(round(duration * rate))) / rate
    roots = np.array([110.0, 146.8, 98.0, 130.8])[(t // 1.0).astype(int) % 4]
    phase = 2 * np.pi * np.cumsum(roots) / rate
    out = sum(np.sin(k * phase * ratio) / k for ratio in (1.0, 1.26, 1.5) for k in range(1, 12))
    hits = np.zeros_like(t)
    for start in np.arange(0.0, duration, 0.5):
        n = (t >= start) & (t < start + 0.12)
        hits[n] = rng.normal(0, 1, n.sum()) * np.exp(-(t[n] - start) / 0.03)
    out = out / np.sqrt(np.mean(out ** 2)) + 0.8 * hits
    return out / np.sqrt(np.mean(out ** 2)) * 10 ** (env_db / 20)


def delayed(x: np.ndarray, seconds: float, rate: int = RATE, trim_db: float = 0.0) -> np.ndarray:
    pad = np.zeros(int(round(seconds * rate)))
    return np.concatenate([pad, x]) * 10 ** (trim_db / 20)


def to_rate(x: np.ndarray, rate_in: int, rate_out: int) -> np.ndarray:
    """Plain linear interpolation; good enough to hand a test a second sample rate."""
    n_made = int(round(len(x) * rate_out / rate_in))
    return np.interp(np.arange(n_made) * rate_in / rate_out, np.arange(len(x)), x)
