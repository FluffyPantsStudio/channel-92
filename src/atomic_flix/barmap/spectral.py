"""Short-time spectra of a stem, reduced to the few tracks the beat and bar stages read.

The stem is folded to mono and brought down to about 22 kHz. From one fine
spectrogram (46 ms windows every 5.8 ms) comes broadband spectral flux on log
magnitudes, for finding beats. A longer spectrogram (93 ms windows every 11.6 ms, finer
in frequency) gives flux on plain magnitudes under 150 Hz (kicks) and from
1.5 to 6 kHz weighted by spectral flatness (snares and hats: noisy, not
tonal). Plain magnitudes keep a loud kick louder than a soft one, which the
bar-one scores rely on; log magnitudes would flatten them. Two coarser
spectrograms with finer frequency steps give pitch-class profiles: one from
130 Hz to 2 kHz for chords, one from 40 to 130 Hz for the bass.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TARGET_RATE = 22050
FINE_FFT = 1024
FINE_HOP = 128
DRUM_FFT = 2048
DRUM_HOP = 256
TONAL_FFT = 1024
TONAL_HOP = 256
TONAL_DECIMATE = 4
BASS_DECIMATE = 16
BASS_FFT = 512
BASS_HOP = 64
LOG_GAIN = 100.0
BLOCK_FRAMES = 2048
ONSET_BAND = (30.0, 8000.0)
KICK_BAND = (30.0, 150.0)
SNARE_BAND = (1500.0, 6000.0)
CHORD_BAND = (130.0, 2000.0)
BASS_BAND = (40.0, 130.0)


def _mono(samples: np.ndarray) -> np.ndarray:
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim == 2:
        return data.mean(axis=1)
    if data.ndim != 1:
        raise ValueError("audio must be 1-D or (frames, channels)")
    return data


def _lowpass_taps(factor: int, taps: int = 63) -> np.ndarray:
    cutoff = 0.45 / factor
    n = np.arange(taps) - (taps - 1) / 2.0
    h = 2 * cutoff * np.sinc(2 * cutoff * n) * np.hanning(taps)
    return h / h.sum()


def decimate(x: np.ndarray, factor: int) -> np.ndarray:
    """Low-pass then keep every `factor`-th sample."""
    if factor <= 1:
        return x
    return np.convolve(x, _lowpass_taps(factor), mode="same")[::factor]


def _frames(x: np.ndarray, nfft: int, hop: int):
    """Yield (first frame index, magnitudes) chunks of a centred STFT; frame i is centred on sample i*hop."""
    padded = np.pad(x, (nfft // 2, nfft // 2))
    count = 1 + (len(padded) - nfft) // hop if len(padded) >= nfft else 0
    taper = np.hanning(nfft).astype(np.float32)
    for first in range(0, count, BLOCK_FRAMES):
        n = min(BLOCK_FRAMES, count - first)
        idx = (first + np.arange(n))[:, None] * hop + np.arange(nfft)[None, :]
        yield first, np.abs(np.fft.rfft(padded[idx].astype(np.float32) * taper, axis=1))


def _band(freqs: np.ndarray, band: tuple[float, float]) -> slice:
    return slice(int(np.searchsorted(freqs, band[0])), int(np.searchsorted(freqs, band[1])))


def _pitch_profile(x: np.ndarray, rate: float, nfft: int, hop: int, band: tuple[float, float]) -> np.ndarray:
    """Energy per pitch class (frames, 12), not normalised."""
    freqs = np.fft.rfftfreq(nfft, 1.0 / rate)
    keep = (freqs >= band[0]) & (freqs < band[1])
    classes = np.round(12 * np.log2(freqs[keep] / 440.0)).astype(int) % 12
    out = []
    for _, mag in _frames(x, nfft, hop):
        power = mag[:, keep] ** 2
        profile = np.zeros((len(mag), 12), dtype=np.float32)
        for pc in range(12):
            profile[:, pc] = power[:, classes == pc].sum(axis=1)
        out.append(profile)
    return np.concatenate(out) if out else np.zeros((0, 12), dtype=np.float32)


def _drum_tracks(x: np.ndarray, rate: float) -> tuple[np.ndarray, np.ndarray]:
    """Kick and snare onset tracks: rises of plain magnitude in their bands, snare times flatness."""
    freqs = np.fft.rfftfreq(DRUM_FFT, 1.0 / rate)
    kick_band, snare_band = _band(freqs, KICK_BAND), _band(freqs, SNARE_BAND)
    low, snare = [], []
    previous = None
    for _, mag in _frames(x, DRUM_FFT, DRUM_HOP):
        before = np.vstack([mag[:1] if previous is None else previous, mag[:-1]])
        hit = np.maximum(mag - before, 0.0)
        part = mag[:, snare_band] + 1e-9
        flat = np.exp(np.log(part).mean(axis=1)) / part.mean(axis=1)
        low.append(hit[:, kick_band].sum(axis=1))
        snare.append(hit[:, snare_band].sum(axis=1) * flat)
        previous = mag[-1:]
    return np.concatenate(low), np.concatenate(snare)


@dataclass(frozen=True)
class Spectra:
    """Feature tracks of one stem. Fine tracks are sampled every `hop / rate` seconds from 0."""

    rate: float
    hop: int
    duration: float
    samples: np.ndarray
    onset: np.ndarray
    low: np.ndarray
    snare: np.ndarray
    drum_step: float
    chroma: np.ndarray
    chroma_step: float
    bass: np.ndarray
    bass_step: float

    @property
    def step(self) -> float:
        return self.hop / self.rate

    def frame(self, seconds: float) -> int:
        return int(round(seconds / self.step))

    def times(self) -> np.ndarray:
        return np.arange(len(self.onset)) * self.step

    def peak(self, which: str, start: float, end: float) -> float:
        """Largest value of the 'low' (kick) or 'snare' track between two times."""
        track = self.low if which == "low" else self.snare
        a = max(0, int(round(start / self.drum_step)))
        b = min(len(track), int(round(end / self.drum_step)) + 1)
        return float(track[a:b].max()) if b > a else 0.0

    def profile(self, which: str, start: float, end: float) -> np.ndarray:
        """Mean pitch-class profile ('chroma' or 'bass') between two times."""
        table, step = (self.chroma, self.chroma_step) if which == "chroma" else (self.bass, self.bass_step)
        a, b = max(0, int(round(start / step))), min(len(table), int(round(end / step)) + 1)
        return table[a:b].mean(axis=0) if b > a else np.zeros(12)


def spectra_of(samples: np.ndarray, rate: int) -> Spectra:
    """Compute the feature tracks of a stem given as samples at `rate` Hz."""
    mono = _mono(samples)
    factor = max(1, int(rate // TARGET_RATE))
    x = decimate(mono, factor)
    sr = rate / factor
    freqs = np.fft.rfftfreq(FINE_FFT, 1.0 / sr)
    onset_band = _band(freqs, ONSET_BAND)
    onset = []
    previous = None
    for _, mag in _frames(x, FINE_FFT, FINE_HOP):
        logmag = np.log1p(LOG_GAIN * mag)
        before = np.vstack([logmag[:1] if previous is None else previous, logmag[:-1]])
        onset.append(np.maximum(logmag - before, 0.0)[:, onset_band].sum(axis=1))
        previous = logmag[-1:]
    low, snare = _drum_tracks(x, sr)
    tonal = decimate(x, TONAL_DECIMATE)
    deep = decimate(tonal, BASS_DECIMATE // TONAL_DECIMATE)
    tonal_rate, deep_rate = sr / TONAL_DECIMATE, sr / BASS_DECIMATE
    return Spectra(
        rate=sr, hop=FINE_HOP, duration=len(mono) / rate, samples=x,
        onset=np.concatenate(onset), low=low, snare=snare, drum_step=DRUM_HOP / sr,
        chroma=_pitch_profile(tonal, tonal_rate, TONAL_FFT, TONAL_HOP, CHORD_BAND),
        chroma_step=TONAL_HOP / tonal_rate,
        bass=_pitch_profile(deep, deep_rate, BASS_FFT, BASS_HOP, BASS_BAND),
        bass_step=BASS_HOP / deep_rate)
