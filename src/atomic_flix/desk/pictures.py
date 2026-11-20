"""The packet's pictures, drawn with numpy and the review sheets' pixel font (no imaging library):
the song's timeline strip, the fixed zoom tiles of a still, and the board's contact sheets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..review.canvas import Tile, compose, text_image
from .strip import GAP_EDGE, LOW_PITCH, SCALE, SWATCH, TEXT_H, Label, StripPlan, clock, font_text, strip_plan

SCREEN_LONG_SIDE = 1600          # a still as a phone shows it
SHEET_LONG_SIDE = 2400           # a review or contact sheet, zoomed on the phone
TILE_OVERLAP = 0.08              # each zoom tile reaches this share of its size into its neighbours
STRIP_SIZE = (1600, 360)          # the width; the height grows with what the strip must hold
THUMB_WIDTH = 760
SHOTS_PER_SHEET = 6
SHEET_COLUMNS = 2
BACKGROUND = (22, 22, 26)
INK = (235, 235, 235)
DIM = (150, 150, 160)
KIND_COLOURS = {"sung": (232, 168, 56), "mixed": (196, 120, 176), "instrumental": (64, 76, 98)}
GAP_COLOUR = (90, 210, 225)


def fit_size(width: int, height: int, long_side: int) -> tuple[int, int]:
    """WIDTH x HEIGHT brought down (never up) so the long side is at most LONG_SIDE, both sides even."""
    scale = min(1.0, long_side / max(width, height))
    return max(2, int(round(width * scale / 2)) * 2), max(2, int(round(height * scale / 2)) * 2)


def _edges(length: int, parts: int) -> list[int]:
    return [int(round(index * length / parts)) for index in range(parts + 1)]


def tile_boxes(width: int, height: int) -> list[tuple[int, int, int, int]]:
    """Six fixed zoom tiles (left, top, right, bottom) that cover the whole picture at native pixels: three across
    and two down for a wide picture, two across and three down for a tall one, each reaching a little into its
    neighbours so nothing sits on a seam. Reading order, left to right, top to bottom."""
    columns, rows = (3, 2) if width >= height else (2, 3)
    if width < columns or height < rows:
        raise ValueError(f"a {width}x{height} picture is too small for zoom tiles")
    xs, ys = _edges(width, columns), _edges(height, rows)
    boxes = []
    for row in range(rows):
        for column in range(columns):
            pad_x = int(round((xs[column + 1] - xs[column]) * TILE_OVERLAP))
            pad_y = int(round((ys[row + 1] - ys[row]) * TILE_OVERLAP))
            boxes.append((max(0, xs[column] - pad_x), max(0, ys[row] - pad_y),
                          min(width, xs[column + 1] + pad_x), min(height, ys[row + 1] + pad_y)))
    return boxes


TILE_NAMES = {(3, 2): ("top left", "top middle", "top right", "bottom left", "bottom middle", "bottom right"),
              (2, 3): ("top left", "top right", "middle left", "middle right", "bottom left", "bottom right")}


def tile_names(width: int, height: int) -> tuple[str, ...]:
    return TILE_NAMES[(3, 2) if width >= height else (2, 3)]


def _ink(canvas: np.ndarray, text: str, x: int, y: int, scale: int, colour, max_width: int | None = None) -> None:
    """Draw TEXT into CANVAS at (x, y), clipped to MAX_WIDTH and to the canvas."""
    glyphs = text_image(font_text(text), scale)
    room_w = canvas.shape[1] - x if max_width is None else min(max_width, canvas.shape[1] - x)
    glyphs = glyphs[: max(0, canvas.shape[0] - y), : max(0, room_w)]
    if glyphs.size == 0:
        return
    region = canvas[y:y + glyphs.shape[0], x:x + glyphs.shape[1]]
    region[glyphs > 0] = colour


def _block(canvas: np.ndarray, box: tuple[int, int, int, int], colour) -> None:
    left, top, right, bottom = box
    canvas[top:bottom, left:right] = colour


def _outline(canvas: np.ndarray, box: tuple[int, int, int, int], colour, edge: int = 4) -> None:
    left, top, right, bottom = box
    for side in ((left, top, right, top + edge), (left, bottom - edge, right, bottom),
                 (left, top, left + edge, bottom), (right - edge, top, right, bottom)):
        _block(canvas, side, colour)


def _leader(canvas: np.ndarray, label: Label, colour) -> None:
    """The leader line from LABEL to what it names; a short run under the label when the line starts beside it."""
    x, top, bottom = label.leader
    _block(canvas, (x, min(top, bottom), x + 2, max(top, bottom)), colour)
    left, _, right, _ = label.box
    if not left <= x <= right and top < bottom:
        _block(canvas, (min(x, right), top, max(x + 2, left), top + 2), colour)


def _section_blocks(canvas: np.ndarray, plan: StripPlan, sections: Sequence[dict]) -> None:
    for section in sections:
        left, right = plan.x(section["start"]), plan.x(section["end"])
        colour = KIND_COLOURS.get(section.get("kind"), KIND_COLOURS["instrumental"])
        _block(canvas, (left, plan.bar_top, max(left + 1, right - 2), plan.bar_bottom), colour)


def _gap_outlines(canvas: np.ndarray, plan: StripPlan, gaps: Sequence[dict]) -> None:
    for gap in gaps:
        left = plan.x(gap["start"])
        right = max(left + 9, plan.x(gap["end"]))
        _outline(canvas, (left, plan.bar_top - GAP_EDGE, right, plan.bar_bottom + GAP_EDGE), GAP_COLOUR)


def _label(canvas: np.ndarray, label: Label) -> None:
    left, top = label.box[0], label.box[1]
    if label.kind == "key":
        _block(canvas, (left, top - 1, left + SWATCH, top + TEXT_H + 1), KIND_COLOURS.get(label.swatch, DIM))
        left += SWATCH + 8
    elif label.kind == "time":
        x, tick_top, tick_bottom = label.leader
        _block(canvas, (x, tick_top, x + 2, tick_bottom), DIM)
    elif label.leader is not None:
        _leader(canvas, label, GAP_COLOUR if label.kind == "gap" else DIM)
    for row, line in enumerate(label.lines):
        _ink(canvas, line, left, top + row * LOW_PITCH, SCALE, DIM if label.kind == "time" else INK)


def _legend(canvas: np.ndarray, y: int) -> None:
    x = 24
    for name, colour in (*KIND_COLOURS.items(), ("story gap", GAP_COLOUR)):
        _block(canvas, (x, y, x + 24, y + 18), colour)
        _ink(canvas, name, x + 32, y + 2, 3, INK)
        x += 40 + 12 * len(name) + 40


def timeline_strip(structure: dict, title: str) -> np.ndarray:
    """The song's sections in time (sung, mixed, instrumental), story gaps outlined and labelled, times below; where
    names crowd, numbers and a key under the strip (`strip.strip_plan` lays every label out first)."""
    plan = strip_plan(structure, STRIP_SIZE[0])
    canvas = np.full((plan.height, plan.width, 3), BACKGROUND, np.uint8)
    _ink(canvas, f"{title}  {clock(plan.total_s)}", 24, 16, 4, INK)
    _section_blocks(canvas, plan, structure["sections"])
    _gap_outlines(canvas, plan, (structure.get("pacing") or {}).get("story_gaps") or [])
    for label in plan.labels:
        _label(canvas, label)
    _legend(canvas, plan.legend_y)
    return canvas


def placeholder(width: int, height: int, text: str) -> np.ndarray:
    canvas = np.full((height, width, 3), 60, np.uint8)
    _ink(canvas, text, 12, 12, 4, INK)
    return canvas


@dataclass(frozen=True)
class BoardShot:
    number: int
    key: str
    at: float | None
    lines: str
    picture: np.ndarray


def board_label(shot: BoardShot) -> str:
    when = clock(shot.at, tenths=True) if shot.at is not None else "TIME ?"
    return f"{shot.number}  {shot.key}  {when}  {shot.lines}".strip()


def contact_sheet(shots: Sequence[BoardShot], sheet: int, sheets: int) -> np.ndarray:
    """One numbered contact sheet: each shot's first frame under its number, time on the song and lines."""
    tiles = [Tile(shot.picture, font_text(board_label(shot))) for shot in shots]
    title = f"BOARD {sheet} OF {sheets}  SHOTS {shots[0].number} TO {shots[-1].number}"
    return compose(tiles, SHEET_COLUMNS, title=title, scale=3)
