"""The song's pacing from its sections: sung and instrumental time, the story gaps, the longest unbroken sung
stretch and how the repeated sections compare."""

from __future__ import annotations

from itertools import groupby
from typing import Sequence

import numpy as np

from ..timing.level import FRAME_S
from .lines import TimedLine
from .voice import LeadVoice

SAME_DB = 1.0


def _gaps(sections: Sequence[dict], gap_s: float) -> list[dict]:
    """Instrumental sections whose silence (as measured, before the bar snap) lasts `gap_s` or more, longest first,
    with what comes either side."""
    found = []
    for i, section in enumerate(sections):
        silent_s = round(_measured_s(section), 2)
        if section["kind"] != "instrumental" or silent_s < gap_s:
            continue
        found.append({"id": section["id"], "label": section["label"], "start": section["start"],
                      "end": section["end"], "duration_s": silent_s, "measured": section["measured"],
                      "on_bars_s": section["duration_s"], "bars": section["bars"],
                      "after": sections[i - 1]["label"] if i > 0 else None,
                      "before": sections[i + 1]["label"] if i + 1 < len(sections) else None})
    ranked = sorted(found, key=lambda gap: -gap["duration_s"])
    return [{"rank": n, **gap} for n, gap in enumerate(ranked, start=1)]


def _measured_s(section: dict) -> float:
    return section["measured"][1] - section["measured"][0]


def _longest_sung(sections: Sequence[dict]) -> dict | None:
    """The longest run of sections with no instrumental section between them, as measured (before the bar snap)."""
    runs = [list(group) for sung, group in groupby(sections, key=lambda s: s["kind"] != "instrumental") if sung]
    if not runs:
        return None
    best = max(runs, key=lambda run: run[-1]["measured"][1] - run[0]["measured"][0])
    start, end = best[0]["measured"][0], best[-1]["measured"][1]
    return {"start": start, "end": end, "duration_s": round(end - start, 2),
            "on_bars": [best[0]["start"], best[-1]["end"]], "labels": [s["label"] for s in best]}


def _against(level: float, first: float) -> tuple[float | None, str]:
    if level <= 0 or first <= 0:
        return None, "unknown"
    difference = round(20.0 * float(np.log10(level / first)), 1)
    if abs(difference) < SAME_DB:
        return difference, "same"
    return difference, "louder" if difference > 0 else "quieter"


def _repeats(sections: Sequence[dict]) -> list[dict]:
    """Each lyric section sung more than once, every time it comes against the first time."""
    by_label: dict[str, list[dict]] = {}
    for section in sections:
        if section.get("occurrence"):
            by_label.setdefault(section["label"], []).append(section)
    out = []
    for label, times in by_label.items():
        if len(times) < 2:
            continue
        first = times[0]["rest_level"]
        rows = []
        for n, section in enumerate(times):
            difference, differs = _against(section["rest_level"], first)
            rows.append({"id": section["id"], "start": section["start"], "duration_s": section["duration_s"],
                         "voice_share": section["voice_share"], "rest_level": section["rest_level"],
                         "vs_first_db": 0.0 if n == 0 else difference, "differs": "first" if n == 0 else differs})
        out.append({"label": label, "times": rows})
    return out


def pacing(sections: Sequence[dict], voice: LeadVoice, lines: Sequence[TimedLine], total: float,
           gap_s: float) -> dict:
    """The whole song's pacing record; every length in it is as measured (where the voice starts and stops), not
    snapped to the bar."""
    sung_s = round(sum(_measured_s(s) for s in sections if s["kind"] != "instrumental"), 2)
    voice_on_s = round(float(voice.on.sum()) * FRAME_S, 2)
    share = (lambda seconds: round(seconds / total, 3) if total > 0 else 0.0)
    first_line = min(lines, key=lambda x: x.start) if lines else None
    return {"total_s": round(total, 2), "sung_s": sung_s, "sung_share": share(sung_s),
            "instrumental_s": round(total - sung_s, 2), "instrumental_share": share(total - sung_s),
            "voice_on_s": voice_on_s, "voice_on_share": share(voice_on_s),
            "first_voice_s": voice.regions[0][0] if voice.regions else None,
            "first_line": {"id": first_line.id, "label": first_line.label, "start": first_line.start}
            if first_line else None,
            "longest_sung": _longest_sung(sections), "story_gap_threshold_s": gap_s,
            "story_gaps": _gaps(sections, gap_s), "repeats": _repeats(sections)}
