"""Generated clips for the cut tests: colour fields with a frame counter drawn in as blocks.

The counter is ten black or white blocks along the top edge, bit 0 on the left. Blocks survive compression, so a
decoded frame tells which take frame it came from.
"""

from __future__ import annotations

import numpy as np

from atomic_flix.cut.media import write_video
from atomic_flix.wav import save_wav

FPS = 24
WIDTH, HEIGHT = 192, 108
COUNTER_BITS = 10
BLOCK = WIDTH // (COUNTER_BITS + 2)
BLOCK_ROWS = 16


def counter_frames(count: int, colour: tuple[int, int, int], width: int = WIDTH, height: int = HEIGHT) -> np.ndarray:
    frames = np.empty((count, height, width, 3), np.uint8)
    frames[:] = np.array(colour, np.uint8)
    block = width // (COUNTER_BITS + 2)
    for number in range(count):
        for bit in range(COUNTER_BITS):
            left = (bit + 1) * block
            frames[number, :BLOCK_ROWS, left:left + block] = 255 if (number >> bit) & 1 else 0
    return frames


def read_counter(frame: np.ndarray) -> int:
    """Decode the counter from one RGB or grey frame of the clip's own size."""
    grey = frame.mean(axis=2) if frame.ndim == 3 else frame
    block = grey.shape[1] // (COUNTER_BITS + 2)
    value = 0
    for bit in range(COUNTER_BITS):
        left = (bit + 1) * block
        patch = grey[4:BLOCK_ROWS - 4, left + 4:left + block - 4]
        if patch.mean() > 128:
            value |= 1 << bit
    return value


def make_take(path, count: int = 96, colour=(200, 40, 40), fps: int = FPS, width: int = WIDTH, height: int = HEIGHT):
    return write_video(path, counter_frames(count, colour, width, height), fps, crf=10)


def make_tone(path, seconds: float = 4.0, amplitude: float = 0.05, rate: int = 48000, freq: float = 440.0):
    t = np.arange(int(round(seconds * rate))) / rate
    mono = amplitude * np.sin(2 * np.pi * freq * t)
    return save_wav(path, np.stack([mono, mono], axis=1), rate)


def flashing_frames(seconds: float, toggles_per_second: float, area: float = 1.0, size=(96, 54),
                    fps: int = FPS) -> np.ndarray:
    """Black and white alternating `toggles_per_second` times a second over a centred square of `area`."""
    width, height = size
    count = int(round(seconds * fps))
    frames = np.zeros((count, height, width, 3), np.uint8)
    side_w = int(round(width * np.sqrt(area)))
    side_h = int(round(height * np.sqrt(area)))
    top, left = (height - side_h) // 2, (width - side_w) // 2
    for number in range(count):
        if int(np.floor(number * toggles_per_second / fps)) % 2 == 0:
            frames[number, top:top + side_h, left:left + side_w] = 255
    return frames
