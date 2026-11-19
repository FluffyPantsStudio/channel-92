"""Write a tiny synthetic song with everything a film needs to start: stems, lyric and shot list.

    python tools/synth_song.py OUT_DIR

OUT_DIR gets mix.wav, voice.wav, band.wav, drums.wav (22.05 kHz mono), lyric.txt, shots.txt and truth.json (the
beats, the bar phase and each sung line's start and end, for checking). Deterministic: the same files every run.

The groove is 111 BPM, fifteen bars, the bar's one on the first beat: kick on one and three, a noise snare on two
and four, a new chord and bass root on every one. Four sung lines are buzzy vowels whose pitch moves every quarter
second, so a render that carries the sent voice can be placed on it by sound.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from atomic_flix.formats import stamped  # noqa: E402
from atomic_flix.wav import save_wav  # noqa: E402

RATE = 22050
BPM = 111.0
FIRST_BEAT = 0.5
BARS = 15
TAIL_S = 2.0
CHORDS = ((0, 4, 7), (5, 9, 0), (7, 11, 2), (9, 0, 4))
ROOTS = (0, 5, 7, 9)
# Sung lines as (first beat, last beat), on the beat grid; each starts half a beat after a bar's one.
SUNG = ((8.5, 14.0), (24.5, 30.0), (32.5, 38.0), (44.5, 52.0))
LYRIC = """[Verse]
The tub is warm tonight
We float above the town
The stars are coming down
[Chorus]
Hold on, hold on to me
"""
SHOTS = """S01 vocal: v01
  still: stills/S01.png
  setup: roof
  crop: 1.0
  place: a quiet rooftop at night

  gaze: straight into the lens

N01 cutaway
  still: stills/N01.png
  cam_move: locked
  beat: the white bathtub glows under the stars

S02 vocal: v02 v03
  still: stills/S02.png
  setup: roof
  crop: 0.6
  place: a quiet rooftop at night
  gaze: straight into the lens

S03 vocal: v04
  still: stills/S03.png
  setup: street
  crop: 1.0
  place: an empty street at dawn
  gaze: straight into the lens

N02 cutaway
  still: stills/N02.png
  cam_move: locked
  beat: the street lights go out one by one
"""


def beat_times() -> np.ndarray:
    return FIRST_BEAT + (60.0 / BPM) * np.arange(4 * BARS)


def _place(track: np.ndarray, sound: np.ndarray, at: float) -> None:
    start = int(round(at * RATE))
    stop = min(len(track), start + len(sound))
    track[start:stop] += sound[: stop - start]


def _kick(gain: float) -> np.ndarray:
    t = np.arange(int(0.3 * RATE)) / RATE
    freq = 50.0 + 70.0 * np.exp(-t / 0.04)
    return gain * np.exp(-t / 0.08) * np.sin(2 * np.pi * np.cumsum(freq) / RATE)


def _snare(rng: np.random.Generator) -> np.ndarray:
    n = int(0.25 * RATE)
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / RATE)
    spectrum[(freqs < 1800) | (freqs > 7000)] = 0
    noise = np.fft.irfft(spectrum, n)
    return 0.35 * np.exp(-np.arange(n) / RATE / 0.05) * noise / np.abs(noise).max()


def _tone(freqs, seconds: float, gain: float) -> np.ndarray:
    t = np.arange(int(round(seconds * RATE))) / RATE
    wave = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
    ramp = np.minimum(1.0, np.minimum(t, t[::-1]) / 0.01)
    return gain * wave * ramp


def _sung(seconds: float, seed: int) -> np.ndarray:
    """A buzzy vowel whose pitch steps every quarter second (a tune), with soft edges."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(round(seconds * RATE))) / RATE
    steps = 196.0 * 2 ** (rng.integers(0, 8, size=int(seconds / 0.25) + 1) / 12)
    pitch = steps[(t / 0.25).astype(int)]
    phase = 2 * np.pi * np.cumsum(pitch) / RATE
    formant = 1.0 + 0.5 * np.sin(2 * np.pi * 1.5 * t)
    wave = sum(np.sin(k * phase) / k ** formant for k in range(1, 7))
    edge = np.minimum(1.0, np.minimum(t, t[::-1]) / 0.03)
    return 0.25 * wave * edge * (1.0 + 0.15 * np.sin(2 * np.pi * 4.0 * t))


def make_stems() -> tuple[dict[str, np.ndarray], dict]:
    beats = beat_times()
    total = int(round((beats[-1] + TAIL_S) * RATE))
    rng = np.random.default_rng(11)
    drums, band, voice = np.zeros(total), np.zeros(total), np.zeros(total)
    period = 60.0 / BPM
    for index, at in enumerate(beats):
        count = index % 4
        if count in (0, 2):
            _place(drums, _kick(0.7 if count == 0 else 0.55), at)
        else:
            _place(drums, _snare(rng), at)
        if count == 0:
            bar = index // 4
            chord = CHORDS[bar % len(CHORDS)]
            _place(band, _tone([261.63 * 2 ** (pc / 12) for pc in chord], 4 * period, 0.10), at)
            _place(band, _tone([55.0 * 2 ** (ROOTS[bar % len(ROOTS)] / 12)], 4 * period, 0.2), at)
    lines = []
    for number, (first, last) in enumerate(SUNG, start=1):
        start = FIRST_BEAT + first * period
        end = FIRST_BEAT + last * period
        _place(voice, _sung(end - start, seed=number), start)
        lines.append({"id": f"v{number:02d}", "start": round(start, 3), "end": round(end, 3)})
    mix = drums + band + voice
    scale = 0.89 / np.abs(mix).max()
    stems = {"drums": drums * scale, "band": band * scale, "voice": voice * scale, "mix": mix * scale}
    truth = {"rate": RATE, "bpm": BPM, "downbeat_slot": 0, "beats": [round(float(b), 4) for b in beats],
             "lines": lines, "seconds": round(total / RATE, 3)}
    return stems, truth


def write_song(folder: Path) -> dict:
    """Write the song's files into FOLDER; returns the truth."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stems, truth = make_stems()
    for name, samples in stems.items():
        save_wav(folder / f"{name}.wav", samples, RATE)
    (folder / "lyric.txt").write_text(LYRIC, encoding="utf-8", newline="\n")
    (folder / "shots.txt").write_text(SHOTS, encoding="utf-8", newline="\n")
    (folder / "truth.json").write_text(json.dumps(stamped("fixture-truth", truth), indent=1) + "\n", encoding="utf-8", newline="\n")
    return truth


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", type=Path, help="folder for the song's files")
    args = parser.parse_args(argv)
    truth = write_song(args.out)
    print(f"wrote a {truth['seconds']:.1f} s song with {len(truth['lines'])} sung lines to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
