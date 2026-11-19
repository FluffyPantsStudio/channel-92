"""Reading a shot's levels from the cut: where its darks sit, where its lights sit, and how strong its colour is.

Frames are decoded small (SAMPLE_SIZE) in YUV, the cut's own colour space, so no colour matrix stands between the
measure and the correction. Luma is read on the video scale (code 16 is 0, code 235 is 1); chroma as offsets from
grey (code 128 is 0, 224 codes are 1). Per frame: black is the BLACK_PERCENTILE of luma, white the WHITE_PERCENTILE,
colour the mean length of the (u, v) chroma vector, hue the angle of the mean chroma vector. A shot's value is the
median over its sampled frames: SAMPLES_PER_SECOND instants a second, leaving EDGE_S out at each end.
"""

from __future__ import annotations

import math
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from ..cut.media import ERROR_TAIL, ENCODER_EXE, SCALE_FLAGS, MediaError

SAMPLE_SIZE = (160, 90)
SAMPLES_PER_SECOND = 2
EDGE_S = 0.25
BLACK_PERCENTILE = 2
WHITE_PERCENTILE = 98
LUMA_FLOOR, LUMA_SPAN = 16.0, 219.0
CHROMA_CENTRE, CHROMA_SPAN = 128.0, 224.0
MEASURES = ("black", "white", "colour")


@dataclass(frozen=True)
class ShotSpan:
    """One shot of the cut, in the cut's own frames: [frame_in, end_frame)."""

    key: str
    frame_in: int
    end_frame: int


@dataclass(frozen=True)
class Levels:
    key: str
    black: float
    white: float
    colour: float
    hue: float = 0.0

    def to_dict(self) -> dict:
        return {"key": self.key, "black": round(self.black, 4), "white": round(self.white, 4),
                "colour": round(self.colour, 4), "hue": round(self.hue, 4)}


def sample_frames(shot: ShotSpan, fps: float) -> list[int]:
    """Frames of the cut to measure a shot on: SAMPLES_PER_SECOND a second, EDGE_S kept clear of each end."""
    start, end = shot.frame_in / fps, shot.end_frame / fps
    step = 1.0 / SAMPLES_PER_SECOND
    instants = [k * step for k in range(math.ceil(start / step - 1e-9), math.floor(end / step) + 1)]
    inside = [t for t in instants if start + EDGE_S - 1e-9 <= t <= end - EDGE_S + 1e-9]
    picked = inside or [t for t in instants if start <= t < end]
    frames = sorted({min(shot.end_frame - 1, max(shot.frame_in, int(round(t * fps)))) for t in picked})
    return frames or [(shot.frame_in + shot.end_frame - 1) // 2]


def small_frames(film: Path | str, wanted: Iterable[int], size=SAMPLE_SIZE) -> dict[int, np.ndarray]:
    """The wanted frames of a clip at `size`, as float arrays (3, h, w): luma, u, v on the scales above."""
    keep = set(int(i) for i in wanted)
    width, height = size
    plane = width * height
    command = [ENCODER_EXE, "-v", "error", "-nostdin", "-i", str(film), "-vf", f"scale={width}:{height}:flags={SCALE_FLAGS}",
               "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "yuv444p", "-"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    found: dict[int, np.ndarray] = {}
    index = 0
    last = max(keep) if keep else -1
    try:
        while index <= last:
            raw = process.stdout.read(plane * 3)
            if len(raw) < plane * 3:
                break
            if index in keep:
                planes = np.frombuffer(raw, np.uint8).reshape(3, height, width).astype(np.float64)
                found[index] = np.stack([(planes[0] - LUMA_FLOOR) / LUMA_SPAN,
                                         (planes[1] - CHROMA_CENTRE) / CHROMA_SPAN,
                                         (planes[2] - CHROMA_CENTRE) / CHROMA_SPAN])
            index += 1
    finally:
        process.stdout.close()
        error = process.stderr.read().decode(errors="replace")
        process.stderr.close()
        process.wait()
    if not found and keep:
        raise MediaError(f"ffmpeg could not read {film}: {error[-ERROR_TAIL:]}")
    return found


def frame_levels(picture: np.ndarray) -> tuple[float, float, float, float]:
    """(black, white, colour, hue) of one small frame (3, h, w)."""
    luma, u, v = picture
    black, white = np.percentile(luma, [BLACK_PERCENTILE, WHITE_PERCENTILE])
    colour = float(np.hypot(u, v).mean())
    hue = math.atan2(float(v.mean()), float(u.mean()))
    return float(black), float(white), colour, hue


def measure_shots(film: Path | str, shots: Sequence[ShotSpan], fps: float) -> list[Levels]:
    """Each shot's levels: the median of its sampled frames."""
    wanted = {shot.key: sample_frames(shot, fps) for shot in shots}
    pictures = small_frames(film, {f for frames in wanted.values() for f in frames})
    measured = []
    for shot in shots:
        rows = [frame_levels(pictures[f]) for f in wanted[shot.key] if f in pictures]
        if not rows:
            raise MediaError(f"{Path(film).name} ends before shot {shot.key} (frames {shot.frame_in} to "
                             f"{shot.end_frame}): is this the cut of this edit?")
        black, white, colour, hue = (statistics.median(column) for column in zip(*rows))
        measured.append(Levels(shot.key, black, white, colour, hue))
    return measured


def spread(levels: Sequence) -> dict:
    """The spread across shots (population standard deviation) of black, white and colour strength."""
    return {name: round(statistics.pstdev(getattr(item, name) for item in levels), 4) if levels else 0.0
            for name in MEASURES}
