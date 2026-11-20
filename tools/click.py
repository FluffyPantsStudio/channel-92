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

from atomic_flix.barmap.click import (COUNT_HZ, PEAK_LIMIT, RATE, TAIL_S,  # noqa: F401 (the tool's API)
                                      mix_over, render_clicks, to_rate as _to_rate)
from atomic_flix.wav import WavError, read_wav, save_wav


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
