"""Each render's slice of the song, its whole-second steps, the phrases used to place it, and its voice gate."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from .model import Line

HEAD = 0.25            # a render starts this long before its shot comes on; those frames are never shown
RUN_UP_S = 0.7          # and a vocal render at least this long before her first sound
TAIL = 0.3             # and runs at least this long past the cut that leaves it
MIN_SECONDS, MAX_SECONDS = 4, 15
SHORT_REST = 0.9       # a rest shown for less than this folds into the step beside it
SILENT_SLACK = 0.4     # a rest step may hold this much singing at its edge
WORDS_AFTER = 0.5      # a sung step may end this long before its line's last word
PHRASE_JOIN = 0.45     # lines closer than this place as one phrase
GATE_BEFORE, GATE_AFTER, GATE_MIN = 0.07, 0.25, 0.03
GATE_CLEAR = 0.04      # the gate, fade included, stays this far from a neighbouring line


@dataclass(frozen=True)
class Step:
    start: int
    end: int
    lines: tuple[str, ...] = ()
    folded_head: bool = False
    folded_tail: bool = False


def slice_bounds(shown_at: tuple[float, float], first: float | None) -> tuple[float, int, list[str]]:
    """(slice_start, whole seconds, notes) covering the shot plus a tail, with the lead-in before her first sound."""
    notes = []
    slice_start = shown_at[0] - HEAD
    if first is not None:
        slice_start = min(slice_start, first - RUN_UP_S)
    slice_start = round(max(0.0, slice_start), 3)
    needed = shown_at[1] + TAIL - slice_start
    seconds = max(MIN_SECONDS, math.ceil(needed - 1e-6))
    if seconds > MAX_SECONDS:
        notes.append(f"the shot needs {needed:.1f} s of render, over the {MAX_SECONDS} s limit: split it or move a "
                     f"cut; the render holds {MAX_SECONDS} s")
        seconds = MAX_SECONDS
    return slice_start, seconds, notes


def _between(prev_end: float, next_start: float) -> int:
    """The boundary between two sung items: the whole second nearest the gap's middle, inside the gap if one is."""
    middle = (prev_end + next_start) / 2
    inside = [s for s in range(math.ceil(prev_end), math.floor(next_start) + 1)]
    if inside:
        return min(inside, key=lambda s: abs(s - middle))
    return round(middle)


def whole_second_steps(items: Sequence[tuple[float, float, str]], seconds: int,
                       shown: tuple[float, float]) -> list[Step]:
    """Steps over 0..seconds for sung items (start, end, line id) in slice time.

    A rest shown for under SHORT_REST folds into the step beside it; lines too close for a whole second between them
    share a step."""
    if not items:
        return [Step(0, seconds)]
    items = sorted(items)
    head = round(items[0][0])
    if head - items[0][0] > SILENT_SLACK:
        head -= 1
    tail = round(items[-1][1])
    if items[-1][1] - tail > WORDS_AFTER:
        tail += 1
    keep_head = items[0][0] - shown[0] >= SHORT_REST and head > 0
    keep_tail = shown[1] - items[-1][1] >= SHORT_REST and tail < seconds
    stretches: list[list] = []                    # [end boundary, line ids] in order; a rest has no ids
    if keep_head:
        stretches.append([head, ()])
    for index, (_, end, key) in enumerate(items):
        boundary = _between(end, items[index + 1][0]) if index + 1 < len(items) else (tail if keep_tail else seconds)
        stretches.append([boundary, (key,)])
    if keep_tail:
        stretches.append([seconds, ()])
    steps: list[list] = []
    start, awaiting = 0, ()
    for boundary, keys in stretches:
        boundary = min(max(boundary, start), seconds)
        if boundary <= start:                    # no room for a whole second: its lines join the step beside it
            if steps:
                steps[-1][2] = steps[-1][2] + keys
            else:
                awaiting = awaiting + keys
            continue
        steps.append([start, boundary, awaiting + keys])
        start, awaiting = boundary, ()
    if not steps:
        steps = [[0, seconds, awaiting]]
    steps[-1][1] = seconds
    silent_before = items[0][0] > 0 and not keep_head
    silent_after = items[-1][1] < seconds and not keep_tail
    return [Step(a, b, keys, folded_head=bool(keys) and index == 0 and silent_before,
                 folded_tail=bool(keys) and index == len(steps) - 1 and silent_after)
            for index, (a, b, keys) in enumerate(steps)]


def spread_steps(count: int, seconds: int, shown: tuple[float, float]) -> list[tuple[int, int]]:
    """Whole-second steps for `count` events spread over what the cut shows (slice time), the last to the end."""
    count = max(1, count)
    span = max(shown[1] - shown[0], 0.0)
    marks = sorted({min(seconds - 1, max(1, round(shown[0] + span * k / count))) for k in range(1, count)})
    bounds = [0] + [m for m in marks if 0 < m < seconds] + [seconds]
    return list(zip(bounds, bounds[1:]))


def phrases_in_slice(lines: Sequence[Line], slice_start: float) -> list[list]:
    """Her lines in slice time, joined across gaps under PHRASE_JOIN, for placing the render by sound."""
    vocal_spans: list[list] = []
    for line in sorted(lines, key=lambda x: x.start):
        start, end = round(line.start - slice_start, 2), round(line.end - slice_start, 2)
        if vocal_spans and start - vocal_spans[-1][1] < PHRASE_JOIN:
            vocal_spans[-1][1] = max(vocal_spans[-1][1], end)
            vocal_spans[-1][2] = f"{vocal_spans[-1][2]} {line.text}".strip()
        else:
            vocal_spans.append([start, end, line.text])
    return vocal_spans


def gate_span(keys: Sequence[str], lines: Mapping[str, Line]) -> tuple[float, float]:
    """Song seconds the voice is heard: her first line's start to her last line's end, widened a little but never into
    a neighbouring line."""
    own = [lines[key] for key in keys]
    first = min(line.start for line in own)
    last = max(line.end for line in own)
    rivals = [line for key, line in lines.items() if key not in keys and line.timed]
    before = [line.end for line in rivals if line.end <= first + 1e-9]
    after = [line.start for line in rivals if line.start >= last - 1e-9]
    room_before = (first - max(before)) - GATE_CLEAR if before else GATE_BEFORE
    room_after = (min(after) - last) - GATE_CLEAR if after else GATE_AFTER
    widen_before = min(GATE_BEFORE, max(0.0, room_before))
    widen_after = min(GATE_AFTER, max(0.0, room_after))
    if room_before >= GATE_MIN:
        widen_before = max(widen_before, GATE_MIN)
    if room_after >= GATE_MIN:
        widen_after = max(widen_after, GATE_MIN)
    return round(first - widen_before, 3), round(last + widen_after, 3)
