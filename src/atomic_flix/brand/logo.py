"""The logo file and where it sits on a frame (see the package's own docstring)."""

from __future__ import annotations

import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_LOGO = HERE / "channel92-logo.png"
ERA_LOGOS = HERE / "eras"
WIDTH_SHARE = 0.14
MARGIN_SHARE = 0.03
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(path: Path | str) -> tuple[int, int]:
    """(width, height) from a PNG's header, without decoding it."""
    with open(path, "rb") as handle:
        head = handle.read(24)
    if len(head) < 24 or head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a PNG")
    width, height = struct.unpack(">II", head[16:24])
    return int(width), int(height)


LOGO_NATIVE = png_size(DEFAULT_LOGO)


def logo_file(era_id: str | None = None) -> Path:
    """The logo for ERA_ID ("1950s" to "2000s", or None): the era's own mark, else the channel's modern mark (the
    2000s wear it, and so does a film with no era). The era logos are drawn by tools/make_era_logos.py."""
    if era_id is not None and not isinstance(era_id, str):
        raise TypeError(f"an era is named like '1980s', not {era_id!r}")
    own = ERA_LOGOS / f"logo-{era_id}.png" if era_id else None
    return own if own is not None and own.is_file() else DEFAULT_LOGO


def logo_box(width: int, height: int, native: tuple[int, int] = LOGO_NATIVE) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the logo on a WIDTHxHEIGHT frame: top right, inside the margin, never larger than NATIVE."""
    if width <= 0 or height <= 0:
        raise ValueError(f"a frame of {width}x{height} has no room for a logo")
    margin = round(MARGIN_SHARE * width)
    logo_w = min(round(WIDTH_SHARE * width), native[0])
    logo_h = max(1, round(logo_w * native[1] / native[0]))
    return width - margin - logo_w, margin, logo_w, logo_h
