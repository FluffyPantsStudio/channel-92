"""Photosensitivity: count flashes the way WCAG 2.3.1 defines its general flash threshold.

Decoding runs at 24 fps and 96x54 pixels; brightness per pixel is relative luminance computed in linear light.
Comparing neighbouring frames, a pixel counts toward a transition if its value moves by 0.10 or more while the
dimmer of the pair stays below 0.8. When a quarter of the picture (25 %) or more moves the same way, that frame pair
is one transition. Consecutive transitions of one sign fuse into one; two of opposite sign make a flash. A one-second
window holding over three flashes is a failure, and every failing stretch is listed with its times.

Saturated red changes (WCAG's red flash rule) are outside this measure: judge those by eye.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .media import read_frames

FLASH_FPS = 24
FLASH_SIZE = (96, 54)
MIN_CHANGE = 0.10
DARK_SIDE_LIMIT = 0.8
MIN_AREA = 0.25
MAX_FLASHES_PER_SECOND = 3
WINDOW_SECONDS = 1.0
RED_NOTE = "The red flash rule is not checked: look at any saturated red flashing by eye."


@dataclass
class FlashReport:
    passed: bool
    flash_count: int
    worst_count: int
    worst_at: float | None
    flashes: list[tuple[float, float]] = field(default_factory=list)
    failing: list[tuple[float, float]] = field(default_factory=list)
    note: str = RED_NOTE

    def to_dict(self) -> dict:
        return {"passed": self.passed, "flash_count": self.flash_count, "worst_count": self.worst_count,
                "worst_at": self.worst_at, "limit_per_second": MAX_FLASHES_PER_SECOND,
                "flashes": [[round(a, 3), round(b, 3)] for a, b in self.flashes],
                "failing": [[round(a, 3), round(b, 3)] for a, b in self.failing], "note": self.note}

    def text(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        lines = [f"flash check {verdict}: {self.flash_count} flashes, at most {self.worst_count} in one second "
                 f"(limit {MAX_FLASHES_PER_SECOND})"]
        lines += [f"  over the limit from {a:.2f} s to {b:.2f} s" for a, b in self.failing]
        lines.append(self.note)
        return "\n".join(lines)


def relative_luminance(rgb: np.ndarray) -> np.ndarray:
    """Relative luminance (0 to 1) of 8-bit sRGB pixels."""
    value = rgb.astype(np.float64) / 255.0
    lin = np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)
    return lin[..., 0] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 2] * 0.0722


def count_transitions(luminance: np.ndarray) -> list[tuple[int, int]]:
    """(frame index, direction) of each merged transition; +1 brighter, -1 darker."""
    marks: list[tuple[int, int]] = []
    for index in range(1, len(luminance)):
        before, after = luminance[index - 1], luminance[index]
        change = after - before
        counts = (np.abs(change) >= MIN_CHANGE) & (np.minimum(before, after) < DARK_SIDE_LIMIT)
        brighter = np.count_nonzero(counts & (change > 0)) / change.size
        darker = np.count_nonzero(counts & (change < 0)) / change.size
        if max(brighter, darker) < MIN_AREA:
            continue
        direction = 1 if brighter >= darker else -1
        if marks and marks[-1][1] == direction:
            continue
        marks.append((index, direction))
    return marks


def pair_flashes(marks: list[tuple[int, int]], fps: float) -> list[tuple[float, float]]:
    """Consecutive opposite transitions, paired without overlap, as (start, end) seconds."""
    return [(marks[i][0] / fps, marks[i + 1][0] / fps) for i in range(0, len(marks) - 1, 2)]


def _windows(flashes: list[tuple[float, float]]) -> tuple[int, float | None, list[tuple[float, float]]]:
    starts = [start for start, _ in flashes]
    worst, worst_at, failing = 0, None, []
    for position, start in enumerate(starts):
        inside = [s for s in starts[position:] if s < start + WINDOW_SECONDS]
        if len(inside) > worst:
            worst, worst_at = len(inside), start
        if len(inside) > MAX_FLASHES_PER_SECOND:
            span = (start, start + WINDOW_SECONDS)
            if failing and span[0] <= failing[-1][1]:
                failing[-1] = (failing[-1][0], span[1])
            else:
                failing.append(span)
    return worst, worst_at, failing


def check_luminance(luminance: np.ndarray, fps: float = FLASH_FPS) -> FlashReport:
    flashes = pair_flashes(count_transitions(luminance), fps)
    worst, worst_at, failing = _windows(flashes)
    return FlashReport(passed=not failing, flash_count=len(flashes), worst_count=worst, worst_at=worst_at,
                       flashes=flashes, failing=failing)


def check_flashes(path) -> FlashReport:
    """Run the flash check on a clip (the graded film)."""
    frames = read_frames(path, size=FLASH_SIZE, fps=FLASH_FPS)
    return check_luminance(relative_luminance(frames), FLASH_FPS)
