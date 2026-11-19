"""Synthetic clips for the review tests: a smooth noise texture that can pan, freeze, or carry a busy 'mouth' box."""

from __future__ import annotations

import numpy as np

from atomic_flix.cut.media import write_video

FPS = 24
WIDTH, HEIGHT = 320, 180


def texture(width: int, height: int, seed: int = 1) -> np.ndarray:
    """Smooth random greys (box-blurred noise), so a shift is visible at reduced size."""
    rng = np.random.default_rng(seed)
    noise = rng.random((height, width))
    for axis in (0, 1):
        kernel = 7
        padded = np.cumsum(np.pad(noise, [(kernel, 0) if a == axis else (0, 0) for a in (0, 1)], mode="edge"),
                           axis=axis)
        noise = (np.take(padded, range(kernel, padded.shape[axis]), axis=axis)
                 - np.take(padded, range(0, padded.shape[axis] - kernel), axis=axis)) / kernel
    noise = (noise - noise.min()) / (noise.max() - noise.min())
    return (40 + 180 * noise).astype(np.uint8)


def grey_to_rgb(frames: np.ndarray) -> np.ndarray:
    return np.repeat(frames[..., None], 3, axis=-1)


def panning(seconds: float, pixels_per_frame: float, still_after: float | None = None) -> np.ndarray:
    """A window sliding right over a wide texture (content moves left); frozen from `still_after` seconds."""
    count = int(round(seconds * FPS))
    wide = texture(WIDTH + int(abs(pixels_per_frame) * count) + 4, HEIGHT)
    frames = []
    for number in range(count):
        moving = number if still_after is None else min(number, int(round(still_after * FPS)))
        left = int(round(moving * pixels_per_frame))
        frames.append(wide[:, left:left + WIDTH])
    return grey_to_rgb(np.stack(frames))


def busy_box(seconds: float, box: tuple[float, float, float, float], busy: list[tuple[float, float]],
             seed: int = 3) -> np.ndarray:
    """A still texture with a box that changes every frame inside the `busy` stretches and holds still otherwise."""
    count = int(round(seconds * FPS))
    base = texture(WIDTH, HEIGHT)
    x, y, w, h = (int(round(box[0] * WIDTH)), int(round(box[1] * HEIGHT)), int(round(box[2] * WIDTH)),
                  int(round(box[3] * HEIGHT)))
    rng = np.random.default_rng(seed)
    frames = np.repeat(base[None], count, axis=0).copy()
    patch = base[y:y + h, x:x + w].copy()
    for number in range(count):
        t = number / FPS
        if any(a <= t < b for a, b in busy):
            patch = (rng.random((h, w)) * 255).astype(np.uint8)
        frames[number, y:y + h, x:x + w] = patch
    return grey_to_rgb(frames)


def save(path, frames: np.ndarray) -> object:
    return write_video(path, frames, FPS, crf=12, x264_speed="veryfast")
