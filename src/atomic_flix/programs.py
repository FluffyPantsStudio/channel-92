"""The external programs the kit runs (ffmpeg, ffprobe, ntsc-rs-cli, Blender), found on the real PATH.

On Windows a program named by its bare name runs from the current directory before the PATH is searched, so a file
called ffmpeg.exe dropped into a film folder would run in its place. The kit never launches a program by its bare
name: `command_of` swaps the name for an absolute path that `find_program` searched for itself, in
os.environ["PATH"] only, leaving out the current directory and every relative entry, and honouring PATHEXT on
Windows. Each name is looked up once per PATH. A program that sits inside a film folder (one this process opened,
`guard_film`) is refused: a film folder holds a film, never the tools that make it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Sequence

DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD"
_FOUND: dict[tuple[str, str, str], Path | None] = {}
_FILM_ROOTS: set[Path] = set()


class ProgramError(FileNotFoundError):
    """A program the kit needs is not on the PATH, or was found where a program may not be."""


def guard_film(root: Path | str) -> None:
    """Remember ROOT as a film folder: no program inside it is ever run."""
    try:
        _FILM_ROOTS.add(Path(root).resolve())
    except OSError:
        pass


def _film_holding(path: Path) -> Path | None:
    return next((root for root in _FILM_ROOTS if path == root or path.is_relative_to(root)), None)


def checked(path: Path | str, what: str = "") -> Path:
    """PATH made absolute, refused (ProgramError) when it lies inside a film folder."""
    resolved = Path(path).resolve()
    root = _film_holding(resolved)
    if root is not None:
        raise ProgramError(f"{what or resolved.name} at {resolved} is inside the film folder {root}; the kit never "
                           "runs a program from a film folder")
    return resolved


def _cwd() -> Path | None:
    try:
        return Path.cwd().resolve()
    except OSError:
        return None


def _folders() -> Iterator[Path]:
    """The PATH's folders, without the current directory and without relative entries."""
    here = _cwd()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        entry = entry.strip().strip('"')
        if not entry or not Path(entry).is_absolute():
            continue
        try:
            folder = Path(entry).resolve()
        except OSError:
            continue
        if folder != here:
            yield folder


def _names(name: str) -> list[str]:
    if os.name != "nt":
        return [name]
    endings = [ext for ext in os.environ.get("PATHEXT", DEFAULT_PATHEXT).split(";") if ext]
    if Path(name).suffix.lower() in {ext.lower() for ext in endings}:
        return [name]
    return [name + ext for ext in endings]


def _runnable(path: Path) -> bool:
    return path.is_file() and (os.name == "nt" or os.access(path, os.X_OK))


def find_program(name: str) -> Path | None:
    """NAME's absolute path on the PATH (current directory and relative entries left out), or None.

    Refuses (ProgramError) when the first one found lies inside a film folder."""
    key = (name, os.environ.get("PATH", ""), str(_cwd()))
    if key not in _FOUND:
        _FOUND[key] = next((folder / candidate for folder in _folders() for candidate in _names(name)
                            if _runnable(folder / candidate)), None)
    found = _FOUND[key]
    return None if found is None else checked(found, name)


def program(name: str) -> str:
    """NAME's absolute path as text, for a command line; ProgramError when it is not on the PATH."""
    found = find_program(name)
    if found is None:
        raise ProgramError(f"{name} is not on the PATH (the current directory is never searched); install it and "
                           "put its folder on the PATH")
    return str(found)


def command_of(command: Sequence[str]) -> list[str]:
    """COMMAND with its program made absolute: a bare name is looked up on the PATH, a path is checked."""
    first, rest = str(command[0]), [str(part) for part in command[1:]]
    if os.sep in first or (os.altsep and os.altsep in first):
        return [str(checked(first)), *rest]
    return [program(first), *rest]


__all__ = ["ProgramError", "checked", "command_of", "find_program", "guard_film", "program"]
