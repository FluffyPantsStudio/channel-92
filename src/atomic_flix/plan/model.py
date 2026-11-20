"""The plan stage's inputs: timed lyric lines, the beat grid with its bar phase, and the shot list.

File formats follow the core spec: `analysis/voice-lines.json` (timing stage) and `analysis/pulse.json` (bars stage).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

KINDS = ("vocal", "mute", "cutaway")
ON_GRID_TOLERANCE = 0.02      # seconds: a cut this close to a grid point counts as on it


class PlanError(ValueError):
    """The inputs cannot be planned; the message says which shot or line and why."""


@dataclass(frozen=True)
class Line:
    """One sung line as the timing stage measured it (song seconds)."""

    key: str
    part: str
    text: str
    start: float | None
    end: float | None
    gaps: tuple[tuple[float, float], ...] = ()
    provenance: str = "level"
    flags: tuple[str, ...] = ()

    @property
    def timed(self) -> bool:
        return self.start is not None and self.end is not None


@dataclass(frozen=True)
class Pulse:
    """The beat grid. The bar's one falls on beats whose index mod 4 equals `downbeat_slot`."""

    beats: tuple[float, ...]
    downbeat_slot: int = 0
    grounds: Mapping = field(default_factory=lambda: MappingProxyType({}))

    @property
    def ones(self) -> tuple[float, ...]:
        return tuple(t for k, t in enumerate(self.beats) if k % 4 == self.downbeat_slot % 4)

    @property
    def thirds(self) -> tuple[float, ...]:
        return tuple(t for k, t in enumerate(self.beats) if k % 4 == (self.downbeat_slot + 2) % 4)

    def grid_of(self, time: float) -> str:
        """'one', 'three', 'beat' or 'off' for a song time."""
        for name, ties in (("one", self.ones), ("three", self.thirds), ("beat", self.beats)):
            if any(abs(point - time) <= ON_GRID_TOLERANCE for point in ties):
                return name
        return "off"


@dataclass(frozen=True)
class ShotSpec:
    """One shot as the person wrote it. Shots name lines, never seconds (except a time the person sets in `at`)."""

    key: str
    kind: str
    sings: tuple[str, ...] = ()
    still: str | None = None
    closing_still: str | None = None
    setup: str | None = None
    crop: float | None = None
    framing: str | None = None
    place: str | None = None
    goal: str | None = None
    acts: Mapping[str, str] = field(default_factory=dict)
    beats: tuple[str, ...] = ()
    cam_move: str | None = None
    pin: str | None = None
    figures: bool | None = None
    count: int = 1
    at: str | None = None
    late_in: float | None = None
    outfit: str | None = None
    scene: str | None = None        # shots of one scene share a master still, prop references, aspect and look
    takes: int | None = None
    extra: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise PlanError(f"{self.key}: type {self.kind!r} is not one of {', '.join(KINDS)}")
        if self.kind == "vocal" and not self.sings:
            raise PlanError(f"{self.key}: a vocal shot names the lines she sings")

    @property
    def has_person(self) -> bool:
        if self.kind in ("vocal", "mute"):
            return True
        return bool(self.figures)

    @property
    def still_path(self) -> str:
        return self.still or f"stills/{self.key}.png"


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def lines_from_json(data: Mapping) -> list[Line]:
    """Lines from the timing stage's `voice-lines.json` mapping."""
    out = []
    for row in data.get("lines", []):
        out.append(Line(key=row["id"], part=row.get("part", "lead"), text=row.get("text", ""),
                        start=row.get("start"), end=row.get("end"),
                        gaps=tuple(tuple(gap) for gap in row.get("gaps", [])),
                        provenance=row.get("provenance", "level"), flags=tuple(row.get("flags", []))))
    return out


def pulse_from_json(data: Mapping, downbeat_slot: int | None = None) -> Pulse:
    """The grid from `pulse.json`; a person's `downbeat_slot` from film.json overrides the stage's guess."""
    beats = tuple(float(t) for t in data["beats"])
    downbeat_slot = int(data.get("downbeat_slot", 0)) if downbeat_slot is None else int(downbeat_slot)
    return Pulse(beats=beats, downbeat_slot=downbeat_slot, grounds=MappingProxyType(dict(data.get("grounds", {}))))
