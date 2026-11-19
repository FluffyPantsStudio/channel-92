"""Where each shot comes on. Cuts are planned first, on the bar's one, else its three, else any beat; every render's
slice is derived from them afterwards, so the footage never decides where a cut falls.

The film's first cut is the lead, at LEAD seconds of song: the first render starts at the song's 0, and a render's
opening frames are never shown, so the picture can only begin once they have passed. A song sung before the lead
cannot be planned and is refused with the reason."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from .model import Line, PlanError, Pulse, ShotSpec
from .slices import HEAD

MIN_SHOT = 1.6           # no shot shorter than this
ENTER_EARLY = 1.3        # a vocal shot may come on this long before her first sound
ENTER_LATE = 0.12        # and up to this long after it on a bar line
ENTER_LATE_BEAT = 0.6    # or this late on any beat when no bar line is in reach
THREE_COST = 0.25        # seconds of distance a three gives away to a one when entering
AFTER_SOUND_WEIGHT = 3.0  # coming on after her first sound costs three times as much as coming on before it
LEAVE_EARLY = 0.3        # a vocal shot may be left this long before her last sound has died
LEAVE_WITHIN = 2.2       # the first bar line once she is done, within this
PIN_EXIT = 1.0           # a fully pinned vocal shot exits within this of her last sound (rule P1)
SNAP = 0.6               # a time set by the person snaps to a one or three this close
FREE_SNAP = 1.1          # a cut between two cutaways looks this far for a bar line
LEAD = HEAD               # the first cut: the first render's opening frames pass before it
_SECONDS = re.compile(r"^\d+(\.\d+)?$")


@dataclass(frozen=True)
class Cut:
    key: str
    at: float
    grid: str
    note: str = ""


def first_sound(shot: ShotSpec, lines: Mapping[str, Line]) -> float:
    return min(lines[key].start for key in shot.sings)


def last_sound(shot: ShotSpec, lines: Mapping[str, Line]) -> float:
    return max(lines[key].end for key in shot.sings)


def pinned(shot: ShotSpec) -> bool:
    return (shot.pin or "full") == "full" if shot.kind == "vocal" else shot.pin == "full"


def _inside(ties: Sequence[float], low: float, high: float) -> list[float]:
    return [t for t in ties if low - 1e-9 <= t <= high + 1e-9]


def _snap(pulse: Pulse, aim: float, reach: float) -> tuple[float, str] | None:
    near = [(abs(t - aim), t, name) for name, grid in (("one", pulse.ones), ("three", pulse.thirds))
            for t in _inside(grid, aim - reach, aim + reach)]
    if not near:
        return None
    _, time, name = min(near)
    return time, name


def _enter(pulse: Pulse, first: float, floor: float) -> tuple[float, str]:
    """On before her first sound when a bar line allows; a one is worth a little more than a three."""
    low = max(floor, first - ENTER_EARLY)
    options = []
    for name, grid in (("one", pulse.ones), ("three", pulse.thirds)):
        for t in _inside(grid, low, first + ENTER_LATE):
            distance = first - t if t <= first else AFTER_SOUND_WEIGHT * (t - first)
            options.append((distance + (THREE_COST if name == "three" else 0.0), t, name))
    if options:
        _, time, name = min(options)
        return time, name
    beats = _inside(pulse.beats, floor, first + ENTER_LATE_BEAT)
    if beats:
        return min(beats, key=lambda t: (t > first, abs(t - first))), "beat"
    return max(floor, first - 0.4), "off"


def _earliest(pulse: Pulse, low: float, high: float) -> tuple[float, str] | None:
    """The earliest bar line (one or three) in the range, else the earliest beat."""
    bars = sorted((t, name) for name, grid in (("one", pulse.ones), ("three", pulse.thirds))
                  for t in _inside(grid, low, high))
    if bars:
        return bars[0]
    beats = _inside(pulse.beats, low, high)
    return (beats[0], "beat") if beats else None


def _leave(pulse: Pulse, last: float, floor: float, limit: float, is_pinned: bool) -> tuple[float, str, str]:
    """Leaving her: the first bar line once her last sound is nearly over. A pinned shot may not hold past PIN_EXIT."""
    low = max(floor, last - LEAVE_EARLY)
    natural = _earliest(pulse, low, min(limit, last + LEAVE_WITHIN))
    if not is_pinned or (natural and natural[0] - last <= PIN_EXIT):
        if natural:
            return natural[0], natural[1], ""
        return min(limit, max(low, last)), "off", "OFF GRID: no beat in reach after her last sound"
    bars = _inside(pulse.ones + pulse.thirds, low, last + PIN_EXIT)
    beats = _inside(pulse.beats, low, last + PIN_EXIT)
    was = f"{natural[0]:.2f} ({natural[1]})" if natural else "no bar line"
    if bars:
        time = max(bars)
        grid = pulse.grid_of(time)
    elif beats:
        time, grid = max(beats), "beat"
    else:
        time, grid = min(limit, last + PIN_EXIT), "off"
    note = (f"moved earlier from {was} to {time:.2f}: a pinned shot exits within {PIN_EXIT:.1f} s of her last sound "
            "(P1)")
    return time, grid, note


def _person_time(pulse: Pulse, value: float) -> tuple[float, str, str]:
    snapped = _snap(pulse, value, SNAP)
    if snapped:
        return snapped[0], snapped[1], f"set by the person ({value:g})"
    return value, "off", f"OFF GRID: set by the person ({value:g}); no one or three within {SNAP} s"


def _anchor(index: int, shots: Sequence[ShotSpec], lines: Mapping[str, Line], pulse: Pulse,
            floor: float, ends_at: float) -> tuple[float, str, str] | None:
    """The cut that brings shot `index` on, or None when it only depends on its neighbours (a free cut)."""
    shot, before = shots[index], shots[index - 1]
    if shot.at is not None:
        if _SECONDS.match(shot.at.strip()):
            return _person_time(pulse, float(shot.at))
        if shot.at not in lines:
            raise PlanError(f"{shot.key}: at {shot.at!r} is neither seconds nor a line id")
        time, grid = _enter(pulse, lines[shot.at].start, floor)
        return time, grid, f"on before line {shot.at}"
    if shot.kind == "vocal" and shot.late_in is not None:
        aim = first_sound(shot, lines) + shot.late_in
        snapped = _snap(pulse, aim, SNAP)
        if snapped:
            return snapped[0], snapped[1], f"late in: her first sound plays over {before.key}"
        return aim, "off", "OFF GRID: late in, no bar line near"
    if shot.kind == "vocal" and before.kind == "vocal":
        last = last_sound(before, lines)
        limit = first_sound(shot, lines) + ENTER_LATE
        if pinned(before):
            limit = min(limit, last + PIN_EXIT)
        low = max(floor, last - LEAVE_EARLY)
        found = _earliest(pulse, low, limit) or _earliest(pulse, low, first_sound(shot, lines) + ENTER_LATE_BEAT)
        if found:
            note = ""
            if pinned(before) and found[0] - last > PIN_EXIT:
                note = f"{before.key} is pinned and holds {found[0] - last:.2f} s past her last sound"
            return found[0], found[1], note
        return low, "off", f"OFF GRID: no beat in the silence between {before.key} and {shot.key}"
    if shot.kind == "vocal":
        time, grid = _enter(pulse, first_sound(shot, lines), floor)
        return time, grid, "" if grid != "off" else "OFF GRID: no beat near her first sound"
    if before.kind == "vocal":
        return _leave(pulse, last_sound(before, lines), floor, ends_at, pinned(before))
    return None


def _snap_between(pulse: Pulse, aim: float, low: float, high: float) -> tuple[float, str] | None:
    """The bar line nearest AIM within FREE_SNAP that also lies in [low, high]."""
    near = [(abs(t - aim), t, name) for name, grid in (("one", pulse.ones), ("three", pulse.thirds))
            for t in _inside(grid, max(low, aim - FREE_SNAP), min(high, aim + FREE_SNAP))]
    if not near:
        return None
    _, time, name = min(near)
    return time, name


def _fill_free(cuts: list, shots: Sequence[ShotSpec], pulse: Pulse, ends_at: float) -> None:
    """Cuts between two cutaways share the time between their anchors evenly, each on the nearest bar line that
    leaves every shot of the run at least MIN_SHOT seconds; with no such bar line the cut stays off grid."""
    index = 1
    while index < len(cuts):
        if cuts[index] is not None:
            index += 1
            continue
        stop = index
        while stop < len(cuts) and cuts[stop] is None:
            stop += 1
        left = cuts[index - 1][0]
        right = cuts[stop][0] if stop < len(cuts) else ends_at
        span = stop - index + 1
        if right - left < MIN_SHOT * span - 1e-9:
            keys = ", ".join(shot.key for shot in shots[index - 1:stop])
            raise PlanError(f"{keys} share {right - left:.2f} s from {left:.2f} to {right:.2f}: {span} shots need at "
                            f"least {MIN_SHOT * span:.1f} s ({MIN_SHOT} s each); drop a shot or give them more song")
        for offset, position in enumerate(range(index, stop), start=1):
            aim = left + (right - left) * offset / span
            low = cuts[position - 1][0] + MIN_SHOT
            high = right - MIN_SHOT * (stop - position)
            snapped = _snap_between(pulse, aim, low, high)
            if snapped:
                cuts[position] = (snapped[0], snapped[1], "")
                continue
            placed = min(max(aim, low), high)
            grid = pulse.grid_of(placed)
            cuts[position] = (placed, grid, f"{'OFF GRID' if grid == 'off' else 'on a ' + grid}: no bar line near "
                                            f"that leaves each shot {MIN_SHOT} s")
        index = stop


def plan_cuts(shots: Sequence[ShotSpec], lines: Mapping[str, Line], pulse: Pulse, ends_at: float) -> list[Cut]:
    """One cut per shot: the time it comes on. The first shot is on from the lead (LEAD seconds)."""
    if not shots:
        raise PlanError("the shot list is empty")
    for shot in shots:
        for key in shot.sings:
            if key not in lines:
                raise PlanError(f"{shot.key}: sings {key}, which is not in the line table")
            if not lines[key].timed:
                raise PlanError(f"{shot.key}: line {key} has no time; fix it before planning")
    sung_from = min((lines[key].start for shot in shots for key in shot.sings), default=None)
    if sung_from is not None and sung_from < LEAD:
        raise PlanError(f"the song is sung from {sung_from:.2f} s, before the film's first frame at {LEAD:.2f} s "
                        f"(the first render's opening frames are never shown): the film cannot open on her first "
                        "sound; trim silence onto the song's head or start the song later")
    lead_note = (f"lead: the film opens at {LEAD:.2f} s, once the first render's opening frames have passed; the "
                 "song before it is not in the film")
    cuts: list = [(LEAD, "lead", lead_note)] + [None] * (len(shots) - 1)
    known = 0
    for index in range(1, len(shots)):
        floor = cuts[known][0] + MIN_SHOT * (index - known)
        found = _anchor(index, shots, lines, pulse, floor, ends_at)
        if found is not None:
            cuts[index] = found
            known = index
    _fill_free(cuts, shots, pulse, ends_at)
    result = [Cut(key=shot.key, at=round(time, 3), grid=grid, note=note)
              for shot, (time, grid, note) in zip(shots, cuts)]
    for left, right in zip(result, result[1:]):
        if right.at <= left.at:
            raise PlanError(f"two cuts at the same time or out of order: {left.key} at {left.at:.2f}, "
                            f"{right.key} at {right.at:.2f}")
    if result[-1].at >= ends_at:
        raise PlanError(f"{result[-1].key} comes on at {result[-1].at:.2f}, after the song ends ({ends_at:.2f})")
    return result
