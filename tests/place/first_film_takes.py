"""Placing the first film's sung takes on its lead vocal, read-only.

The takes are LTX-2.3 renders that heard a gated window of the lead vocal (some a soft copy); their own soundtrack is
that audio, re-encoded by the model. The windows' times are not in our fixture, so each take is first found in the
whole lead stem by sound (a correlation of feature frames over the take's voiced frames), then the stretch of lead it
lines up with is used as the sent audio, silenced outside the span the take sounds in (as the real gate was), and the
take's voiced stretches as the phrases. The lead here is not compressed, which the level-proof features allow for.

Run directly for numbers on every take:  python tests/place/first_film_takes.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from atomic_flix.place.features import FEATURE_RATE, HOP_S, N_BANDS, resample, sound_features
from atomic_flix.place.fit import fit_by_sound, voiced_phrases
from atomic_flix.wav import read_wav
from first_film_env import film_folder

REPO = Path(__file__).resolve().parents[2]
FILM = film_folder()
TAKES = FILM / "takes" if FILM is not None else None
LEAD = REPO / "fixtures" / "first-film" / "audio" / "lead.wav"
TAKE_NAME = re.compile(r"take-([0-9]+)\.mp4")
GATE_BEFORE_S = 0.07
GATE_AFTER_S = 0.25


def available() -> bool:
    return TAKES is not None and TAKES.is_dir() and LEAD.is_file() and shutil.which("ffmpeg") is not None


def sung_takes(latest_only: bool = False) -> list[Path]:
    """Sung shots' takes made on an LTX graph that heard the vocal, in shot and take order."""
    found = []
    for shot in sorted(p for p in TAKES.iterdir() if p.is_dir() and p.name.startswith("S")):
        takes = []
        for video in shot.glob("take-*.mp4"):
            match = TAKE_NAME.fullmatch(video.name)
            record = video.with_suffix(".json")
            if not match or not record.is_file():
                continue
            graph = json.loads(record.read_text(encoding="utf-8")).get("workflow", "")
            if "sung-ltx" in graph:
                takes.append((int(match.group(1)), video))
        takes.sort()
        found.extend([takes[-1][1]] if latest_only and takes else [video for _, video in takes])
    return found


def decode(video: Path) -> np.ndarray:
    """The video's soundtrack, mono at 16 kHz, through ffmpeg."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(FEATURE_RATE),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


@dataclass(frozen=True)
class Song:
    lead: np.ndarray
    features: np.ndarray
    spectra: np.ndarray
    size: int

    @classmethod
    def load(cls, path: Path = LEAD) -> "Song":
        samples, rate = read_wav(path)
        lead = resample(samples, rate, FEATURE_RATE)
        features = sound_features(lead, FEATURE_RATE)[:, :N_BANDS]
        size = 1 << int(np.ceil(np.log2(len(features) + 4096)))
        return cls(lead, features, np.fft.rfft(features, size, axis=0), size)

    def locate(self, clip: np.ndarray) -> float:
        """Where in the song the render's sound starts (seconds), by its voiced frames."""
        frames = sound_features(clip, FEATURE_RATE)
        vocal_on = frames[:, N_BANDS] == 0
        weights = frames[:, :N_BANDS] * vocal_on[:, None]
        spectrum = np.fft.rfft(weights, self.size, axis=0)
        score = np.fft.irfft(self.spectra * np.conj(spectrum), self.size, axis=0).sum(axis=1)
        last = len(self.features) - len(frames)
        return int(np.argmax(score[:max(1, last)])) * HOP_S


def place_take(song: Song, video: Path) -> dict:
    clip = decode(video)
    start = song.locate(clip)
    first = int(round(start * FEATURE_RATE))
    sent = song.lead[first:first + len(clip)].copy()
    vocal_spans = voiced_phrases(clip, FEATURE_RATE)
    if vocal_spans:
        # the render heard a gated window: silence the lead outside the span the take itself sounds in
        times = np.arange(len(sent)) / FEATURE_RATE
        sent[(times < vocal_spans[0][0] - GATE_BEFORE_S) | (times > vocal_spans[-1][1] + GATE_AFTER_S)] = 0.0
    fit = fit_by_sound(sent, FEATURE_RATE, clip, FEATURE_RATE, vocal_spans=vocal_spans, slice_start=start)
    costs = [p["cost"] for p in fit["vocal_spans"]]
    return {"take": f"{video.parent.name}/{video.stem}", "slice_start": round(start, 2), "costs": costs,
            "worst": max(costs) if costs else None, "offset": fit["offset"], "fit": fit}


def main() -> int:
    if not available():
        print("the first film's takes, lead stem or ffmpeg are not on this machine")
        return 1
    song = Song.load()
    results = []
    for video in sung_takes(latest_only="--latest" in sys.argv):
        try:
            results.append(place_take(song, video))
        except subprocess.CalledProcessError as err:
            print(f"{video}: ffmpeg failed: {err.stderr[:200]!r}")
    worst = np.array([r["worst"] for r in results if r["worst"] is not None])
    offsets = np.array([r["offset"] for r in results if r["offset"] is not None])
    print(f"{len(results)} takes, {sum(len(r['costs']) for r in results)} phrases")
    for limit in (0.05, 0.09, 0.2, 0.45):
        print(f"  worst phrase <= {limit}: {np.sum(worst <= limit)} of {len(worst)}")
    print(f"  worst phrase cost: median {np.median(worst):.3f}, 95th {np.percentile(worst, 95):.3f}, "
          f"max {worst.max():.3f}")
    print(f"  offset after locating: median {np.median(offsets):+.3f} s, range {offsets.min():+.3f} to "
          f"{offsets.max():+.3f}")
    for row in sorted(results, key=lambda r: -(r["worst"] or 0))[:12]:
        print(f"  {row['take']}: worst {row['worst']}, phrases {row['costs']}, at {row['slice_start']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
