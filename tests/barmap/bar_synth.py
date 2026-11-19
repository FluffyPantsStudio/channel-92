"""Synthetic songs for the bar-one tie tests, made in the test run.

Results are cached; treat them as read-only. `tie_song` builds a groove where the bar's one and three look alike to the
drums and to the keys (kick on 1 and 3, snare on 2 and 4, a new keys chord
every two beats). Options add the cues that can still tell them apart: a bass
whose root moves only on the one, or an eight-bar phrase where a soft pad
comes in on the first bar of every second phrase.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from atomic_flix.wav import read_wav

RATE = 22050
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic"

# Keys move in whole tones so neighbouring chords share no pitch class.
KEYS = ((0, 4, 7), (2, 6, 9), (4, 8, 11), (6, 10, 1))
BASS_ROOTS = (0, 5, 7, 3)


@lru_cache(maxsize=None)
def load_fixture(name: str) -> tuple[dict, dict]:
    """(stems as mono arrays, truth) for one of the Phase 0 synthetic fixtures."""
    folder = FIXTURES / name
    truth = json.loads((folder / "truth.json").read_text(encoding="utf-8"))
    stems = {}
    for key in ("drums", "band", "mix"):
        samples, rate = read_wav(folder / f"{key}.wav")
        assert rate == truth["rate"]
        stems[key] = samples[:, 0]
    return stems, truth


def _kick(gain=0.7):
    t = np.arange(int(0.35 * RATE)) / RATE
    freq = 50.0 + 70.0 * np.exp(-t / 0.04)
    return gain * np.clip(t / 0.001, 0, 1) * np.exp(-t / 0.08) * np.sin(2 * np.pi * np.cumsum(freq) / RATE)


def _snare(rng, gain=0.35):
    n = int(0.3 * RATE)
    spec = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / RATE)
    spec[(freqs < 1800) | (freqs > 7000)] = 0
    noise = np.fft.irfft(spec, n)
    noise /= np.abs(noise).max()
    t = np.arange(n) / RATE
    return gain * np.clip(t / 0.001, 0, 1) * np.exp(-t / 0.05) * noise


def _tone(freqs, seconds, gain):
    n = int(round(seconds * RATE))
    t = np.arange(n) / RATE
    out = sum(np.sin(2 * np.pi * f * t) for f in freqs) / max(1, len(freqs))
    ramp = min(int(0.01 * RATE), n // 2)
    env = np.ones(n)
    env[:ramp] = np.linspace(0, 1, ramp)
    env[n - ramp:] = np.linspace(1, 0, ramp)
    return gain * out * env


def _place(track, sound, t):
    a = int(round(t * RATE))
    b = min(len(track), a + len(sound))
    track[a:b] += sound[: b - a]


def four_on_the_floor(bars: int = 16, bpm: float = 120.0) -> tuple[dict, dict]:
    """The same kick on every beat and nothing else: no way to tell where a bar starts."""
    period = 60.0 / bpm
    beats = 0.5 + period * np.arange(4 * bars)
    drums = np.zeros(int(round((beats[-1] + 2.0) * RATE)))
    for t in beats:
        _place(drums, _kick(), t)
    drums *= 0.9 / np.abs(drums).max()
    silent = np.zeros_like(drums)
    return {"drums": drums, "band": silent, "mix": drums}, {"beats": beats.tolist(), "downbeat_slot": None, "rate": RATE}


@lru_cache(maxsize=None)
def tie_song(bars: int = 32, bpm: float = 111.0, pickup: int = 1, bass: bool = False,
             phrase_pad: bool = False, seed: int = 5) -> tuple[dict, dict]:
    """(stems, truth) for a song whose one and three tie on drums and keys."""
    rng = np.random.default_rng(seed)
    period = 60.0 / bpm
    count = pickup + 4 * bars
    beats = 0.5 + period * np.arange(count + 1)
    total = int(round((beats[-1] + 2.0) * RATE))
    drums, band = np.zeros(total), np.zeros(total)
    _place(drums, _snare(rng), beats[0])
    for i in range(pickup, count):
        beat_in_bar = (i - pickup) % 4
        if beat_in_bar % 2 == 0:
            _place(drums, _kick(), beats[i])
            chord = KEYS[((i - pickup) // 2) % len(KEYS)]
            _place(band, _tone([261.63 * 2 ** (pc / 12) for pc in chord], 2 * period, 0.12), beats[i])
        else:
            _place(drums, _snare(rng), beats[i])
    for bar in range(bars):
        first = pickup + 4 * bar
        start, end = beats[first], beats[first + 4]
        if bass:
            root = BASS_ROOTS[bar % len(BASS_ROOTS)]
            _place(band, _tone([55.0 * 2 ** (root / 12)], end - start, 0.25), start)
        if phrase_pad and bar % 16 == 8:
            stop = beats[min(first + 32, count)]
            _place(band, _tone([523.25 * 1.5, 659.25 * 1.5], stop - start, 0.05), start)
    mix = drums + band
    scale = 0.9 / np.abs(mix).max()
    stems = {"drums": drums * scale, "band": band * scale, "mix": mix * scale}
    truth = {"beats": beats[:count].tolist(), "downbeat_slot": pickup % 4, "rate": RATE}
    return stems, truth
