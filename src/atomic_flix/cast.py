"""The film's cast and their reference sheets.

A character is a person the pictures must keep the same: the star (`film.json` `star`) and every entry of
`characters`. Each one has a sheet of views (`data/rules/character-views.txt`: front, three-quarter, profile, back),
one picture per view, the whole figure on a plain background with no environment: a model that has seen one picture
only draws every angle from it, and a picture with a street behind it carries the street into every shot. A sheet is
written in film.json as `views: {"front": "refs/frankie-front.png", ...}`.

`measure_view` checks the environment-free rule on the picture itself, so it never rests on a prompt's wording. A
view is plain when its border is one flat colour (the figure alone, with a margin) and most of the whole picture is
that same colour (a street with a flat frame around it fails). It is measured on the colours a model is shown, so a
picture's transparency is ignored.
"""

from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .plan.vocab import terms
from .scenes.imageio import read_png

BAND = 0.12              # the band along the top and both sides that must be background, as a share of the size
EDGE_LEVEL = 8.0         # 0 to 255: the steepest change between neighbours (after a light blur) a smooth pixel has
RING_MIN = 0.7           # the share of that band that is smooth: a flat or softly lit backdrop. A coarse screen: it
                         # catches a busy place, not a flat-coloured wall (the judge and gate 3 look at that)
ASPECT_MIN = 1.2         # a view is a tall portrait cell: height at least this times its width
FILL_MIN = 0.8           # the figure covers at least this share of the picture's height
FIGURE_PIXELS = 3        # a picture row holds the figure when this many of its (sampled) pixels are edges
MEASURE_SIDE = 512       # a picture is sampled down to about this many pixels on its long side before measuring
CACHE_FILE = "cache/plain.json"
FIELDS = ("ring", "aspect", "figure")


def kind_of(view: str) -> str:
    """"body" for a full-length view (body_front, body_back...), else "bust" (head and shoulders, cut at the chest)."""
    return "body" if view.startswith("body_") else "bust"


@dataclass(frozen=True)
class Plainness:
    """What a view picture is like: how smooth the band along its top and sides is (a flat or softly lit studio
    backdrop is; a street, a room or any scenery is not), its height over its width, and how much of its height the
    figure covers. Measured on the picture, so it never rests on a prompt's wording."""

    ring: float
    aspect: float = 1.5
    figure: float = 1.0

    def environment(self) -> str | None:
        """Why the background is not plain (edges and texture behind the figure), or None."""
        if self.ring < RING_MIN:
            return (f"only {self.ring:.0%} of the band along its top and sides is smooth backdrop, {RING_MIN:.0%} is "
                    "the least: there is an environment behind the figure")
        return None

    def small(self) -> str | None:
        """Why the figure is too small in its picture, or None: a view is a tall cell the figure fills."""
        if self.aspect < ASPECT_MIN:
            return (f"is {1 / self.aspect:.2f} times as wide as it is tall; a view is a tall portrait picture "
                    f"(height at least {ASPECT_MIN:g} times its width) with the figure filling it")
        if self.figure < FILL_MIN:
            return f"the figure covers only {self.figure:.0%} of the picture's height, {FILL_MIN:.0%} is the least"
        return None

    def ok(self) -> bool:
        return self.environment() is None and self.small() is None


def as_plainness(value: Any) -> Plainness | str:
    """A measurement written by hand (a test case): a number is the smooth share of the band, an object names the
    fields, a string is the reason a picture could not be measured."""
    if isinstance(value, (str, Plainness)):
        return value
    if isinstance(value, dict):
        return Plainness(**{key: float(number) for key, number in value.items()})
    return Plainness(ring=float(value))


def required_views(rules_dir: Path | None = None) -> tuple[str, ...]:
    """The views a sheet holds, from the project's `rules/character-views.txt` or the kit's list."""
    return terms("character-views", rules_dir)


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def cast_of(film: Mapping) -> dict[str, dict]:
    """Every character of the film by name: the star first, then `characters`. Each entry is the film's own data; a
    star and a `characters` entry of one name are merged, their `views` together. Anything that is not an object is
    ignored here (lint and progress then say the sheet is missing)."""
    cast: dict[str, dict] = {}
    star = _dict(film.get("star"))
    if star.get("name"):
        cast[str(star["name"])] = dict(star)
    for name, data in _dict(film.get("characters")).items():
        merged = {**cast.get(str(name), {}), **_dict(data)}
        merged["views"] = {**_dict(cast.get(str(name), {}).get("views")), **_dict(_dict(data).get("views"))}
        cast[str(name)] = merged
    return cast


def views_of(person: Mapping) -> dict[str, str]:
    """The sheet as written: view name to picture path. A lone `identity` picture counts as the front view."""
    views = {str(name): str(path) for name, path in _dict(person.get("views")).items() if path}
    if "front" not in views and person.get("identity"):
        views["front"] = str(person["identity"])
    return views


def missing_views(person: Mapping, rules_dir: Path | None = None) -> list[str]:
    """The required views the person's sheet does not name."""
    have = views_of(person)
    return [view for view in required_views(rules_dir) if view not in have]


def _pixels(path: Path) -> np.ndarray:
    """The picture's colours as an (h, w, 3) uint8 array, sampled down to about MEASURE_SIDE on its long side."""
    try:
        from PIL import Image                     # optional: quick, and reads every kind of PNG
    except ImportError:
        Image = None
    if Image is not None:
        with Image.open(path) as picture:
            picture.draft("RGB", (MEASURE_SIDE, MEASURE_SIDE))
            rgb = picture.convert("RGB")
            rgb.thumbnail((MEASURE_SIDE, MEASURE_SIDE))
            return np.asarray(rgb)
    img = read_png(path)
    if img.ndim == 2:
        img = img[..., None]
    img = (img >> 8).astype(np.uint8) if img.dtype == np.uint16 else img
    step = max(1, max(img.shape[:2]) // MEASURE_SIDE)
    img = img[::step, ::step]
    return np.repeat(img[..., :1], 3, axis=2) if img.shape[2] < 3 else img[..., :3]


def _smooth(pixels: np.ndarray) -> np.ndarray:
    """True where the picture is smooth: no steep change between neighbours once it is lightly blurred."""
    colour = pixels.astype(np.float32)
    height, width = colour.shape[:2]
    padded = np.pad(colour, ((1, 1), (1, 1), (0, 0)), mode="edge")
    blurred = sum(padded[y:y + height, x:x + width] for y in range(3) for x in range(3)) / 9.0
    edge = np.pad(blurred, ((1, 1), (1, 1), (0, 0)), mode="edge")
    step_x = np.abs(edge[1:-1, 2:] - edge[1:-1, :-2]).max(axis=2)      # every channel: a red on a grey of the same
    step_y = np.abs(edge[2:, 1:-1] - edge[:-2, 1:-1]).max(axis=2)      # brightness is still an edge
    return np.maximum(step_x, step_y) <= EDGE_LEVEL


def plain_of(path: str | Path) -> Plainness:
    """Measure a picture. Raises ValueError, naming the file and the reason, for a file that cannot be read (corrupt,
    or a PNG kind the built-in reader does not take: save it as 8-bit RGB, not interlaced, not indexed)."""
    try:
        pixels = _pixels(Path(path))
    except (ValueError, OSError, zlib.error, struct.error, IndexError, KeyError) as problem:
        raise ValueError(f"{Path(path).name}: {problem}") from None
    height, width = pixels.shape[:2]
    smooth = _smooth(pixels)
    band_y, band_x = max(1, int(height * BAND)), max(1, int(width * BAND))
    ring = np.zeros((height, width), bool)
    ring[:band_y, :] = True
    ring[:, :band_x] = ring[:, -band_x:] = True
    rows = np.nonzero((~smooth).sum(axis=1) >= FIGURE_PIXELS)[0]
    figure = float((rows[-1] - rows[0] + 1) / height) if len(rows) else 0.0
    return Plainness(ring=float(smooth[ring].mean()), aspect=height / width, figure=figure)


def measure_view(root: Path, relative: str) -> Plainness:
    """`plain_of` for a view of the film, remembered in cache/plain.json by the file's size and time, so a sheet is
    read once, not on every `lint`. A cache that cannot be read or written is ignored."""
    path = Path(root) / relative
    stat = path.stat()
    key = [stat.st_mtime_ns, stat.st_size]
    cache_path = Path(root) / CACHE_FILE
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    row = cache.get(relative) if isinstance(cache, dict) else None
    if isinstance(row, dict) and row.get("key") == key and all(name in row for name in FIELDS):
        return Plainness(**{name: float(row[name]) for name in FIELDS})
    found = plain_of(path)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({**(cache if isinstance(cache, dict) else {}), relative: {
            "key": key, **{name: getattr(found, name) for name in FIELDS}}}), encoding="utf-8")
    except OSError:
        pass
    return found
