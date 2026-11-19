"""The same numbers as the baseline, measured on one film from its ledger, folders and standing.json."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

from ..gates import parse_time
from ..project import FilmFolder, load_standing
from .ledger import JobLogRow, read_job_log

HOUR = 3600.0
RENDER_KINDS = ("vocal", "mute", "cutaway")
KIND_GROUPS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "gpu_hours_vocal": ("vocal",),
    "gpu_hours_cutaway": ("cutaway", "mute"),
    "gpu_hours_still": ("still", "edit"),
    "gpu_hours_test": ("test",),
})
KNOWN_KINDS = frozenset(kind for kinds in KIND_GROUPS.values() for kind in kinds)
CUT_NAME = re.compile(r"v\d+\.mp4")


@dataclass(frozen=True)
class Measured:
    value: float | None
    note: str = ""


def _busy(logged: Iterable[JobLogRow]) -> tuple[float, int]:
    """GPU seconds of ENTRIES (wall time where the GPU time is missing) and how many used wall time."""
    total, walled = 0.0, 0
    for entry in logged:
        if entry.state == "planned":
            continue
        if entry.gpu_seconds is not None:
            total += entry.gpu_seconds
        elif entry.wall_seconds is not None:
            total += entry.wall_seconds
            walled += 1
    return total, walled


def _hours(logged: list[JobLogRow]) -> Measured:
    seconds, walled = _busy(logged)
    note = f"{walled} job(s) without GPU time counted at wall time, an upper bound" if walled else ""
    return Measured(seconds / HOUR, note)


def _per_shot(done: list[JobLogRow], kinds: tuple[str, ...]) -> Measured:
    counts: dict[str, int] = defaultdict(int)
    for entry in done:
        if entry.kind in kinds and entry.shot:
            counts[entry.shot] += 1
    if not counts:
        return Measured(None, "no finished renders of this kind")
    return Measured(sum(counts.values()) / len(counts))


def _job_log_metrics(logged: tuple[JobLogRow, ...], finished: float | None) -> dict[str, Measured]:
    if not logged:
        empty = Measured(None, "the ledger is empty")
        keys = ("gpu_hours_total", *KIND_GROUPS, "vocal_renders_per_shot", "cutaway_renders_per_shot",
                "renders_per_finished_second", "rendered_to_finished")
        return {key: empty for key in keys}
    total = _hours(list(logged))
    extra = other_kinds(logged)
    if extra:
        joined = "; ".join(part for part in (total.note, "includes job kinds the first film had no row for: "
                                             + ", ".join(extra)) if part)
        total = Measured(total.value, joined)
    found = {"gpu_hours_total": total}
    for key, kinds in KIND_GROUPS.items():
        found[key] = _hours([e for e in logged if e.kind in kinds])
    done = [e for e in logged if e.state == "done" and e.kind in RENDER_KINDS]
    found["vocal_renders_per_shot"] = _per_shot(done, ("vocal",))
    found["cutaway_renders_per_shot"] = _per_shot(done, ("cutaway", "mute"))
    if not finished:
        found["renders_per_finished_second"] = Measured(None, "finished_seconds not in the record")
        found["rendered_to_finished"] = Measured(None, "finished_seconds not in the record")
        return found
    found["renders_per_finished_second"] = Measured(len(done) / finished)
    lengths = [e.video_seconds for e in done if e.video_seconds is not None]
    if not lengths:
        found["rendered_to_finished"] = Measured(None, "no ledger line carries video_seconds")
    else:
        short = len(done) - len(lengths)
        note = f"{short} render(s) without video_seconds left out, a lower bound" if short else ""
        found["rendered_to_finished"] = Measured(sum(lengths) / finished, note)
    return found


def _days(created: str, accepted: str | None) -> Measured:
    if accepted is None:
        return Measured(None, "the person has not accepted v1 yet")
    days = (parse_time(accepted).date() - parse_time(created).date()).days
    return Measured(float(days))


def other_kinds(logged: Iterable[JobLogRow]) -> tuple[str, ...]:
    """Job kinds in the ledger that have no counterpart in the first film (counted in the total only)."""
    return tuple(sorted({e.kind for e in logged} - KNOWN_KINDS))


def measure_film(film: FilmFolder | Path) -> Mapping[str, Measured]:
    """Every metric of METRICS for the film in folder FILM."""
    folder = film if isinstance(film, FilmFolder) else FilmFolder(Path(film))
    standing = load_standing(folder)
    record = standing.record
    logged = read_job_log(folder.job_log).logged
    found = _job_log_metrics(logged, record.get("finished_seconds"))
    cuts = [p for p in (folder.root / "cuts").glob("v*.mp4") if CUT_NAME.fullmatch(p.name)]
    found["builds"] = Measured(float(len(cuts))) if cuts else Measured(None, "no cuts yet")
    v1 = standing.gates.record("v1")
    accepted = v1.latest.at if v1.state == "passed" and v1.latest else None
    found["days_to_acceptance"] = _days(standing.created, accepted)
    names = {"reshoot_passes": "reshoot_passes", "driver_calls": "calls", "cost_usd": "cost_usd",
             "driver_median_tokens": "median_tokens"}
    for key, field in names.items():
        value = record.get(field)
        found[key] = Measured(None if value is None else float(value), "" if value is not None else
                              f"{field} not in the record")
    return MappingProxyType(found)
