"""Sound features for placing a render: levels, resampling, and level-proof log-mel frames.

Frames are 10 ms apart at 16 kHz (hop 160, 512-point FFT, Hann window, centred so frame i sits at i x 10 ms). Each
frame is 40 mel bands from 120 Hz to 6.5 kHz in log power with the frame's own mean removed, so a copy 8 dB down
gives the same vectors, then scaled to unit length. A silent frame (50 dB under the loudest) becomes a separate unit
vector, so silence matches silence (distance 0) and never matches sound (distance 1).
"""

from __future__ import annotations

import numpy as np

FEATURE_RATE = 16_000
HOP = 160
HOP_S = HOP / FEATURE_RATE
N_FFT = 512
N_BANDS = 40
LOW_HZ = 120.0
HIGH_HZ = 6_500.0
SILENT_DB = 50.0
FLOOR_DB = -120.0


def mono(samples: np.ndarray) -> np.ndarray:
    data = np.asarray(samples, dtype=np.float64)
    return data.mean(axis=1) if data.ndim == 2 else data


def resample(samples: np.ndarray, rate_in: int, rate_out: int) -> np.ndarray:
    """Band-limited resampling of a mono signal by FFT (an ideal low-pass when going down)."""
    x = mono(samples)
    if rate_in == rate_out or len(x) == 0:
        return x.copy()
    n_made = int(round(len(x) * rate_out / rate_in))
    spectrum = np.fft.rfft(x)
    keep = min(len(spectrum), n_made // 2 + 1)
    out_spectrum = np.zeros(n_made // 2 + 1, dtype=complex)
    out_spectrum[:keep] = spectrum[:keep]
    return np.fft.irfft(out_spectrum, n_made) * (n_made / len(x))


def levels_db(samples: np.ndarray, rate: int, frame_s: float = 0.01) -> np.ndarray:
    """RMS level in dBFS of consecutive frames (10 ms by default); channels are averaged in power."""
    data = np.asarray(samples, dtype=np.float64)
    power = (data ** 2).mean(axis=1) if data.ndim == 2 else data ** 2
    size = max(1, int(round(frame_s * rate)))
    count = len(power) // size
    if count == 0:
        return np.full(0, FLOOR_DB)
    mean_power = power[:count * size].reshape(count, size).mean(axis=1)
    return np.maximum(10 * np.log10(mean_power + 1e-30), FLOOR_DB)


def working_level_db(levels: np.ndarray) -> float | None:
    """The 95th percentile of frames above -60 dBFS; None when nothing is that loud."""
    loud = levels[levels > -60.0]
    return float(np.percentile(loud, 95)) if len(loud) else None


def _mel(hz: np.ndarray | float) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + np.asarray(hz) / 700.0)


def _hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10 ** (mel / 2595.0) - 1.0)


def mel_bank() -> np.ndarray:
    """Triangular filters, shape (N_BANDS, N_FFT // 2 + 1)."""
    edges = _hz(np.linspace(_mel(LOW_HZ), _mel(HIGH_HZ), N_BANDS + 2))
    bins = np.fft.rfftfreq(N_FFT, 1 / FEATURE_RATE)
    bank = np.zeros((N_BANDS, len(bins)))
    for band in range(N_BANDS):
        low, mid, high = edges[band:band + 3]
        rising = (bins - low) / (mid - low)
        falling = (high - bins) / (high - mid)
        bank[band] = np.clip(np.minimum(rising, falling), 0.0, None)
    return bank


_BANK = mel_bank()
_SPAN_FRAMES = np.hanning(N_FFT)


def frame_count(samples_16k: np.ndarray) -> int:
    return len(samples_16k) // HOP + 1


def sound_features(samples: np.ndarray, rate: int) -> np.ndarray:
    """Unit feature vectors, shape (frames, N_BANDS + 1): mean-removed log-mel, the last slot marks silence."""
    x = resample(samples, rate, FEATURE_RATE) if rate != FEATURE_RATE else mono(samples)
    count = frame_count(x)
    padded = np.concatenate([np.zeros(N_FFT // 2), x, np.zeros(N_FFT)])
    starts = np.arange(count) * HOP
    frames = padded[starts[:, None] + np.arange(N_FFT)[None, :]] * _SPAN_FRAMES
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    bands = power @ _BANK.T
    frame_db = 10 * np.log10(bands.sum(axis=1) + 1e-30)
    silent = frame_db < frame_db.max() - SILENT_DB if count else np.zeros(0, dtype=bool)
    log_bands = np.log10(bands + 1e-12)
    centred = log_bands - log_bands.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(centred, axis=1, keepdims=True)
    silent |= norms[:, 0] < 1e-9
    unit = np.where(norms > 1e-9, centred / np.maximum(norms, 1e-9), 0.0)
    out = np.zeros((count, N_BANDS + 1))
    out[:, :N_BANDS] = unit
    out[silent, :N_BANDS] = 0.0
    out[silent, N_BANDS] = 1.0
    return out
