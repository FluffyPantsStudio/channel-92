"""The audio a render hears: the shot's own lines gated out of the voice stem, and a quieter compressed copy.

Gated voice: exactly the slice, 48 kHz stereo, silent except from the shot's first line start to its last line end.
The gate opens 30 to 70 ms before the first line and shuts 30 to 250 ms after the last, following the sound (a
breath in, a release out), but never reaches into a neighbouring line (it is fully shut 20 ms before one starts).
Edges are 20 ms raised-cosine fades.

Soft copy: a compressor (threshold -30 dB, ratio 6, attack 5 ms, release 120 ms), then makeup gain back to the
gated copy's voiced level, then -8 dB, so the copy sits 8 dB under the gated one with its loud vowels tamed. A long
loud vowel on the full vocal made renders open into a laugh; on this copy they did not.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..wav import save_wav
from .features import levels_db, mono, resample, working_level_db

OUT_RATE = 48_000
RAMP_S = 0.02
GUARD_S = 0.02
BEFORE_S = (0.03, 0.07)
AFTER_S = (0.03, 0.25)
QUIET_UNDER_WORKING_DB = 18.0
EDGE_WINDOW_S = 0.04
TOUCH_S = 0.05
LEVEL_FRAME_S = 0.01
MARGIN_S = 0.1

THRESHOLD_DB = -30.0
RATIO = 6.0
ATTACK_S = 0.005
RELEASE_S = 0.12
SOFT_DROP_DB = -8.0
CHUNK_S = 0.001


@dataclass(frozen=True)
class GatedVoice:
    samples: np.ndarray
    rate: int
    open_from: float
    open_to: float
    warnings: tuple[str, ...]


def _level_at(levels: np.ndarray, t: float) -> float:
    index = int(np.floor(t / LEVEL_FRAME_S))
    return float(levels[index]) if 0 <= index < len(levels) else -120.0


def _window_level(levels: np.ndarray, centre: float) -> float:
    first = int(np.floor((centre - EDGE_WINDOW_S / 2) / LEVEL_FRAME_S))
    last = int(np.ceil((centre + EDGE_WINDOW_S / 2) / LEVEL_FRAME_S))
    chunk = levels[max(0, first):max(0, last)]
    return float(10 * np.log10(np.mean(10 ** (chunk / 10)))) if len(chunk) else -120.0


def _edges(levels: np.ndarray, quiet: float, start: float, end: float, before_limit: float,
           after_limit: float) -> tuple[float, float]:
    sound_start = start
    while sound_start - LEVEL_FRAME_S >= start - BEFORE_S[1] and _level_at(levels, sound_start - LEVEL_FRAME_S) >= quiet:
        sound_start -= LEVEL_FRAME_S
    sound_end = end
    while sound_end < end + AFTER_S[1] and _level_at(levels, sound_end) >= quiet:
        sound_end += LEVEL_FRAME_S
    open_from = float(np.clip(sound_start - RAMP_S, start - BEFORE_S[1], start - BEFORE_S[0]))
    open_to = float(np.clip(sound_end + RAMP_S, end + AFTER_S[0], end + AFTER_S[1]))
    return max(open_from, before_limit), min(open_to, after_limit)


def _slice(voice: np.ndarray, rate: int, start_s: float, seconds: float, out_rate: int) -> np.ndarray:
    """Channels x samples of the stem from start_s, `seconds` long at out_rate, zero beyond the stem."""
    data = np.asarray(voice, dtype=np.float64)
    data = data[:, None] if data.ndim == 1 else data
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    data = data[:, :2]
    first = int(round((start_s - MARGIN_S) * rate))
    count = int(round((seconds + 2 * MARGIN_S) * rate))
    chunk = np.zeros((count, 2))
    lo, hi = max(first, 0), min(first + count, len(data))
    if hi > lo:
        chunk[lo - first:hi - first] = data[lo:hi]
    out_count = int(round(seconds * out_rate))
    skip = int(round(MARGIN_S * out_rate))
    channels = [resample(chunk[:, c], rate, out_rate) if rate != out_rate else chunk[:, c] for c in range(2)]
    return np.stack([ch[skip:skip + out_count] for ch in channels], axis=1)


def _gate_gain(times: np.ndarray, open_from: float, open_to: float) -> np.ndarray:
    rise = np.clip((times - open_from) / RAMP_S, 0.0, 1.0)
    fall = np.clip((open_to - times) / RAMP_S, 0.0, 1.0)
    gain = 0.5 - 0.5 * np.cos(np.pi * np.minimum(rise, fall))
    gain[(times <= open_from) | (times >= open_to)] = 0.0
    return gain


def gated_voice(voice: np.ndarray, rate: int, *, slice_from: float, seconds: float,
                own: list[tuple[float, float]], rivals: list[tuple[float, float]] = (),
                out_rate: int = OUT_RATE) -> GatedVoice:
    """Gate the shot's own lines (song times) out of the voice stem for the slice starting at `slice_from`."""
    if not own:
        raise ValueError("a gated voice needs at least one of the shot's own lines")
    start = min(a for a, _ in own)
    end = max(b for _, b in own)
    levels = levels_db(mono(voice), rate, LEVEL_FRAME_S)
    working = working_level_db(levels)
    warnings: list[str] = []
    quiet = working - QUIET_UNDER_WORKING_DB if working is not None else 0.0
    prev_end = max((b for a, b in rivals if b <= start + 1e-9), default=-np.inf)
    next_start = min((a for a, b in rivals if a >= end - 1e-9), default=np.inf)
    open_from, open_to = _edges(levels, quiet, start, end, prev_end + GUARD_S, next_start - GUARD_S)
    if open_from < slice_from or open_to > slice_from + seconds:
        warnings.append(f"the lines ({start:.2f} to {end:.2f}) run outside the slice ({slice_from:.2f} to "
                        f"{slice_from + seconds:.2f}); the gate is cut at the slice")
    samples = _slice(voice, rate, slice_from, seconds, out_rate)
    times = slice_from + np.arange(len(samples)) / out_rate
    gated = samples * _gate_gain(times, open_from, open_to)[:, None]
    in_lines = levels[max(0, int(start / LEVEL_FRAME_S)):max(0, int(end / LEVEL_FRAME_S) + 1)]
    if working is None or np.max(in_lines, initial=-120.0) < quiet:
        warnings.append("no voice in the slice's lines: the line times are probably wrong")
    else:
        for edge, neighbour, name in ((open_from, prev_end, "opening"), (open_to, next_start, "closing")):
            touches = abs(edge - neighbour) <= TOUCH_S + GUARD_S
            if not touches and _window_level(levels, edge) >= quiet:
                warnings.append(f"the gate's {name} edge at {edge:.2f} s is inside sound: a word may be clipped")
    return GatedVoice(gated, out_rate, round(open_from, 4), round(open_to, 4), tuple(warnings))


def _active_db(samples: np.ndarray, rate: int) -> float | None:
    levels = levels_db(samples, rate, LEVEL_FRAME_S)
    active = levels[levels > -60.0]
    return float(10 * np.log10(np.mean(10 ** (active / 10)))) if len(active) else None


def soft_copy(samples: np.ndarray, rate: int) -> np.ndarray:
    """The compressed copy, 8 dB under the input's voiced level. Same shape as the input."""
    data = np.asarray(samples, dtype=np.float64)
    frames = data if data.ndim == 2 else data[:, None]
    block = max(1, int(round(CHUNK_S * rate)))
    count = int(np.ceil(len(frames) / block))
    padded = np.zeros((count * block, frames.shape[1]))
    padded[:len(frames)] = frames
    power = (padded ** 2).max(axis=1).reshape(count, block).mean(axis=1)
    attack = 1 - np.exp(-CHUNK_S / ATTACK_S)
    release = 1 - np.exp(-CHUNK_S / RELEASE_S)
    envelope = np.empty(count)
    level = 0.0
    for i, p in enumerate(power):
        level += (attack if p > level else release) * (p - level)
        envelope[i] = level
    over = 10 * np.log10(envelope + 1e-30) - THRESHOLD_DB
    reduction_db = -np.clip(over, 0.0, None) * (1 - 1 / RATIO)
    gain = np.repeat(10 ** (reduction_db / 20), block)[:len(frames)]
    squeezed = frames * gain[:, None]
    before, after = _active_db(frames, rate), _active_db(squeezed, rate)
    makeup_db = (before - after) if before is not None and after is not None else 0.0
    out = squeezed * 10 ** ((makeup_db + SOFT_DROP_DB) / 20)
    return out if data.ndim == 2 else out[:, 0]


def write_voice_pair(gated: GatedVoice, stem: str | Path) -> tuple[Path, Path]:
    """Write `<stem>.voice.wav` and `<stem>.voice-soft.wav`; returns both paths."""
    base = Path(stem)
    gated_path = save_wav(base.with_name(base.name + ".voice.wav"), gated.samples, gated.rate)
    soft_path = save_wav(base.with_name(base.name + ".voice-soft.wav"), soft_copy(gated.samples, gated.rate),
                          gated.rate)
    return gated_path, soft_path
