"""Write a counting click track, to confirm by ear where the bar's one is.

    python tools/click.py BEATS.json --phase P --out click.wav [--over song.wav --gain -6]

BEATS.json holds a list of beat times in seconds under "beats" (or --key). With
phase P, the bar's one is every beat whose index mod 4 is P. Each count has its
own pitch: the one is loud and high, then two, three and four rise softly back
toward it, so a listener can count "ONE two three four" along with the song.
Output is 44100 Hz mono 16-bit. With --over, the clicks are laid over that WAV
(downmixed to mono, resampled by linear interpolation, music at --gain dB).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from atomic_flix.wav import WavError, read_wav, save_wav

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


def _to_rate(music: np.ndarray, rate: int, aim: int) -> np.ndarray:
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


def load_beats(path, key: str = "beats") -> list[float]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or key not in data:
        raise ValueError(f"{path}: no list of beat times under '{key}'")
    beats = data[key]
    if not isinstance(beats, list) or not all(isinstance(b, (int, float)) for b in beats):
        raise ValueError(f"{path}: '{key}' must be a list of numbers (seconds)")
    return [float(b) for b in beats]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Write a counting click track on the beats of a song.")
    parser.add_argument("beats_json")
    parser.add_argument("--phase", type=int, required=True, help="the bar's one is on beats where index mod 4 = phase")
    parser.add_argument("--out", required=True, help="output WAV, 44100 Hz mono")
    parser.add_argument("--key", default="beats", help="name of the beat list in the JSON (default: beats)")
    parser.add_argument("--over", help="a WAV to lay the clicks over")
    parser.add_argument("--gain", type=float, default=-6.0, help="gain in dB for the --over WAV (default -6)")
    args = parser.parse_args(argv)
    try:
        beats = load_beats(args.beats_json, args.key)
        music = None
        if args.over:
            samples, rate = read_wav(args.over)
            music = _to_rate(samples.mean(axis=1), rate, RATE)
        clicks = render_clicks(beats, args.phase, RATE)
    except (OSError, ValueError, WavError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    out = mix_over(clicks, music, args.gain) if music is not None else clicks
    save_wav(args.out, out, RATE)
    ones = sum(1 for i in range(len(beats)) if i % 4 == args.phase)
    print(f"{args.out}: {len(beats)} beats, {ones} ones at phase {args.phase}, {len(out) / RATE:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
