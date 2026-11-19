"""Lead lines on the lead stem: build each line's cues, run the global choice, explain it.

Pace (voiced seconds per syllable) begins as an estimate; each pass makes the
choice, re-reads the pace from what it chose, and chooses again. From the second pass on, a line whose words are sung more
than once (a chorus line, a repeated pre-chorus) also expects the length its
copies took in the previous pass, half and half with its syllable count, so a
copy that went wrong is pulled back towards the ones that did not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from .align import LineCue, Placement, align
from .bounds import label_joins
from .labels import Label
from .lyric import LyricLine
from .units import Unit, find_units

FIRST_PACE_S = 0.32
PACE_LIMITS_S = (0.12, 1.0)
SWEEPS = 3
WORDLESS_STRETCH = 2.0
WORDLESS_WEIGHT = 0.3
REPEAT_SHARE = 0.5
REPEAT_WEIGHT = 1.0
UNCERTAIN_BELOW = 0.5


@dataclass(frozen=True)
class LeadTime:
    """Where one lead line was put, how sure that is, and why."""

    start: float | None
    end: float | None
    confidence: float
    why: str
    flags: tuple[str, ...]


def _beats(line: LyricLine) -> float:
    return line.syllables * (WORDLESS_STRETCH if line.wordless else 1.0)


def _repeat_lengths(lines, placements, units) -> dict[str, float]:
    """Per line id: geometric mean voiced length of the other placed copies of its text.

    The line's own length is left out, so a copy that went wrong is compared
    with the others, not with itself.
    """
    lengths: dict[tuple[str, ...], list[tuple[str, float]]] = {}
    for line, got in zip(lines, placements):
        if got.first is None or not line.words:
            continue
        vocal_on = sum(u.vocal_on for u in units[got.first:got.stop])
        lengths.setdefault(line.words, []).append((line.id, max(vocal_on, 0.05)))
    out = {}
    for line in lines:
        rivals = [v for key, v in lengths.get(line.words, []) if key != line.id]
        if rivals:
            out[line.id] = float(np.exp(np.mean(np.log(rivals))))
    return out


def _cues(lines, found, labels, pace, repeats) -> list[LineCue]:
    out = []
    for i, line in enumerate(lines):
        expected = _beats(line) * pace
        weight = WORDLESS_WEIGHT if line.wordless else 1.0
        if line.id in repeats:
            expected = float(np.exp(REPEAT_SHARE * np.log(repeats[line.id])
                                    + (1 - REPEAT_SHARE) * np.log(expected)))
            weight = max(weight, REPEAT_WEIGHT)
        heard = found.get(line.id)
        out.append(LineCue(expected, weight,
                           i > 0 and lines[i - 1].verse_part == line.verse_part,
                           labels[heard[0]] if heard else None, labels[heard[-1]] if heard else None))
    return out


def _measured_pace(lines, placements, units) -> float | None:
    paces = [sum(u.vocal_on for u in units[got.first:got.stop]) / _beats(line)
             for line, got in zip(lines, placements) if got.first is not None and not line.wordless]
    return float(np.clip(np.median(paces), *PACE_LIMITS_S)) if paces else None


def _why(line, got: Placement, units: Sequence[Unit], cue: LineCue, heard: int) -> str:
    parts = [f"labels {heard}/{len(line.words)}" if heard else "level only, no labels"]
    if got.first is None:
        parts.append("no stretch of singing fits")
    else:
        head = units[got.first]
        if head.cut == "pause":
            parts.append(f"starts after a {min(head.pause_before, 99.0):.2f} s pause")
        elif head.cut == "dip":
            parts.append(f"starts at a {head.depth_db:.0f} dB dip (legato)")
        else:
            parts.append("starts inside a held run with no dip: split by length alone")
        vocal_on = sum(u.vocal_on for u in units[got.first:got.stop])
        parts.append(f"{vocal_on:.1f} s voiced, {cue.expected_s:.1f} s expected")
    if got.alternative is not None:
        parts.append(f"next best start {got.alternative:.2f} s (+{got.clearance:.2f})")
    elif got.first is not None:
        parts.append(f"next best: no time (+{got.clearance:.2f})")
    return "; ".join(parts)


def _flags(got: Placement) -> tuple[str, ...]:
    if got.first is None or got.confidence >= UNCERTAIN_BELOW:
        return ()
    if got.alternative is None:
        return (f"uncertain ({got.confidence:.2f}): may not be in the stem",)
    return (f"uncertain ({got.confidence:.2f}): could start at {got.alternative:.2f} s",)


def time_lead(level: np.ndarray, floor_db: float, sung_db: float, lines: Sequence[LyricLine],
              found: Mapping[str, list[int]], labels: Sequence[Label] | None) -> dict[str, LeadTime]:
    """Time the lead lines (in sung order); `found` holds the usable label matches per line id."""
    lines = list(lines)
    labels = list(labels or [])
    joins = label_joins(level, floor_db, lines, found, labels) if found else {}
    units = find_units(level, floor_db, tuple(joins.values()))
    pace, repeats = FIRST_PACE_S, {}
    for _ in range(SWEEPS):
        cues = _cues(lines, found, labels, pace, repeats)
        placements = align(units, cues, sung_db)
        pace = _measured_pace(lines, placements, units) or pace
        repeats = _repeat_lengths(lines, placements, units)
    out = {}
    for line, got, cue in zip(lines, placements, cues):
        start = units[got.first].start if got.first is not None else None
        end = units[got.stop - 1].end if got.first is not None else None
        why = _why(line, got, units, cue, len(found.get(line.id, [])))
        out[line.id] = LeadTime(start, end, got.confidence, why, _flags(got))
    return out
