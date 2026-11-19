"""Build the test fixtures for the beat and bar stages, and the first-film pack.

    python tools/make_fixtures.py synthetic [--out fixtures/synthetic]
    python tools/make_fixtures.py first-film [--src DIR] [--out fixtures/first-film]

`--src` defaults to the first film's folder under FLIX_FIRST_FILM (docs/first-film-replay.md).

Synthetic fixtures are drum, band and mix stems (22050 Hz, mono, 16-bit) with a
truth.json beside them. They are fully deterministic.

The first-film pack is a byte copy of our first film's audio stems and timing
files, with a manifest of sizes and sha256 hashes and a note of what is known
to be true about its bars. It is git-ignored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np

from atomic_flix.formats import stamped
from atomic_flix.wav import save_wav

REPO = Path(__file__).resolve().parents[1]
RATE = 22050
LEAD_IN_S = 0.5
TAIL_S = 2.0

# Whole-tone steps, so neighbouring chords share no pitch class.
CHORDS = ((0, 4, 7), (2, 6, 9), (4, 8, 11), (6, 10, 1))

KICK_GAIN = 0.7
DECOY_KICK_GAIN = 0.95
SNARE_GAIN = 0.35
CHORD_GAIN = 0.12

SYNTHETIC = {
    "steady-111": {"bpm": (111.0, 111.0), "bars": [4] * 32, "decoy": False, "seed": 11},
    "decoy-kick-on-two": {"bpm": (111.0, 111.0), "bars": [4] * 32, "decoy": True, "seed": 12},
    "drift-108-114": {"bpm": (108.0, 114.0), "bars": [4] * 32, "decoy": False, "seed": 13},
    "bar-of-two": {"bpm": (111.0, 111.0), "bars": [4] * 8 + [2] + [4] * 8, "decoy": False, "seed": 14},
}

PICKUP_BEATS = 1

FIRST_FILM_ENV = "FLIX_FIRST_FILM"
FIRST_FILM_SLUG = "the-girl-in-the-magic-tub"


def first_film_src() -> Path | None:
    """The first film's folder under FLIX_FIRST_FILM, or None when the variable is unset."""
    root = os.environ.get(FIRST_FILM_ENV, "").strip()
    return Path(root) / "films" / FIRST_FILM_SLUG if root else None


FIRST_FILM_FILES = (
    "audio/lead.wav", "audio/rest.wav", "audio/song.wav", "audio/group.wav",
    "build/beats.json", "build/lines.json", "build/words.json", "build/drums.json",
    "build/hits.json", "build/phrases.json", "build/loudness.json",
)

FIRST_FILM_TRUTH = {
    "downbeat_slot": 0,
    "downbeat_slot_means": "the bar's one is on beats whose index mod 4 is 0 in build/beats.json",
    "relative_to_old_downbeat": "the bar's one is one beat before the old grid's downbeat",
    "phase_tie": [0, 2],
    "slot_scores": {"0": 2.84, "2": 2.84, "1": -2.97, "3": -2.72},
    "tie_margin": 0.001,
    "stretches_16_bar": "split 5 to 3 between counts 0 and 2",
    "snare_counts": [1, 3],
    "confirmed_by_ear": False,
}

TRUTH_NOTE = """\
Known truth for the first film (The Girl In The Magic Tub)

Bar phase 0. The bar's one falls on the beats whose index mod 4 is 0 in
build/beats.json. That is one beat before the grid's old "downbeat", which was
really beat 2: snare and hat land there and two beats later, and the chords
change a beat before it.

Counts 1 and 3 are the snare beats. A cut there is the mistake to avoid; the
bar-one method rejects them by more than 5 z.

Counts 0 and 2 cannot be told apart by drums or chords in this song: kick
strength and chord change repeat every two beats, so the bar's one and three
look the same (margin 0.001; 16-bar stretches split 5 to 3). A bar-one stage
must report this tie and offer the click track; it must not pick silently.

Not yet confirmed by ear. Make a click on phase 0 over audio/song.wav and count
along; record the answer here when a person has listened.

Source: the prototype result at the end of the core kit spec (2026-11-19).
"""


# ---- synthesis -----------------------------------------------------------------


def beat_times(bpm_from: float, bpm_to: float, count: int) -> list[float]:
    """Beat times starting at LEAD_IN_S, tempo moving linearly by beat index."""
    times = [LEAD_IN_S]
    for k in range(count - 1):
        bpm = bpm_from + (bpm_to - bpm_from) * k / max(count - 2, 1)
        times.append(times[-1] + 60.0 / bpm)
    return times


def _kick(gain: float) -> np.ndarray:
    t = np.arange(int(0.35 * RATE)) / RATE
    freq = 45.0 + 75.0 * np.exp(-t / 0.04)
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    attack = np.clip(t / 0.001, 0.0, 1.0)
    return gain * attack * np.exp(-t / 0.08) * np.sin(phase)


def _snare(gain: float, rng: np.random.Generator) -> np.ndarray:
    n = int(0.3 * RATE)
    noise = rng.standard_normal(n)
    spec = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1 / RATE)
    spec[(freqs < 1800) | (freqs > 7000)] = 0.0
    shaped = np.fft.irfft(spec, n)
    shaped /= np.max(np.abs(shaped)) + 1e-12
    t = np.arange(n) / RATE
    attack = np.clip(t / 0.001, 0.0, 1.0)
    return gain * attack * np.exp(-t / 0.05) * shaped


def _chord(pitch_classes, seconds: float) -> np.ndarray:
    n = int(round(seconds * RATE))
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for pc in pitch_classes:
        f = 261.63 * 2 ** (pc / 12)
        out += np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)
    ramp = min(int(0.01 * RATE), n // 2)
    env = np.ones(n)
    env[:ramp] = np.linspace(0, 1, ramp)
    env[n - ramp:] = np.linspace(1, 0, ramp)
    return CHORD_GAIN * out * env / len(pitch_classes)


def _place(track: np.ndarray, sound: np.ndarray, t: float) -> None:
    start = int(round(t * RATE))
    end = min(len(track), start + len(sound))
    track[start:end] += sound[: end - start]


def _bar_layout(bars: list[int]) -> list[dict]:
    layout = []
    first = PICKUP_BEATS
    for extent in bars:
        layout.append({"first_beat": first, "extent": extent})
        first += extent
    return layout


def build_synthetic(name: str) -> tuple[dict, dict]:
    """Return (stems, truth) for one named fixture; stems are float arrays."""
    spec = SYNTHETIC[name]
    rng = np.random.default_rng(spec["seed"])
    layout = _bar_layout(spec["bars"])
    n_beats = PICKUP_BEATS + sum(spec["bars"])
    beats = beat_times(spec["bpm"][0], spec["bpm"][1], n_beats)
    beats.append(beats[-1] + (beats[-1] - beats[-2]))  # closes the last bar; not a beat of the song
    total = int(round((beats[-1] + TAIL_S) * RATE))
    drums = np.zeros(total)
    band = np.zeros(total)

    _place(drums, _snare(SNARE_GAIN, rng), beats[0])  # the pickup is a count of four
    for bar_no, bar in enumerate(layout):
        first = bar["first_beat"]
        for count in range(bar["extent"]):
            t = beats[first + count]
            if count % 2 == 0:
                _place(drums, _kick(KICK_GAIN), t)
            else:
                _place(drums, _snare(SNARE_GAIN, rng), t)
                if spec["decoy"] and count == 1:
                    _place(drums, _kick(DECOY_KICK_GAIN), t)
        start, end = beats[first], beats[first + bar["extent"]]
        _place(band, _chord(CHORDS[bar_no % len(CHORDS)], end - start), start)

    mix = drums + band
    scale = 0.9 / max(np.max(np.abs(mix)), 1e-9)
    stems = {"drums": drums * scale, "band": band * scale, "mix": mix * scale}

    grid = beats[:n_beats]
    ones = [grid[bar["first_beat"]] for bar in layout]
    phase = layout[0]["first_beat"] % 4
    bpm_from, bpm_to = spec["bpm"]
    truth = {
        "name": name,
        "rate": RATE,
        "bpm": bpm_from if bpm_from == bpm_to else None,
        "bpm_from": bpm_from,
        "bpm_to": bpm_to,
        "beats": [round(t, 6) for t in grid],
        "pickup_beats": PICKUP_BEATS,
        "first_one_beat": layout[0]["first_beat"],
        "downbeat_slot": phase,
        "ones": [round(t, 6) for t in ones],
        "bars": layout,
        "stems": {"drums": "drums.wav", "band": "band.wav", "mix": "mix.wav"},
        "expect": _expectations(name, layout, phase),
    }
    return stems, truth


def _expectations(name: str, layout: list[dict], phase: int) -> dict:
    expect = {"slot_tolerance_beats": 0, "beat_tolerance_s": 0.010}
    if name == "decoy-kick-on-two":
        expect["low_band_strongest_count"] = 1
        expect["note"] = "the loudest kick is on beat 2; a low-band method picks it, the bar-one method must not"
    if name == "drift-108-114":
        expect["beat_tolerance_s"] = 0.020
    if name == "bar-of-two":
        short = next(i for i, bar in enumerate(layout) if bar["extent"] == 2)
        change = layout[short + 1]["first_beat"]
        expect["short_bar_index"] = short
        expect["phase_change_at_beat"] = change
        expect["slot_after"] = change % 4
        expect["note"] = "a stretch after the 2/4 bar prefers another phase; it must be reported, never re-phased silently"
    return expect


def write_synthetic(write_to, names=None) -> list[Path]:
    write_to = Path(write_to)
    written = []
    for name in names or SYNTHETIC:
        stems, truth = build_synthetic(name)
        folder = write_to / name
        folder.mkdir(parents=True, exist_ok=True)
        for stem, data in stems.items():
            save_wav(folder / truth["stems"][stem], data, RATE)
        (folder / "truth.json").write_text(json.dumps(stamped("fixture-truth", truth), indent=1) + "\n", encoding="utf-8")
        written.append(folder)
    return written


# ---- first-film pack -----------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_first_film(src, dst) -> dict:
    """Copy the named files from the first film into dst, with manifest and truth note."""
    src, dst = Path(src), Path(dst)
    missing = [rel for rel in FIRST_FILM_FILES if not (src / rel).is_file()]
    if missing:
        raise FileNotFoundError(f"missing in {src}: {', '.join(missing)}")
    files = []
    for rel in FIRST_FILM_FILES:
        aim = dst / rel
        aim.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / rel, aim)
        files.append({"path": rel, "bytes": aim.stat().st_size, "sha256": _sha256(aim)})
    manifest = {
        "film": "The Girl In The Magic Tub",
        "provenance": str(src).replace("\\", "/"),
        "files": files,
        "truth": FIRST_FILM_TRUTH,
    }
    (dst / "TRUTH.txt").write_text(TRUTH_NOTE, encoding="utf-8")
    manifest = stamped("fixture-manifest", manifest)
    (dst / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


# ---- command line --------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="what", required=True)
    syn = sub.add_parser("synthetic", help="write the synthetic beat and bar fixtures")
    syn.add_argument("--out", default=str(REPO / "fixtures" / "synthetic"))
    film = sub.add_parser("first-film", help="copy the first film's stems and timing files")
    film.add_argument("--src", help=f"the first film's folder (default: films/{FIRST_FILM_SLUG} under ${FIRST_FILM_ENV})")
    film.add_argument("--out", default=str(REPO / "fixtures" / "first-film"))
    args = parser.parse_args(argv)
    if args.what == "synthetic":
        for folder in write_synthetic(args.out):
            print(folder)
        return 0
    src = args.src or first_film_src()
    if src is None:
        print(f"error: give --src or set {FIRST_FILM_ENV} (docs/first-film-replay.md)", file=sys.stderr)
        return 1
    try:
        manifest = extract_first_film(src, args.out)
    except FileNotFoundError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    total = sum(item["bytes"] for item in manifest["files"])
    print(f"{len(manifest['files'])} files, {total / 1e6:.1f} MB -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
