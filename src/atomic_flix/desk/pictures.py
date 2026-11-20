"""The packet's pictures, drawn with numpy and the review sheets' pixel font (no imaging library):
the song's timeline strip, the fixed zoom tiles of a still, and the board's contact sheets."""

from __future__ import annotations

import string
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..review.canvas import Tile, compose, text_image

SCREEN_LONG_SIDE = 1600          # a still as a phone shows it
SHEET_LONG_SIDE = 2400           # a review or contact sheet, zoomed on the phone
TILE_OVERLAP = 0.08              # each zoom tile reaches this share of its size into its neighbours
STRIP_SIZE = (1600, 360)
THUMB_WIDTH = 760
SHOTS_PER_SHEET = 6
SHEET_COLUMNS = 2
FONT = set(string.ascii_uppercase + string.digits + ".-:/+%_><=()# ")
BACKGROUND = (22, 22, 26)
INK = (235, 235, 235)
DIM = (150, 150, 160)
KIND_COLOURS = {"sung": (232, 168, 56), "mixed": (196, 120, 176), "instrumental": (64, 76, 98)}
GAP_COLOUR = (90, 210, 225)


def font_text(text: str) -> str:
    """TEXT as the pixel font can draw it: upper case, characters it lacks dropped, spaces collapsed."""
    kept = "".join(char if char in FONT else ("" if char in "'`" else " ") for char in str(text).upper())
    return " ".join(kept.split())


def clock(seconds: float, tenths: bool = False) -> str:
    """Seconds as M:SS (or M:SS.s)."""
    minutes, rest = divmod(max(0.0, float(seconds)), 60.0)
    return f"{int(minutes)}:{rest:04.1f}" if tenths else f"{int(minutes)}:{int(rest):02d}"


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


def _tick_step(total_s: float) -> int:
    for step in (5, 10, 15, 30, 60):
        if total_s / step <= 12:
            return step
    return 120


@dataclass(frozen=True)
class StripLayout:
    width: int
    left: int = 24
    right: int = 24
    bar_top: int = 132
    bar_bottom: int = 246

    def x(self, seconds: float, total_s: float) -> int:
        span = self.width - self.left - self.right
        return self.left + int(round(span * min(max(seconds, 0.0), total_s) / total_s))


def _sections(canvas: np.ndarray, layout: StripLayout, sections: Sequence[dict], total_s: float) -> None:
    for number, section in enumerate(sections):
        left, right = layout.x(section["start"], total_s), layout.x(section["end"], total_s)
        colour = KIND_COLOURS.get(section.get("kind"), KIND_COLOURS["instrumental"])
        _block(canvas, (left, layout.bar_top, max(left + 1, right - 2), layout.bar_bottom), colour)
        label_y = 64 if number % 2 == 0 else 98
        text = f"{section.get('label') or section.get('id')} {clock(section['start'])}"
        _ink(canvas, text, left + 2, label_y, 3, INK, max_width=max(8, 2 * (right - left)))
        _block(canvas, (left, label_y + 18, left + 2, layout.bar_top), DIM)


def _gaps(canvas: np.ndarray, layout: StripLayout, gaps: Sequence[dict], total_s: float) -> None:
    for gap in gaps:
        left, right = layout.x(gap["start"], total_s), layout.x(gap["end"], total_s)
        _outline(canvas, (left, layout.bar_top - 6, max(left + 9, right), layout.bar_bottom + 6), GAP_COLOUR)
        room = max(8, right - left - 10)
        rank = gap.get("rank", "")
        name = f"STORY GAP {rank}" if len(f"STORY GAP {rank}") * 12 <= room else f"GAP {rank}"
        _ink(canvas, name, left + 8, layout.bar_top + 10, 3, INK, max_width=room)
        if gap.get("duration_s") is not None:
            _ink(canvas, f"{float(gap['duration_s']):.0f} S", left + 8, layout.bar_top + 34, 3, INK, max_width=room)


def _ticks(canvas: np.ndarray, layout: StripLayout, total_s: float) -> None:
    step = _tick_step(total_s)
    for second in range(0, int(total_s) + 1, step):
        x = layout.x(second, total_s)
        _block(canvas, (x, layout.bar_bottom + 8, x + 2, layout.bar_bottom + 20), DIM)
        _ink(canvas, clock(second), x + 6, layout.bar_bottom + 12, 3, DIM)


def _legend(canvas: np.ndarray, y: int) -> None:
    x = 24
    for name, colour in (*KIND_COLOURS.items(), ("story gap", GAP_COLOUR)):
        _block(canvas, (x, y, x + 24, y + 18), colour)
        _ink(canvas, name, x + 32, y + 2, 3, INK)
        x += 40 + 12 * len(name) + 40


def timeline_strip(structure: dict, title: str) -> np.ndarray:
    """The song's sections in time (sung, mixed, instrumental), story gaps outlined and labelled, times below."""
    width, height = STRIP_SIZE
    canvas = np.full((height, width, 3), BACKGROUND, np.uint8)
    sections = list(structure.get("sections") or [])
    total_s = float(structure.get("song_s") or (sections[-1]["end"] if sections else 0.0))
    if total_s <= 0 or not sections:
        raise ValueError("the structure has no sections")
    layout = StripLayout(width)
    _ink(canvas, f"{title}  {clock(total_s)}", 24, 16, 4, INK)
    _sections(canvas, layout, sections, total_s)
    _gaps(canvas, layout, (structure.get("pacing") or {}).get("story_gaps") or [], total_s)
    _ticks(canvas, layout, total_s)
    _legend(canvas, height - 44)
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
