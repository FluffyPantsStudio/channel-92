"""What every film step shares: reading the film folder, its shot list and plan, and a plain error."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..plan import PlanError, ShotSpec, parse_shot_list
from ..project import FilmFolder, ProjectError, read_film
from ..project.standing import write_atomic
from ..formats import stamped

LINEUP_FILE = "shots.txt"


class StepError(Exception):
    """A film step cannot go on; the message says what is missing and what to do."""


@dataclass(frozen=True)
class Film:
    """One film folder, read once per step."""

    folder: FilmFolder
    data: dict

    @classmethod
    def open(cls, root: Path | str) -> "Film":
        folder = FilmFolder(Path(root))
        if not folder.film.is_file():
            raise StepError(f"{folder.root} is not a film folder (no film.json); make one with `atomic-flix new`")
        try:
            return cls(folder, read_film(folder))
        except ProjectError as problem:
            raise StepError(str(problem)) from None

    @property
    def root(self) -> Path:
        return self.folder.root

    def path(self, relative: str) -> Path:
        return self.root / relative

    def stem(self, name: str) -> Path | None:
        """The stem file named in film.json, when it is there."""
        relative = (self.data.get("stems") or {}).get(name)
        if not relative:
            return None
        path = self.path(relative)
        return path if path.is_file() else None

    @property
    def lineup_rows(self) -> Path:
        return self.path(self.data.get("lineup_rows") or LINEUP_FILE)

    def shots(self) -> list[ShotSpec]:
        if not self.lineup_rows.is_file():
            raise StepError(f"no shot list at {self.folder.relative(self.lineup_rows)}; write one shot per paragraph "
                            "(see docs/quickstart.md)")
        try:
            return parse_shot_list(self.lineup_rows.read_text(encoding="utf-8"))
        except PlanError as problem:
            raise StepError(f"{self.folder.relative(self.lineup_rows)}: {problem}") from None

    def tasks(self) -> dict[str, dict]:
        """Every shot's plan task in film order; refuses when the plan is missing."""
        found = {}
        for shot in self.shots():
            path = self.path(f"plan/{shot.key}.task.json")
            if not path.is_file():
                raise StepError(f"{shot.key} has no plan (plan/{shot.key}.task.json); run `atomic-flix plan`")
            found[shot.key] = read_json(path)
        return found

    def cuts(self) -> list[dict]:
        path = self.path("plan/cuts.json")
        if not path.is_file():
            raise StepError("no plan/cuts.json; run `atomic-flix plan`")
        return list(read_json(path)["cuts"])

    @property
    def fps(self) -> int:
        return int(self.data.get("fps") or 24)

    @property
    def frame(self) -> tuple[int, int]:
        width, height = self.data.get("frame") or (1280, 704)
        return int(width), int(height)

    def save(self, data: dict) -> "Film":
        """Write film.json (only the steps that say so do this) and return the film as now written."""
        data = stamped("film", data)
        write_atomic(self.folder.film, json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        return Film(self.folder, data)


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data: Any, kind: str | None = None) -> Path:
    """Write JSON atomically; with `kind`, the data gets its format tag first (`formats.py`)."""
    path = Path(path)
    data = stamped(kind, data) if kind else data
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    return path


def relative_to(path: Path, folder: Path) -> str:
    """PATH written relative to FOLDER with forward slashes (for files that point at other files)."""
    return Path(os.path.relpath(Path(path).resolve(), Path(folder).resolve())).as_posix()


def parser(verb: str, about: str) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog=f"atomic-flix {verb}", description=about,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)


def film_argument(parser_: argparse.ArgumentParser) -> None:
    parser_.add_argument("film", type=Path, help="the film's folder (the one holding film.json)")
