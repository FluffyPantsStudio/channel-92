"""The film's state file, `standing.json`: which gate is next, the review rounds, the song's fingerprint and the
record the comparison with the first film reads (finished length, model calls and cost, reshoot passes).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from ..gates import GateBook, GateRefused, parse_time
from .layout import FilmFolder
from ..formats import tag

FORMAT = tag("standing")
EARLY_FORMAT = "atomic-flix/standing/1"  # the same format, as written before the shared tags (formats.py)
CHUNK = 1 << 20

# The record: numbers the person or the driver writes down for the comparison, each with its type and a floor.
RECORD_FIELDS: Mapping[str, type] = MappingProxyType({
    "finished_seconds": float,   # length of the accepted film
    "calls": int,                # model calls of every session of the film (stats/usage.py)
    "cost_usd": float,           # their cost at list prices
    "median_tokens": int,        # the driver's median context per call
    "reshoot_passes": int,       # passes that re-rendered every vocal shot
})


class ProjectError(ValueError):
    """A film folder or its files are not as the kit needs them."""


@dataclass(frozen=True)
class SongPrint:
    """The mix the person approved by ear at gate 2."""

    file: str
    sha256: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "sha256": self.sha256, "size": self.size}


def fingerprint(path: Path, relative: str) -> SongPrint:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
    return SongPrint(file=relative, sha256=digest.hexdigest(), size=Path(path).stat().st_size)


@dataclass(frozen=True)
class BatchApproval:
    """The batch the person's yes at gate 5 covers, copied from plan/budget.json when they said it: how many takes,
    at what frame size, for how many GPU seconds, and how many takes have been drawn on it (planned) since. A plan that
    differs, or more takes than it covers, needs a new answer."""

    takes: int
    size: tuple[int, int]
    busy_s: float
    at: str
    drawn: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"takes": self.takes, "size": list(self.size), "busy_s": self.busy_s, "at": self.at,
                "drawn": self.drawn}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BatchApproval":
        try:
            width, height = data["size"]
            approval = cls(takes=int(data["takes"]), size=(int(width), int(height)), busy_s=float(data["busy_s"]),
                           at=str(data["at"]), drawn=int(data.get("drawn", 0)))
            parse_time(approval.at)
        except (KeyError, TypeError, ValueError):
            raise ProjectError(f"standing.json: gate 5's batch is unreadable: {data!r}") from None
        if approval.takes < 0 or not 0 <= approval.drawn:
            raise ProjectError(f"standing.json: gate 5's batch has negative counts: {data!r}")
        return approval


def check_record(values: Mapping[str, Any]) -> dict[str, float | int]:
    """VALUES checked against RECORD_FIELDS: known names, right types, nothing negative."""
    clean: dict[str, float | int] = {}
    for name, value in values.items():
        kind = RECORD_FIELDS.get(name)
        if kind is None:
            raise ProjectError(f"the record has no field {name!r}; it has {', '.join(RECORD_FIELDS)}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (kind is int and not isinstance(value, int)):
            raise ProjectError(f"record {name} must be a {kind.__name__}, got {value!r}")
        if value < 0:
            raise ProjectError(f"record {name} cannot be negative, got {value!r}")
        clean[name] = kind(value)
    return clean


@dataclass(frozen=True)
class Standing:
    """Everything standing.json holds, read-only."""

    film: str
    created: str
    gates: GateBook
    song: SongPrint | None = None
    record: Mapping[str, float | int] = field(default_factory=lambda: MappingProxyType({}))
    batch: BatchApproval | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "record", MappingProxyType(check_record(self.record)))

    @classmethod
    def new(cls, film: str, created: str) -> "Standing":
        return cls(film=film, created=created, gates=GateBook.empty())

    def with_record(self, **values: Any) -> "Standing":
        return replace(self, record={**self.record, **check_record(values)})

    def to_dict(self) -> dict[str, Any]:
        written = {"format": FORMAT, "film": self.film, "created": self.created, "gates": self.gates.to_dict(),
                   "song": self.song.to_dict() if self.song else None, "record": dict(self.record)}
        if self.batch is not None:
            written["batch"] = self.batch.to_dict()
        return written

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Standing":
        if data.get("format") not in (FORMAT, EARLY_FORMAT):
            raise ProjectError(f"standing.json is not in the format {FORMAT}")
        try:
            parse_time(data.get("created"))
            gates = GateBook.from_dict(data.get("gates") or {})
        except (ValueError, GateRefused) as problem:
            raise ProjectError(f"standing.json: {problem}") from None
        song = data.get("song")
        try:
            printed = SongPrint(str(song["file"]), str(song["sha256"]), int(song["size"])) if song else None
        except (KeyError, TypeError, ValueError):
            raise ProjectError(f"standing.json: the song's fingerprint is unreadable: {song!r}") from None
        batch = BatchApproval.from_dict(data["batch"]) if data.get("batch") else None
        return cls(film=str(data.get("film", "")), created=data["created"], gates=gates, song=printed,
                   record=data.get("record") or {}, batch=batch)


def load_standing(folder: FilmFolder) -> Standing:
    try:
        data = json.loads(folder.standing.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProjectError(f"{folder.standing} is missing; is {folder.root} a film folder?") from None
    except json.JSONDecodeError as problem:
        raise ProjectError(f"{folder.standing} is not JSON: {problem}") from None
    if not isinstance(data, dict):
        raise ProjectError(f"{folder.standing} must hold one JSON object")
    return Standing.from_dict(data)


def write_atomic(path: Path, text: str) -> None:
    """Write TEXT as UTF-8 to a temporary file beside PATH, then swap it in."""
    path = Path(path)
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def save_standing(folder: FilmFolder, standing: Standing) -> None:
    write_atomic(folder.standing, json.dumps(standing.to_dict(), indent=1, ensure_ascii=False) + "\n")
