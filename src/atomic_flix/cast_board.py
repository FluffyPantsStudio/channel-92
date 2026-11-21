"""The review board of a character's sheet: every view on one picture, laid out like a studio reference board.

A large head-and-shoulders portrait and the full-length front view down the left; to their right a row of the head
views from every side, an optional row of expressions, and the other full-length views. One picture per character is
what a director reviews on a phone; the separate view pictures are what the lint rules measure and the shots use.
Needs Pillow (the only part of the kit that does; everything else reads PNG with numpy alone).
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from .cast import views_of

CANVAS = (2880, 2360)
MARGIN, GAP = 18, 12
LEFT_WIDTH = 900
HERO_HEIGHT = 1130
FRAME = (236, 237, 241)
CELL = (199, 200, 206)
HEAD_ROW = 600
EXPRESSION_ROW = 480
HEADS = ("front", "three_quarter", "profile", "back")
BODIES = ("body_three_quarter", "body_back")


class BoardError(ValueError):
    """A board cannot be made: a view is missing or unreadable, or Pillow is not installed."""


def _boxes(count: int, x: int, y: int, width: int, height: int) -> list[tuple[int, int, int, int]]:
    cell = (width - GAP * (count - 1)) // count
    return [(x + k * (cell + GAP), y, cell, height) for k in range(count)]


def _layout(expressions: int) -> dict[str, list[tuple[int, int, int, int]]]:
    right = MARGIN + LEFT_WIDTH + GAP
    width = CANVAS[0] - MARGIN - right
    lower = CANVAS[1] - MARGIN
    rows = {"hero": [(MARGIN, MARGIN, LEFT_WIDTH, HERO_HEIGHT)],
            "body_front": [(MARGIN, MARGIN + HERO_HEIGHT + GAP, LEFT_WIDTH, lower - MARGIN - HERO_HEIGHT - GAP)],
            "heads": _boxes(len(HEADS), right, MARGIN, width, HEAD_ROW)}
    top = MARGIN + HEAD_ROW + GAP
    if expressions:
        rows["expressions"] = _boxes(expressions, right, top, width, EXPRESSION_ROW)
        top += EXPRESSION_ROW + GAP
    rows["bodies"] = _boxes(len(BODIES), right, top, width, lower - top)
    return rows


def _paste(canvas, picture_path: Path, box: tuple[int, int, int, int]) -> None:
    from PIL import Image, ImageOps

    x, y, width, height = box
    canvas.paste(Image.new("RGB", (width, height), CELL), (x, y))
    with Image.open(picture_path) as picture:
        fitted = ImageOps.contain(picture.convert("RGB"), (width, height))
    canvas.paste(fitted, (x + (width - fitted.width) // 2, y + (height - fitted.height) // 2))


def board_path(stem: str) -> str:
    return f"refs/boards/{stem}-board.png"


def make_board(root: Path, stem: str, person: Mapping, expressions: Sequence[str] = ()) -> Path:
    """Write refs/boards/STEM-board.png from the person's views (all of them must be there) and return its path."""
    try:
        from PIL import Image
    except ImportError:
        raise BoardError("the review board needs Pillow (pip install pillow)") from None
    views = views_of(person)
    wanted = [*HEADS, *BODIES, "body_front"]
    absent = [view for view in wanted if not (view in views and (Path(root) / views[view]).is_file())]
    if absent:
        raise BoardError(f"{stem}: no picture yet for {', '.join(absent)}")
    shown = [path for path in expressions if (Path(root) / path).is_file()][:5]
    layout = _layout(len(shown))
    canvas = Image.new("RGB", CANVAS, FRAME)
    try:
        _paste(canvas, Path(root) / views["front"], layout["hero"][0])
        _paste(canvas, Path(root) / views["body_front"], layout["body_front"][0])
        for view, box in zip(HEADS, layout["heads"]):
            _paste(canvas, Path(root) / views[view], box)
        for path, box in zip(shown, layout.get("expressions", [])):
            _paste(canvas, Path(root) / path, box)
        for view, box in zip(BODIES, layout["bodies"]):
            _paste(canvas, Path(root) / views[view], box)
    except OSError as problem:
        raise BoardError(f"{stem}: a view cannot be read as a picture ({problem})") from None
    aim = Path(root) / board_path(stem)
    aim.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(aim)
    return aim
