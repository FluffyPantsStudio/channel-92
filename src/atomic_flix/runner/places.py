"""Where the runner may read from: the film's own folder, and for graphs also the kit's graph folder.

Every input a job uploads (opening and closing stills, audio, image and video slots) must resolve inside the film
folder, and every graph inside the film folder or the kit's `workflows/` folder; anything else is refused with the
offending path, before planning writes a job file and again before a planned job is sent (a job file can be edited
in between). Links are followed before the check, so a link out of the film counts as outside.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .names import KIT_MAPS
from .template import TemplateError


def inside(path: str | Path, roots: Iterable[str | Path], what: str) -> Path:
    """PATH resolved, if it lies in one of ROOTS; TemplateError naming WHAT and PATH otherwise."""
    folders = [Path(root).resolve() for root in roots]
    resolved = Path(path).resolve()
    if any(resolved == folder or folder in resolved.parents for folder in folders):
        return resolved
    raise TemplateError(f"{what} {path} is outside {' and '.join(str(f) for f in folders)}; refused")


def graph_file(film_dir: str | Path, graph: str | Path, what: str = "graph") -> Path:
    """The graph's path (a relative one is read from the film folder), inside the film or the kit's graphs."""
    given = Path(graph)
    aim = inside(given if given.is_absolute() else Path(film_dir) / given, (film_dir, KIT_MAPS), what)
    if not aim.is_file():
        raise TemplateError(f"{what}: no graph file at {aim}")
    return aim


def film_file(film_dir: str | Path, relative: object, what: str) -> Path:
    """RELATIVE resolved inside the film folder; TemplateError for anything but a relative path with no `..` part that
    stays inside FILM_DIR once links are followed. Readers of a film's own files (lint's book, the eval) use this, so
    a path written into film.json or a task never makes them read outside the film."""
    if not isinstance(relative, (str, Path)) or not str(relative).strip():
        raise TemplateError(f"{what}: {relative!r} is not a path")
    given = Path(relative)
    if given.anchor or ".." in given.parts:
        raise TemplateError(f"{what} {relative} must be a relative path inside the film folder, without `..`; refused")
    return inside(Path(film_dir) / given, (film_dir,), what)


def input_file(film_dir: str | Path, relative: str | Path, what: str) -> Path:
    """An input's path inside the film folder (RELATIVE is read from the film folder)."""
    return inside(Path(film_dir) / relative, (film_dir,), what)
