"""What the grade does to each shot, and the one look laid over the whole film.

Per shot, toward the film's own levels (the median over its shots of black, white and colour strength):
- black and white each move PULL of the way there, never more than MAX_LEVEL_MOVE (a dark scene stays dark);
  a shot whose white sits less than MIN_RANGE above its black is flat on purpose (fog, a night sky) and keeps them;
- colour strength moves the same share of the way, as a gain on chroma held inside COLOUR_GAIN.
Levels act on luma only and the gain scales chroma about grey, so a shot's hue and colour balance never change:
each world keeps its palette.

The look, one for the whole film (`Look`): a soft S-bend on luma between a lifted black and a lowered white, a little
teal in the shadows and warmth in the lights. It never adds grain or noise: masters stay clean, grain is a post step.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from .measure import CHROMA_CENTRE, CHROMA_SPAN, LUMA_FLOOR, LUMA_SPAN, Levels

PULL = 0.7
MAX_LEVEL_MOVE = 0.08
COLOUR_GAIN = (0.85, 1.2)
MIN_RANGE = 0.25
FAINT_COLOUR = 0.005
LUMA_LEGAL = (16, 235)
CHROMA_LEGAL = (16, 240)
FORBIDDEN_LOOK_KEYS = ("grain", "noise", "film_grain")


@dataclass(frozen=True)
class Look:
    """The film's look. Luma: out = lift + (ceiling - lift) * bent(in), bent(y) = y + bend * y (1 - y) (2y - 1).
    Tints are (u, v) chroma offsets, full in the deepest shadow and the brightest light, fading to none at mid grey."""

    lift: float = 0.02
    ceiling: float = 0.985
    bend: float = 0.16
    shadow_tint: tuple[float, float] = (0.012, -0.010)
    light_tint: tuple[float, float] = (-0.010, 0.010)

    @classmethod
    def from_file(cls, path: Path | str) -> "Look":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        bad = [key for key in data if key in FORBIDDEN_LOOK_KEYS]
        if bad:
            raise ValueError(f"{path}: a look may not add {', '.join(bad)}: no grain in masters, it is a post step")
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            known = sorted(cls.__dataclass_fields__)
            raise ValueError(f"{path}: unknown look fields {sorted(unknown)}; known: {known}")
        values = {key: tuple(value) if isinstance(value, list) else value for key, value in data.items()}
        look = cls(**values)
        if not 0 <= look.lift < look.ceiling <= 1:
            raise ValueError(f"{path}: lift and ceiling must satisfy 0 <= lift < ceiling <= 1")
        return look

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_LOOK = Look()
NEUTRAL_LOOK = Look(lift=0.0, ceiling=1.0, bend=0.0, shadow_tint=(0, 0), light_tint=(0, 0))


@dataclass(frozen=True)
class Correction:
    key: str
    black: float
    white: float
    colour: float
    new_black: float
    new_white: float
    gain: float
    flat: bool = False

    def to_dict(self) -> dict:
        return {"key": self.key, "black": round(self.black, 4), "white": round(self.white, 4),
                "colour": round(self.colour, 4), "new_black": round(self.new_black, 4),
                "new_white": round(self.new_white, 4), "gain": round(self.gain, 4), "flat": self.flat}


IDENTITY = Correction("-", 0.0, 1.0, 0.0, 0.0, 1.0, 1.0)


def _toward(value: float, aim: float) -> float:
    move = PULL * (aim - value)
    return value + max(-MAX_LEVEL_MOVE, min(MAX_LEVEL_MOVE, move))


def plan_corrections(levels: Sequence[Levels]) -> list[Correction]:
    if not levels:
        return []
    middle = {name: statistics.median(getattr(item, name) for item in levels) for name in ("black", "white", "colour")}
    plan = []
    for item in levels:
        flat = item.white - item.black < MIN_RANGE
        new_black = item.black if flat else max(0.0, _toward(item.black, middle["black"]))
        new_white = item.white if flat else min(1.0, _toward(item.white, middle["white"]))
        if item.colour > FAINT_COLOUR:
            wanted = item.colour + PULL * (middle["colour"] - item.colour)
            gain = min(COLOUR_GAIN[1], max(COLOUR_GAIN[0], wanted / item.colour))
        else:
            gain = COLOUR_GAIN[1] if middle["colour"] > item.colour else 1.0
        plan.append(Correction(item.key, item.black, item.white, item.colour, new_black, new_white, gain, flat))
    return plan


def _bent(y: np.ndarray, look: Look) -> np.ndarray:
    y = np.clip(y, 0.0, 1.0)
    return look.lift + (look.ceiling - look.lift) * (y + look.bend * y * (1 - y) * (2 * y - 1))


def _graded_luma(correction: Correction, look: Look) -> np.ndarray:
    """Graded luma (video scale, 0 to 1) for each of the 256 input codes."""
    y = (np.arange(256) - LUMA_FLOOR) / LUMA_SPAN
    span = correction.white - correction.black
    if span > 1e-6:
        y = correction.new_black + (y - correction.black) * (correction.new_white - correction.new_black) / span
    return _bent(y, look)


def luma_table(correction: Correction, look: Look) -> np.ndarray:
    """Output luma code for each input luma code."""
    codes = np.round(LUMA_FLOOR + LUMA_SPAN * _graded_luma(correction, look))
    return np.clip(codes, *LUMA_LEGAL).astype(np.uint8)


def tint_tables(look: Look) -> tuple[np.ndarray, np.ndarray]:
    """(u, v) chroma offsets in codes for each OUTPUT luma code."""
    y = np.clip((np.arange(256) - LUMA_FLOOR) / LUMA_SPAN, 0.0, 1.0)
    shadow = np.clip(1 - y / 0.5, 0, 1) ** 2
    light = np.clip((y - 0.5) / 0.5, 0, 1) ** 2
    u = CHROMA_SPAN * (look.shadow_tint[0] * shadow + look.light_tint[0] * light)
    v = CHROMA_SPAN * (look.shadow_tint[1] * shadow + look.light_tint[1] * light)
    return u, v


def grade_planes(y: np.ndarray, u: np.ndarray, v: np.ndarray, table: np.ndarray, gain: float,
                 tints: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One yuv420p frame: luma through the shot's table, chroma scaled about grey and tinted by the graded luma."""
    out_y = table[y]
    height, width = u.shape
    luma_here = out_y[:2 * height, :2 * width].reshape(height, 2, width, 2).mean(axis=(1, 3))
    index = np.clip(np.round(luma_here), 0, 255).astype(np.intp)
    planes = []
    for chroma, tint in zip((u, v), tints):
        value = CHROMA_CENTRE + gain * (chroma.astype(np.float32) - CHROMA_CENTRE) + tint[index]
        planes.append(np.clip(np.round(value), *CHROMA_LEGAL).astype(np.uint8))
    return out_y, planes[0], planes[1]
