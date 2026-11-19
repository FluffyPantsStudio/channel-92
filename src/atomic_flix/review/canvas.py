"""Sheets drawn with numpy: tiles of frames in rows, each with a short label in a small built-in pixel font.

No imaging library is needed; the sheet is written through ffmpeg (`atomic_flix.cut.media.write_image`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 3 x 5 glyphs, rows top to bottom, '1' = ink.
_GLYPHS = {
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
    "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001001010010",
    "8": "111101111101111", "9": "111101111001111", "A": "010101111101101", "B": "110101110101110",
    "C": "011100100100011", "D": "110101101101110", "E": "111100110100111", "F": "111100110100100",
    "G": "011100101101011", "H": "101101111101101", "I": "111010010010111", "J": "001001001101010",
    "K": "101101110101101", "L": "100100100100111", "M": "101111111101101", "N": "110101101101101",
    "O": "010101101101010", "P": "110101110100100", "Q": "010101101110011", "R": "110101110101101",
    "S": "011100010001110", "T": "111010010010010", "U": "101101101101111", "V": "101101101101010",
    "W": "101101111111101", "X": "101101010101101", "Y": "101101010010010", "Z": "111001010100111",
    ".": "000000000000010", "-": "000000111000000", ":": "000010000010000", "/": "001001010100100",
    "+": "000010111010000", "%": "101001010100101", "_": "000000000000111", ">": "100010001010100",
    "<": "001010100010001", "=": "000111000111000", "(": "010100100100010", ")": "010001001001010",
    "#": "101111101111101", " ": "000000000000000",
}
GLYPH_W, GLYPH_H = 3, 5
BACKGROUND = 22
INK = 235
GUTTER = 6
LABEL_PAD = 3


def text_image(text: str, scale: int = 2) -> np.ndarray:
    """A grey image (0 background, 255 ink) of `text` in the pixel font; unknown characters draw as '#'."""
    columns = []
    for char in text.upper():
        bits = _GLYPHS.get(char, _GLYPHS["#"])
        glyph = np.array([int(b) for b in bits], np.uint8).reshape(GLYPH_H, GLYPH_W) * 255
        columns += [glyph, np.zeros((GLYPH_H, 1), np.uint8)]
    if not columns:
        return np.zeros((GLYPH_H * scale, 1), np.uint8)
    line = np.concatenate(columns[:-1], axis=1)
    return np.kron(line, np.ones((scale, scale), np.uint8))


@dataclass(frozen=True)
class Tile:
    picture: np.ndarray            # (h, w, 3) uint8
    label: str = ""
    border: tuple[int, int, int] | None = None


def _label_strip(text: str, width: int, scale: int) -> np.ndarray:
    height = GLYPH_H * scale + 2 * LABEL_PAD
    strip = np.full((height, width, 3), BACKGROUND, np.uint8)
    ink = text_image(text, scale)[:, : max(1, width - 2 * LABEL_PAD)]
    region = strip[LABEL_PAD:LABEL_PAD + ink.shape[0], LABEL_PAD:LABEL_PAD + ink.shape[1]]
    mask = ink > 0
    region[mask] = INK
    return strip


def _framed(tile: Tile, width: int, height: int) -> np.ndarray:
    picture = np.full((height, width, 3), BACKGROUND, np.uint8)
    h, w = min(height, tile.picture.shape[0]), min(width, tile.picture.shape[1])
    picture[:h, :w] = tile.picture[:h, :w]
    if tile.border is not None:
        edge = max(2, width // 80)
        colour = np.array(tile.border, np.uint8)
        picture[:edge], picture[-edge:], picture[:, :edge], picture[:, -edge:] = colour, colour, colour, colour
    return picture


def compose(tiles: list[Tile], columns: int, *, title: str = "", scale: int = 2) -> np.ndarray:
    """Lay tiles out left to right, `columns` to a row, each labelled above; an optional title on top."""
    if not tiles:
        raise ValueError("no tiles to lay out")
    width = max(tile.picture.shape[1] for tile in tiles)
    height = max(tile.picture.shape[0] for tile in tiles)
    cells = [np.concatenate([_label_strip(tile.label, width, scale), _framed(tile, width, height)]) for tile in tiles]
    cell_h, cell_w = cells[0].shape[:2]
    columns = max(1, min(columns, len(cells)))
    rows = -(-len(cells) // columns)
    sheet_w = columns * cell_w + (columns + 1) * GUTTER
    top = 0
    title_strip = None
    if title:
        title_strip = _label_strip(title, sheet_w, scale + 1)
        top = title_strip.shape[0]
    sheet = np.full((top + rows * cell_h + (rows + 1) * GUTTER, sheet_w, 3), BACKGROUND, np.uint8)
    if title_strip is not None:
        sheet[:top] = title_strip
    for position, cell in enumerate(cells):
        row, column = divmod(position, columns)
        y = top + GUTTER + row * (cell_h + GUTTER)
        x = GUTTER + column * (cell_w + GUTTER)
        sheet[y:y + cell_h, x:x + cell_w] = cell
    return sheet


def stack(boards: list[np.ndarray]) -> np.ndarray:
    """Stack sheets of possibly different widths top to bottom."""
    width = max(sheet.shape[1] for sheet in boards)
    padded = []
    for sheet in boards:
        block = np.full((sheet.shape[0], width, 3), BACKGROUND, np.uint8)
        block[:, : sheet.shape[1]] = sheet
        padded.append(block)
    return np.concatenate(padded)


def heat(difference: np.ndarray, gain: float = 4.0) -> np.ndarray:
    """A difference image (0 to 1 floats, (h, w)) as amber on black: bright where the picture changed."""
    value = np.clip(difference * gain, 0, 1)
    return np.stack([value * 255, value * 200, value * 60], axis=-1).astype(np.uint8)
