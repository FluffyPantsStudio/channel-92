"""Line times from the voice stem: the `ears` stage.

Boundaries come from the voice stem's level. The lead is timed on the lead
stem by a single search across the whole song (`lead.time_lead`,
`align.align`); word labels, if supplied, enter that search as one price
among several and only settle which stretch of singing goes with which
line. Where a label's start sits far from the level's start, a person is
asked to look. A line with no usable labels is marked as a guess. Each lead
line carries a confidence and the reason it landed there; under 0.5 is flagged.

Choir lines are dealt to the choir stem between their lead neighbours
(`assign.deal_vocal_spans`), which bounds any error to that stretch.

On the "66 of 68 lines" figure against the 56-line table (first film): the
two counts are of different lyrics. 66 of 68 is the first `songmap` run,
level alone, on the draft lyric (the generation prompt with the instrument
directions removed: `lyric-source.txt` as written, 64 lines, with the four
inline "(magical tub)" backing parts counted as lines of their own, 68). The
56-line table (`build/lines.json`, the fixture's reference) is the corrected
lyric: `lyric.txt` has 52 sung lines, and the table splits the same four
inline backing parts out as group rows, 52 + 4 = 56. "66 of 68 timed" says
nothing about the 56-line table; that run also put verse 2 before the break.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .assign import deal_vocal_spans
from .bounds import anchor
from .lead import UNCERTAIN_BELOW, time_lead
from .labels import Label, match_labels
from .level import FRAME_S, frame_db, quiet_line, running_median, working_level
from .lyric import LyricLine, parse_lyric
from .phrases import find_vocal_spans, runs, vocal_spans_within
from ..formats import stamped

SMOOTH_FRAMES = 5
GAP_MIN_S = 0.25
LABEL_OFF_S = 0.35
FOUND_SHARE_FLAG = 0.70
FOUND_SHARE_USE = 0.50


@dataclass(frozen=True)
class LineTime:
    """One lyric line with its timing and what a person should check."""

    id: str
    part: str
    text: str
    start: float | None
    end: float | None
    marked_start: float | None = None
    gaps: tuple[tuple[float, float], ...] = ()
    provenance: str = "guess"
    flags: tuple[str, ...] = ()
    words: tuple[dict, ...] = ()
    confidence: float | None = None
    why: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "part": self.part, "text": self.text, "start": self.start, "end": self.end,
                "marked_start": self.marked_start, "gaps": [list(g) for g in self.gaps], "provenance": self.provenance,
                "flags": list(self.flags), "words": list(self.words), "confidence": None if self.confidence is None else round(self.confidence, 3),
                "why": self.why}


@dataclass(frozen=True)
class Timing:
    """The line table for a song, plus the levels it was measured against."""

    sung_db: float
    floor_db: float
    marked: bool
    lines: tuple[LineTime, ...]
    vocal_spans: tuple[tuple[float, float], ...] = field(default=())

    @property
    def unplaced(self) -> tuple[str, ...]:
        return tuple(ln.id for ln in self.lines if ln.start is None)

    def to_dict(self) -> dict:
        return {"sung_db": round(self.sung_db, 2), "floor_db": round(self.floor_db, 2),
                "marked": self.marked, "lines": [ln.to_dict() for ln in self.lines],
                "unplaced": list(self.unplaced), "vocal_spans": [list(p) for p in self.vocal_spans]}


@dataclass(frozen=True)
class _Track:
    level: np.ndarray
    sung_db: float
    floor_db: float

    @property
    def vocal_on(self) -> np.ndarray:
        return self.level > self.floor_db


def _track(samples: np.ndarray, rate: int) -> _Track:
    db = frame_db(samples, rate)
    work = working_level(db)
    return _Track(running_median(db, SMOOTH_FRAMES), work, quiet_line(work))


def _frame(seconds: float) -> int:
    return int(round(seconds / FRAME_S))


def _gaps(track: _Track, start: float, end: float) -> tuple[tuple[float, float], ...]:
    a, b = _frame(start), _frame(end)
    out = []
    for first, stop in runs(~track.vocal_on[a:b]):
        if (stop - first) * FRAME_S >= GAP_MIN_S:
            out.append((round((a + first) * FRAME_S, 3), round((a + stop) * FRAME_S, 3)))
    return tuple(out)


def _choir_blocks(lines: Sequence[LyricLine]) -> list[tuple[int, int]]:
    """[first, stop) index ranges of consecutive choir lines in lyric order."""
    chunks, first = [], None
    for i, line in enumerate(list(lines) + [None]):
        is_choir = line is not None and line.part != "lead"
        if is_choir and first is None:
            first = i
        elif not is_choir and first is not None:
            chunks.append((first, i))
            first = None
    return chunks


def _place_choir(lines: Sequence[LyricLine], track: _Track | None,
                 lead_times: Mapping[str, tuple[float, float]]) -> tuple[dict, dict]:
    """Time choir lines on the choir stem, each block between its lead neighbours.

    A choir line sits in the lyric between two lead lines, so it is looked for
    only from the start of the lead line before it to the end of the lead line
    after it. Returns (times, extra flags).
    """
    if track is None:
        return {}, {}
    vocal_spans = find_vocal_spans(track.level, track.floor_db)
    times: dict[str, tuple[float, float]] = {}
    notes: dict[str, list[str]] = {}
    for first, stop in _choir_blocks(lines):
        before = [lead_times[ln.id] for ln in lines[:first] if ln.id in lead_times]
        after = [lead_times[ln.id] for ln in lines[stop:] if ln.id in lead_times]
        lo = _frame(before[-1][0]) if before else 0
        hi = _frame(after[0][1]) if after else len(track.level)
        inside = vocal_spans_within(vocal_spans, lo, hi, track.level, track.floor_db)
        block = list(lines[first:stop])
        for line, got in zip(block, deal_vocal_spans(inside, block, track.sung_db)):
            if got is not None:
                times[line.id] = (inside[got[0]].start, inside[got[1] - 1].end)
        for prev, line in zip(block[:-1], block[1:]):
            if line.id not in times and prev.id in times and prev.words == line.words:
                times[line.id] = times[prev.id]
                notes.setdefault(line.id, []).append(f"same time as {prev.id}: two parts at once?")
    return times, notes


def _trim_around_choir(times: Mapping[str, tuple[float, float]], choir: Mapping[str, tuple[float, float]]) -> dict:
    """A lead line overlapping a choir line starts after it (or ends where it starts)."""
    out = dict(times)
    for key, (start, end) in times.items():
        for c_start, c_end in choir.values():
            if c_start <= start < c_end:
                start = c_end
            elif start < c_start < end:
                end = c_start
        if end > start:
            out[key] = (round(start, 3), round(end, 3))
    return out


def _label_flags(line: LyricLine, start: float | None, found: list[int], labels: Sequence[Label]):
    flags = []
    marked_start = labels[found[0]].start if found else None
    if line.words and not line.wordless and len(found) < FOUND_SHARE_FLAG * len(line.words):
        flags.append(f"{len(found)} of {len(line.words)} words found")
    if start is not None and marked_start is not None and abs(marked_start - start) > LABEL_OFF_S:
        side = "early" if marked_start < start else "late"
        flags.append(f"label {abs(marked_start - start):.2f} s {side}")
    return marked_start, flags


def _usable(lines: Sequence[LyricLine], found_all: Mapping[str, list[int]]) -> dict[str, list[int]]:
    """Lines with at least half their words matched; only these are placed by their labels."""
    return {ln.id: found_all[ln.id] for ln in lines
            if found_all.get(ln.id) and len(found_all[ln.id]) >= FOUND_SHARE_USE * max(1, len(ln.words))}


def _choir_confidence(lines: Sequence[LyricLine], placed: Mapping) -> dict[str, float]:
    """A choir line is looked for between its lead neighbours, so it is only as sure as they are."""
    out = {}
    for first, stop in _choir_blocks(lines):
        before = [placed[ln.id].confidence for ln in lines[:first] if ln.id in placed][-1:]
        after = [placed[ln.id].confidence for ln in lines[stop:] if ln.id in placed][:1]
        for line in lines[first:stop]:
            out[line.id] = min(before + after, default=0.0)
    return out


def _lead_times(lead: _Track, lead_lines: Sequence[LyricLine], found: Mapping[str, list[int]],
                labels: Sequence[Label] | None):
    placed = time_lead(lead.level, lead.floor_db, lead.sung_db, lead_lines, found, labels)
    times = {key: (got.start, got.end) for key, got in placed.items() if got.start is not None}
    return times, placed


def _line_time(line: LyricLine, times, placed, track, ctx) -> LineTime:
    labels, found, found_all, choir_notes, fixes, choir_sure = ctx
    start, end = times.get(line.id, (None, None))
    marked_start, flags = None, []
    if labels and line.part == "lead":
        marked_start, flags = _label_flags(line, start, found_all.get(line.id, []), labels)
    flags.extend(choir_notes.get(line.id, []))
    lead_note = placed.get(line.id)
    confidence = lead_note.confidence if lead_note else choir_sure.get(line.id)
    why = lead_note.why if lead_note else "choir stem, dealt between its lead neighbours; as sure as they are"
    if lead_note and start is not None:
        flags.extend(lead_note.flags)
    elif start is not None and confidence is not None and confidence < UNCERTAIN_BELOW:
        flags.append(f"uncertain ({confidence:.2f}): a lead neighbour is uncertain")
    provenance = "level" if line.id in found else "guess"
    if labels and provenance == "guess" and start is not None:
        flags.append("no labels: placed by level alone")
    if line.id in fixes:
        start, end = float(fixes[line.id][0]), float(fixes[line.id][1])
        provenance, confidence, why = "fixed", 1.0, "set by hand"
    if start is None:
        flags.append("no time")
        if track is None:
            flags.append("no choir stem")
    words = ()
    if labels and start is not None:
        words = tuple({"text": lb.text, "from": lb.start, "to": lb.end}
                      for lb in labels if start <= anchor(lb) <= end)
    gaps = _gaps(track, start, end) if (start is not None and track is not None) else ()
    return LineTime(line.id, line.part, line.text, start, end, marked_start, gaps, provenance,
                    tuple(dict.fromkeys(flags)), words, confidence, why)


def time_lines(lyric: Sequence[LyricLine] | str, voice: np.ndarray, rate: int, *,
               labels: Sequence[Label] | None = None, choir: np.ndarray | None = None,
               choir_rate: int | None = None, fixes: Mapping[str, Sequence[float]] | None = None) -> Timing:
    """Time every lyric line on the voice stem (and choir lines on the choir stem).

    `lyric` is parsed lines or lyric text; `voice` and `choir` are sample
    arrays. `labels` are optional recognised words; `fixes` maps a line id to
    a hand-set [start, end] that overrides everything else.
    """
    lines = parse_lyric(lyric) if isinstance(lyric, str) else list(lyric)
    lead = _track(voice, rate)
    choir_track = _track(choir, choir_rate or rate) if choir is not None else None
    lead_lines = [ln for ln in lines if ln.part == "lead"]
    found_all = match_labels(lines, labels) if labels else {}
    found = _usable(lead_lines, found_all)
    lead_times, placed = _lead_times(lead, lead_lines, found, labels)
    choir_times, choir_notes = _place_choir(lines, choir_track, lead_times)
    times = {**_trim_around_choir(lead_times, choir_times), **choir_times}
    ctx = (labels, found, found_all, choir_notes, fixes or {}, _choir_confidence(lines, placed))
    out = [_line_time(line, times, placed, lead if line.part == "lead" else choir_track, ctx) for line in lines]
    vocal_spans = find_vocal_spans(lead.level, lead.floor_db)
    return Timing(lead.sung_db, lead.floor_db, bool(labels), tuple(out),
                  tuple((p.start, p.end) for p in vocal_spans))


def write_timing(timing: Timing, path) -> Path:
    """Write the line table as UTF-8 JSON (`analysis/voice-lines.json`)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(stamped("voice-lines", timing.to_dict()), ensure_ascii=False, indent=1), encoding="utf-8")
    return out
