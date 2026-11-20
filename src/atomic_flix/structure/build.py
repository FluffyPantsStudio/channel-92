"""The whole structure record, from the stems, the timed lines and the bar's ones."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..timing.level import FRAME_S
from .lines import TimedLine
from .measures import measure, rest_level
from .pacing import pacing
from .sections import Piece, bar_length, cut_song, names, snap
from .voice import TAIL_BELOW_WORKING_DB, LeadVoice, lead_voice

STORY_GAP_S = 8.0
LENGTHS_DIFFER_S = 0.05
LIMIT = ("Sections come from the lead stem's level and the lyric's order, not from listening. A person confirms "
         "them by ear: gate 2 plays the song.")


@dataclass(frozen=True)
class StructureInputs:
    """Everything the structure reads, already loaded: the lead and rest stems, the timed lead lines, the bar's ones
    (None without a pulse), the `bars` ruling, the swells, and notes from loading them."""

    lead: np.ndarray
    lead_rate: int
    rest: np.ndarray | None
    rest_rate: int | None
    rest_name: str
    lines: tuple[TimedLine, ...] = ()
    ones: tuple[float, ...] | None = None
    ruling: str | None = None
    swells: tuple[dict, ...] = ()
    notes: tuple[str, ...] = ()


def _seconds(samples: np.ndarray | None, rate: int | None) -> float:
    return len(samples) / rate if samples is not None and rate else 0.0


def _stem_notes(inputs: StructureInputs, voice: LeadVoice, lead_s: float, rest_s: float) -> list[str]:
    notes = []
    if inputs.rest is not None and abs(lead_s - rest_s) > LENGTHS_DIFFER_S:
        notes.append(f"the lead stem is {lead_s:.2f} s long and the {inputs.rest_name} stem {rest_s:.2f} s; the song "
                     f"is taken as {max(lead_s, rest_s):.2f} s and the shorter stem counts as silent past its end")
    if inputs.rest is None:
        notes.append("no band stem and no mix: the band level is not measured")
    elif inputs.rest_name == "mix":
        notes.append("no band stem: the band level is read from the mix, so it includes the voice")
    if voice.working_db is None:
        notes.append("the lead stem is silent (nothing over -60 dBFS): no sung sections")
    return notes


def _line_notes(lines: Sequence[TimedLine], numbered: bool, pieces: Sequence[Piece]) -> list[str]:
    if not lines:
        return ["no timed lyric lines: the sung stretches come from the vocal gaps alone and are numbered"]
    if numbered:
        return ["the lyric has no [Section] markers: the sung stretches come from the vocal gaps alone and are "
                "numbered"]
    used = {x.id for piece in pieces for x in piece.lines}
    outside = [x for x in lines if x.id not in used]
    return [f"line {x.id} is timed at {x.start:.2f} s, where the lead stem is not singing; it is left out"
            for x in outside]


def _section(n: int, piece: Piece, name: tuple[str, int | None], edges: tuple[float, float], bar: float | None,
             voice: LeadVoice, rest, swells) -> dict:
    start, end = edges
    duration = round(end - start, 2)
    return {"id": f"s{n:02d}", "label": name[0], "lyric_section": piece.label or None, "occurrence": name[1],
            "start": round(start, 2), "end": round(end, 2), "measured": [round(piece.start, 2), round(piece.end, 2)],
            "snap_s": [round(start - piece.start, 2), round(end - piece.end, 2)], "duration_s": duration,
            "bars": round(duration / bar, 1) if bar else None,
            **measure(piece.start, piece.end, piece.sung, voice, rest, swells),
            "lines": [x.id for x in piece.lines], "uncertain_lines": [x.id for x in piece.lines if x.flagged]}


def build_structure(inputs: StructureInputs, gap_s: float = STORY_GAP_S) -> dict:
    """The song's structure record (written as analysis/structure.json)."""
    lead_s, rest_s = _seconds(inputs.lead, inputs.lead_rate), _seconds(inputs.rest, inputs.rest_rate)
    total = max(lead_s, rest_s)
    frames = int(round(total / FRAME_S))
    voice = lead_voice(inputs.lead, inputs.lead_rate, frames)
    rest = rest_level(inputs.rest, inputs.rest_rate, frames)
    numbered = not any(x.label for x in inputs.lines)
    pieces = cut_song(voice, total, () if numbered else inputs.lines)
    edges = snap([p.start for p in pieces] + [total], inputs.ones)
    bar = bar_length(inputs.ones)
    sections = [_section(n, piece, name, (a, b), bar, voice, rest, inputs.swells)
                for n, (piece, name, a, b) in enumerate(zip(pieces, names(pieces, numbered), edges, edges[1:]), 1)]
    notes = (list(inputs.notes) + _stem_notes(inputs, voice, lead_s, rest_s)
             + _line_notes(inputs.lines, numbered, pieces))
    return {"song_s": round(total, 2), "rest_stem": inputs.rest_name,
            "lead_working_db": None if voice.working_db is None else round(voice.working_db, 1),
            "tail_line_db": None if voice.working_db is None else round(voice.working_db - TAIL_BELOW_WORKING_DB, 1),
            "bar_s": None if bar is None else round(bar, 3), "snapped": bar is not None, "ruling": inputs.ruling,
            "sections": sections, "vocal_regions": [list(r) for r in voice.regions],
            "pacing": pacing(sections, voice, inputs.lines, total, gap_s),
            "notes": notes, "limit": LIMIT}
