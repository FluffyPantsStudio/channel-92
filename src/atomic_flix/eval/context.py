"""Everything an eval reads from a film folder, read once. A part that cannot be read keeps the reason instead, so
the rows that needed it come out unchecked with that reason, never silently passed. Every path the film's files name
is read only inside the film folder (`runner.places.film_file`)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from ..plan import PlanError, ShotSpec, parse_shot_list
from ..runner.jobs import WAITING, JobStore
from ..runner.places import film_file
from ..runner.template import TemplateError
from .inputs import input_table


@dataclass(frozen=True)
class Part:
    """One part of the film as read: its value, or why it could not be read."""

    value: Any = None
    problem: str | None = None

    @property
    def ok(self) -> bool:
        return self.problem is None


@dataclass(frozen=True)
class Context:
    root: Path
    film: Part
    shots: Part
    standing: Part
    jobs: Part
    table: Mapping[str, str] = MappingProxyType({})

    def path(self, relative: str) -> Path:
        return self.root / relative

    def read_json(self, relative: str) -> Part:
        return read_json_part(self.root / relative, relative)

    def inside(self, relative: object, what: str) -> Part:
        """A path the film's files name, resolved inside the film folder, or why it is refused (never read)."""
        try:
            return Part(film_file(self.root, relative, what))
        except TemplateError as problem:
            return Part(problem=str(problem))

    def film_field(self, name: str, kind: type, empty: Any) -> Part:
        """film.json's NAME when it has the shape KIND (EMPTY when absent), or why it cannot be used."""
        if not self.film.ok:
            return Part(problem=self.film.problem)
        value = self.film.value.get(name)
        if value is None:
            return Part(empty)
        if not isinstance(value, kind):
            return Part(problem=f"film.json {name} must be a {kind.__name__}, not {type(value).__name__}")
        return Part(value)

    @property
    def sent_jobs(self) -> list[dict]:
        """Jobs that reached a host: every job file past `planned`."""
        return [job for job in self.jobs.value or [] if job.get("state") != WAITING]


def read_json_part(path: Path, name: str) -> Part:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Part(problem=f"{name} is missing")
    except (OSError, ValueError) as problem:
        return Part(problem=f"{name} cannot be read: {problem}")
    if not isinstance(data, dict):
        return Part(problem=f"{name} does not hold one JSON object")
    return Part(data)


def _shots(root: Path, film: Part) -> Part:
    if not film.ok:
        return Part(problem=film.problem)
    name = film.value.get("lineup_rows") or "shots.txt"
    try:
        path = film_file(root, name, "lineup_rows")
        return Part(tuple(parse_shot_list(path.read_text(encoding="utf-8"))))
    except FileNotFoundError:
        return Part(problem=f"{name} is missing")
    except TemplateError as problem:
        return Part(problem=f"the shot list is not read: {problem}")
    except (OSError, PlanError) as problem:
        return Part(problem=f"{name}: {problem}")


def _jobs(root: Path) -> Part:
    try:
        return Part(tuple(JobStore(root).load_all()))
    except (OSError, ValueError) as problem:
        return Part(problem=f"the job files cannot be read: {problem}")


def read_context(root: Path) -> Context:
    root = Path(root)
    film = read_json_part(root / "film.json", "film.json")
    return Context(root=root, film=film, shots=_shots(root, film),
                   standing=read_json_part(root / "standing.json", "standing.json"), jobs=_jobs(root),
                   table=MappingProxyType(input_table(root)))


def shot_list(ctx: Context) -> list[ShotSpec]:
    return list(ctx.shots.value or [])
