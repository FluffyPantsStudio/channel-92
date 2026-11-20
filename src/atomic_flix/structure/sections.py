"""The song cut into sections: instrumental stretches where the lead is silent, sung stretches between them, each
sung stretch divided where the lyric's [Section] changes, then every inner edge moved onto the nearest bar's one."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import groupby
from typing import Sequence

import numpy as np

from .lines import TimedLine
from .voice import LeadVoice

INSTRUMENTAL_MIN_S = 3.0
UNMATCHED_MIN_S = 3.0
UNMATCHED_VOICED_S = 1.0
UNLABELLED = "unlabelled vocal"


@dataclass(frozen=True)
class Piece:
    """A stretch of the song before it is named: sung or not, and the lyric block whose lines are in it."""

    start: float
    end: float
    sung: bool
    block: int | None = None
    label: str = ""
    lines: tuple[TimedLine, ...] = ()


def stretches(regions: Sequence[tuple[float, float]], total: float) -> list[Piece]:
    """Unsung stretches of INSTRUMENTAL_MIN_S or more (song start and end included), and the sung stretches between."""
    if not regions:
        return [Piece(0.0, total, False)]
    edges = [0.0] + [min(x, total) for region in regions for x in region] + [total]
    breaks = [(a, b) for a, b in zip(edges[0::2], edges[1::2]) if b - a >= INSTRUMENTAL_MIN_S]
    out, pos = [], 0.0
    for a, b in breaks:
        if a > pos:
            out.append(Piece(pos, a, True))
        out.append(Piece(a, b, False))
        pos = b
    if pos < total:
        out.append(Piece(pos, total, True))
    return out


def _unmatched(voice: LeadVoice, start: float, end: float) -> bool:
    return end - start >= UNMATCHED_MIN_S and voice.on_seconds(start, end) >= UNMATCHED_VOICED_S


def _divide(stretch: Piece, lines: Sequence[TimedLine], voice: LeadVoice) -> list[Piece]:
    """A sung stretch cut where the lyric block changes; singing no line covers becomes a piece of its own."""
    a, b = stretch.start, stretch.end
    inside = [x for x in lines if a <= (x.start + x.end) / 2 < b]
    pieces: list[Piece] = []
    pos = a
    for block, group in groupby(inside, key=lambda x: x.block):
        group = tuple(group)
        g_start, g_end = max(group[0].start, pos), min(max(x.end for x in group), b)
        if g_end <= g_start:
            continue
        if _unmatched(voice, pos, g_start):
            pieces.append(Piece(pos, g_start, True))
        elif pieces:
            pieces[-1] = replace(pieces[-1], end=g_start)
        else:
            g_start = a
        pieces.append(Piece(g_start, g_end, True, block, group[0].label, group))
        pos = g_end
    if not pieces or _unmatched(voice, pos, b):
        pieces.append(Piece(pos, b, True))
    else:
        pieces[-1] = replace(pieces[-1], end=b)
    return pieces


def cut_song(voice: LeadVoice, total: float, lines: Sequence[TimedLine]) -> list[Piece]:
    """Every piece of the song in time order."""
    out: list[Piece] = []
    for stretch in stretches(voice.regions, total):
        out += _divide(stretch, lines, voice) if stretch.sung else [stretch]
    return out


def names(pieces: Sequence[Piece], numbered: bool) -> list[tuple[str, int | None]]:
    """Each piece's label and, for a lyric section, which time it is sung (1, 2, ...)."""
    out: list[tuple[str, int | None]] = []
    counts = {"instrumental": 0, "vocal": 0}
    seen: set[int] = set()
    times: dict[str, int] = {}
    for piece in pieces:
        if not piece.sung:
            counts["instrumental"] += 1
            out.append((f"Instrumental {counts['instrumental']}", None))
        elif piece.block is None:
            counts["vocal"] += 1
            out.append((f"Vocal {counts['vocal']}", None) if numbered else (UNLABELLED, None))
        elif piece.block in seen:
            out.append((f"{piece.label or 'unnamed section'} (continued)", None))
        else:
            seen.add(piece.block)
            times[piece.label] = times.get(piece.label, 0) + 1
            out.append((piece.label or "unnamed section", times[piece.label]))
    return out


def bar_length(ones: Sequence[float] | None) -> float | None:
    return float(np.median(np.diff(ones))) if ones is not None and len(ones) > 1 else None


def snap(edges: Sequence[float], ones: Sequence[float] | None) -> list[float]:
    """Each inner edge moved to the nearest bar's one when that keeps every section ahead of the one before it
    and the one is on the grid (within half a bar); the song's start and end stay put."""
    bar = bar_length(ones)
    if bar is None:
        return list(edges)
    grid = np.asarray(ones, dtype=float)
    out = [edges[0]]
    for i in range(1, len(edges) - 1):
        nearest = float(grid[int(np.argmin(np.abs(grid - edges[i])))])
        on_grid = abs(nearest - edges[i]) <= bar / 2
        out.append(nearest if on_grid and out[-1] < nearest < edges[i + 1] else edges[i])
    return out + [edges[-1]]
