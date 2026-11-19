"""Synthetic shots for the grade tests: textured greys and colours at chosen levels, joined into one clip."""

from __future__ import annotations

import numpy as np

from atomic_flix.cut.media import write_video

FPS = 24
WIDTH, HEIGHT = 192, 108


def ramp_shot(seconds: float, low: float, high: float, colour=(1.0, 1.0, 1.0), seed: int = 1) -> np.ndarray:
    """A noisy ramp from `low` to `high` (0 to 1) across the picture, tinted by `colour` (RGB gains)."""
    rng = np.random.default_rng(seed)
    count = int(round(seconds * FPS))
    ramp = np.linspace(low, high, WIDTH)[None, :].repeat(HEIGHT, axis=0)
    ramp = np.clip(ramp + rng.normal(0, 0.01, ramp.shape), 0, 1)
    picture = np.stack([ramp * gain for gain in colour], axis=-1)
    frame = np.clip(picture * 255 + 0.5, 0, 255).astype(np.uint8)
    return np.repeat(frame[None], count, axis=0)


def write_shots(path, shots: list[np.ndarray]):
    """Join shots into one clip; returns (path, [(first_frame, end_frame)])."""
    spans, at = [], 0
    for shot in shots:
        spans.append((at, at + len(shot)))
        at += len(shot)
    write_video(path, np.concatenate(shots), FPS, crf=8)
    return path, spans
