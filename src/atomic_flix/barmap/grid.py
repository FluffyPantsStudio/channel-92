"""The beat grid: every beat of a song whose tempo may drift.

1. Onset strength: broadband spectral flux less its local average.
2. Song tempo: autocorrelation of the onset strength over the first 90 s,
   leaning toward 120 BPM so a half or double tempo does not win by accident
   (a hint replaces the lean).
3. Local fits: every 5 s, a 20 s window fits its own beat period (within 4 %
   of the song tempo) and phase. The weakest fifth of the windows are dropped
   and the rest are smoothed into a tempo curve.
4. Path: the beat sequence that best trades landing on strong onsets against
   keeping the local period of the tempo curve, found by dynamic programming
   over the whole song at once. (A step-by-step walk from one window loses
   the beat for good after a single wrong snap in a busy mix; the whole-song
   path cannot.)
5. Snap: each beat moves onto the strongest onset within 30 ms, sharpened to
   the steepest rise of the waveform's energy. Beats at either end that sit
   in silence are dropped.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .spectral import Spectra

TEMPO_SPAN_S = 90.0
BPM_RANGE = (60.0, 200.0)
LEAN_BPM = 120.0
LEAN_OCTAVES = 0.6
HINT_SPREAD = 0.04
WINDOW_S = 20.0
WINDOW_EVERY_S = 5.0
PERIOD_STEPS = 33
DROP_WEAKEST = 0.2
SNAP_S = 0.030
SNAP_FLOOR = 0.15
LOCAL_MEAN_S = 0.4
LOCAL_MAX_S = 2.0
REFINE_BEFORE_S = 0.015
REFINE_AFTER_S = 0.035
REFINE_WINDOW_S = 0.005
REFINE_HOP_S = 0.001
REFINE_MIN_RISE = 4.0
REFINE_FLOOR_FRAMES = 5
REFINE_FRACTION = 0.1
SILENT_RATIO = 0.01
TIGHTNESS = 100.0
STEP_RANGE = (0.5, 2.0)


@dataclass(frozen=True)
class Grid:
    """Beat times, which of them sit on an onset, and the tempo curve behind them."""

    beats: np.ndarray
    on_onset: np.ndarray
    bpm: float
    curve_times: np.ndarray
    tempo_bpm: np.ndarray


def _moving_mean(x: np.ndarray, width: int) -> np.ndarray:
    width = max(1, width)
    kernel = np.ones(width) / width
    return np.convolve(x, kernel, mode="same")


def onset_strength(spectra: Spectra) -> np.ndarray:
    """Spectral flux above its local average, scaled to a 99th percentile of 1."""
    flux = spectra.onset
    env = np.maximum(flux - _moving_mean(flux, int(LOCAL_MEAN_S / spectra.step)), 0.0)
    scale = np.percentile(env, 99) if env.size else 1.0
    return env / scale if scale > 0 else env


def global_tempo(spectra: Spectra, hint_bpm: float | None = None) -> float:
    """Song tempo in BPM from the first 90 s."""
    env = onset_strength(spectra)[: int(TEMPO_SPAN_S / spectra.step)]
    env = env - env.mean()
    size = 1 << int(np.ceil(np.log2(2 * len(env))))
    spectrum = np.fft.rfft(env, size)
    corr = np.fft.irfft(spectrum * np.conj(spectrum), size)[: len(env)]
    lags = np.arange(1, len(corr))
    bpm = 60.0 / (lags * spectra.step)
    if hint_bpm:
        allowed = np.abs(bpm / hint_bpm - 1.0) <= HINT_SPREAD
        lean = np.ones_like(bpm)
    else:
        allowed = (bpm >= BPM_RANGE[0]) & (bpm <= BPM_RANGE[1])
        lean = np.exp(-0.5 * (np.log2(bpm / LEAN_BPM) / LEAN_OCTAVES) ** 2)
    score = np.where(allowed, corr[1:] * lean, -np.inf)
    best = int(np.argmax(score))
    lag = float(lags[best])
    if 0 < best < len(score) - 1 and np.isfinite(score[best - 1]) and np.isfinite(score[best + 1]):
        a, b, c = score[best - 1], score[best], score[best + 1]
        denom = a - 2 * b + c
        if denom < 0:
            lag += 0.5 * (a - c) / denom
    return 60.0 / (lag * spectra.step)


def _fit_window(env: np.ndarray, step: float, start: float, period: float) -> tuple[float, float, float]:
    """(period, time of one beat, mean onset strength on the comb) for one window."""
    end = start + WINDOW_S
    best = (period, start, -np.inf)
    frame_times = np.arange(len(env)) * step
    for p in period * (1.0 + np.linspace(-HINT_SPREAD, HINT_SPREAD, PERIOD_STEPS)):
        phases = np.arange(0.0, p, step)
        count = max(1, int((end - start) / p))
        grid = start + phases[:, None] + p * np.arange(count)[None, :]
        values = np.interp(grid.ravel(), frame_times, env, left=0.0, right=0.0).reshape(grid.shape)
        means = values.mean(axis=1)
        k = int(np.argmax(means))
        if means[k] > best[2]:
            best = (float(p), float(start + phases[k]), float(means[k]))
    return best


@dataclass(frozen=True)
class _Fit:
    centre: float
    period: float
    phase: float
    punch: float


def _window_fits(env: np.ndarray, spectra: Spectra, period: float) -> list[_Fit]:
    """Local fits, weakest fifth dropped, periods smoothed over neighbouring windows."""
    span = min(WINDOW_S, spectra.duration)
    starts = np.arange(0.0, max(spectra.duration - WINDOW_S, 0.0) + 1e-9, WINDOW_EVERY_S)
    raw = [(s + span / 2.0, *_fit_window(env, spectra.step, s, period)) for s in starts]
    strengths = np.array([r[3] for r in raw])
    if len(raw) >= 5:
        raw = [r for r in raw if r[3] >= np.quantile(strengths, DROP_WEAKEST)]
    periods = np.array([r[1] for r in raw])
    if len(periods) >= 3:
        padded = np.pad(periods, 1, mode="edge")
        periods = np.median(np.stack([padded[:-2], padded[1:-1], padded[2:]]), axis=0)
    return [_Fit(r[0], float(p), r[2], r[3]) for r, p in zip(raw, periods)]


def _peaks(env: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """Local maxima of the onset strength that stand out from their surroundings."""
    inner = (env[1:-1] >= env[:-2]) & (env[1:-1] > env[2:])
    idx = np.flatnonzero(inner) + 1
    reach = int(LOCAL_MAX_S / step)
    padded = np.pad(env, reach, mode="constant")
    windows = np.lib.stride_tricks.sliding_window_view(padded, 2 * reach + 1)
    local_max = windows.max(axis=1)
    idx = idx[env[idx] >= SNAP_FLOOR * local_max[idx]]
    return idx, env[idx]


def _refine(samples: np.ndarray, rate: float, near: float) -> float | None:
    """Sharpen an onset time to where the waveform's energy starts its climb.

    The search runs from 15 ms before to 35 ms after `near` (spectral flux
    peaks a little before the attack it marks). Energy is a centred 5 ms
    running mean of the squared signal, read every millisecond. The floor is
    the highest energy in the first 5 ms of the search; the attack is the
    first point a tenth of the way from the floor to the top. Returns None
    when the top is not at least four times the floor (no sharp attack).
    """
    width = max(1, int(REFINE_WINDOW_S * rate))
    a = int((near - REFINE_BEFORE_S) * rate) - width
    b = int((near + REFINE_AFTER_S) * rate) + width
    if a < 0 or b > len(samples):
        return None
    energy = np.convolve(samples[a:b] ** 2, np.ones(width) / width, mode="valid")
    hop = max(1, int(REFINE_HOP_S * rate))
    level = energy[::hop]
    if len(level) < 6:
        return None
    floor, top = float(level[:REFINE_FLOOR_FRAMES].max()), float(level.max())
    if top < REFINE_MIN_RISE * max(floor, 1e-15):
        return None
    k = int(np.argmax(level >= floor + REFINE_FRACTION * (top - floor)))
    return (a + width / 2.0 + k * hop) / rate


def _best_path(env: np.ndarray, period_frames: np.ndarray) -> np.ndarray:
    """Frames of the beat path maximising onset strength less a penalty on off-period steps."""
    n = len(env)
    score = env.astype(np.float64).copy()
    back = np.full(n, -1)
    for t in range(n):
        p = period_frames[t]
        lo, hi = max(0, t - int(STEP_RANGE[1] * p)), t - int(STEP_RANGE[0] * p)
        if hi <= lo:
            continue
        steps = t - np.arange(lo, hi)
        candidates = score[lo:hi] - TIGHTNESS * np.log(steps / p) ** 2
        k = int(np.argmax(candidates))
        if candidates[k] > 0:
            score[t] += candidates[k]
            back[t] = lo + k
    tail = int(period_frames[-1]) if n else 0
    t = n - tail + int(np.argmax(score[n - tail:])) if n else -1
    path = []
    while t >= 0:
        path.append(t)
        t = back[t]
    return np.array(path[::-1], dtype=int)


def _silent_edges(spectra: Spectra, beats: list[tuple[float, bool]], period: float) -> list[tuple[float, bool]]:
    """Drop beats at either end that sit in silence and on no onset."""
    x = spectra.samples
    half = int(period * spectra.rate / 2)
    loud = np.sqrt(np.percentile(x[:: max(1, len(x) // 200000)] ** 2, 95)) + 1e-12

    def silent(t: float) -> bool:
        c = int(t * spectra.rate)
        part = x[max(0, c - half):c + half]
        return part.size == 0 or np.sqrt(np.mean(part ** 2)) < loud * SILENT_RATIO

    lo, hi = 0, len(beats)
    while lo < hi and not beats[lo][1] and silent(beats[lo][0]):
        lo += 1
    while hi > lo and not beats[hi - 1][1] and silent(beats[hi - 1][0]):
        hi -= 1
    return beats[lo:hi]


def beat_grid(spectra: Spectra, hint_bpm: float | None = None) -> Grid:
    """Every beat of the stem the spectra were taken from."""
    env = onset_strength(spectra)
    bpm = global_tempo(spectra, hint_bpm)
    fits = _window_fits(env, spectra, 60.0 / bpm)
    centres = np.array([f.centre for f in fits])
    periods = np.array([f.period for f in fits])
    peak_idx, peak_val = _peaks(env, spectra.step)
    raw_times = peak_idx * spectra.step
    sharp = [_refine(spectra.samples, spectra.rate, t) for t in raw_times]
    shifts = [r - t for r, t in zip(sharp, raw_times) if r is not None]
    lag = float(np.median(shifts)) if shifts else 0.0
    attacks = np.array([r if r is not None else t + lag for r, t in zip(sharp, raw_times)])
    order = np.argsort(attacks)
    attacks, peak_val = attacks[order], peak_val[order]

    def snap(t: float) -> float | None:
        lo, hi = np.searchsorted(attacks, [t - SNAP_S, t + SNAP_S])
        if hi <= lo:
            return None
        return float(attacks[lo + int(np.argmax(peak_val[lo:hi]))])

    frame_times = np.arange(len(env)) * spectra.step
    period_frames = np.interp(frame_times, centres, periods) / spectra.step
    path = _best_path(env, period_frames) * spectra.step + lag
    found = [snap(t) for t in path]
    beats = [(f if f is not None else t, f is not None) for t, f in zip(path, found)]
    beats = _silent_edges(spectra, beats, 60.0 / bpm)
    times = np.array([b[0] for b in beats])
    return Grid(beats=times, on_onset=np.array([b[1] for b in beats]),
                bpm=float(60.0 / np.median(np.diff(times))) if len(times) > 1 else bpm,
                curve_times=centres, tempo_bpm=60.0 / periods)
