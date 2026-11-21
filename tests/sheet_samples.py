"""A character's reference sheet for tests: one small tall PNG per view, the figure filling it on a plain backdrop.

`write_sheet` writes every required view under refs/ and returns the `views` mapping a film.json carries. `busy=True`
paints noise over the whole picture instead, an environment the plain-background screen must refuse; `wide=True`
makes the pictures landscape strips with the figure small in the middle, as the first masters of a film were.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from atomic_flix.cast import required_views
from atomic_flix.scenes.imageio import write_png


def view_path(name: str, view: str) -> str:
    return f"refs/{name.lower()}-{view.replace('_', '-')}.png"


def picture(busy: bool = False, wide: bool = False) -> np.ndarray:
    if busy:
        return np.random.default_rng(1).integers(0, 255, (144, 96, 3), dtype=np.uint8)
    if wide:
        flat = np.full((96, 160, 3), 128, np.uint8)
        flat[4:92, 74:86] = (200, 90, 90)
        return flat
    flat = np.full((144, 96, 3), 128, np.uint8)
    flat[4:140, 36:60] = (200, 90, 90)                  # the figure: nearly the whole height, away from the sides
    return flat


def write_sheet(root: Path, name: str, busy: bool = False, wide: bool = False) -> dict[str, str]:
    views = {}
    for view in required_views():
        path = view_path(name, view)
        (Path(root) / path).parent.mkdir(parents=True, exist_ok=True)
        write_png(Path(root) / path, picture(busy, wide))
        views[view] = path
    return views
