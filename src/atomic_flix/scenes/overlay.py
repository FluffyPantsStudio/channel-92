"""Does a still follow its Blender first frame? The two pictures' lines, laid over each other.

A shot staged in Blender gets its first frame from an image model, with the Blender frame as the layout. An edit model
that "recomposes" (zooms out, recentres, moves a wall) breaks that, and the video model then animates the wrong layout
faithfully. The check takes the edges of the Blender frame (the layout) and measures how many of them the still has
within a few pixels (the still is scaled to cover the Blender frame's shape). Recall, not a symmetric score: a redrawn
still has more lines than a grey blockout, but every line of the blockout should still be there. A screen, not a
measurement of quality: the threshold is a first guess that wants calibrating on real frames.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..cast import sampled_rgb
from .guides import canny, resize_cover

SIDE = 256               # the pictures are compared at this many pixels on the Blender frame's long side
REACH = 5                # pixels: a blockout line within this of a line in the still counts as found
OVERLAY_MIN = 0.6        # the share of the blockout's lines the still must have: below it the layout was recomposed


def _dilate(mask: np.ndarray, reach: int) -> np.ndarray:
    height, width = mask.shape
    padded = np.pad(mask, reach)
    out = np.zeros_like(mask)
    for dy in range(2 * reach + 1):
        for dx in range(2 * reach + 1):
            out |= padded[dy:dy + height, dx:dx + width]
    return out


def edge_match(still: str | Path, blender_frame: str | Path) -> float:
    """The share (0 to 1) of the Blender frame's edge pixels that the still has an edge near. Raises ValueError,
    naming the file, for a picture that cannot be read; a blockout with no edges at all is 1.0 (nothing to follow)."""
    frame = sampled_rgb(Path(blender_frame))
    height, width = frame.shape[:2]
    scale = SIDE / max(height, width)
    size = (max(8, round(width * scale)), max(8, round(height * scale)))
    wanted = canny(resize_cover(frame, *size)) > 0
    if not wanted.any():
        return 1.0
    found = _dilate(canny(resize_cover(sampled_rgb(Path(still)), *size)) > 0, REACH)
    return float((wanted & found).sum() / wanted.sum())
