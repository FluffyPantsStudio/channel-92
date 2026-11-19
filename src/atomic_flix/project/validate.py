"""Find what is missing, stale or out of step in a film folder.

Levels:
  error  blocks now: a core file or folder is gone, a file is unreadable, something the next gate needs is
         missing, the mix differs from the one the person approved, an answer is no longer in the notes.
  stale  a made file is older than what it was made from (a plan older than the stems, a chosen render older
         than its still, the newest cut older than a chosen render): make it again.
  todo   something a later gate will need is not there yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..gates import GATES, gate_spec
from .actions import quote, read_film
from .layout import FOLDER_NAMES, FilmFolder
from .standing import ProjectError, Standing, fingerprint, load_standing

ERROR, STALE, TODO = "error", "stale", "todo"
REQUIRED_STEMS = {"mix": "song", "voice": "board"}      # stem -> the gate that needs it
CUT_NAME = re.compile(r"v(\d+)\.mp4")
SHOW_NEWER = 3                                          # newer inputs named in a stale finding


@dataclass(frozen=True)
class Finding:
    level: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.level:5}  {self.path}: {self.message}"


def _need(gate: str, upcoming: int) -> str:
    """ERROR when GATE is the next one or already behind us, else TODO."""
    return ERROR if gate_spec(gate).number <= upcoming else TODO


def _files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file()) if folder.is_dir() else []


def _newest(paths: Iterable[Path]) -> Path | None:
    existing = [p for p in paths if p.is_file()]
    return max(existing, key=lambda p: p.stat().st_mtime) if existing else None


def _structure(film: FilmFolder) -> list[Finding]:
    found = [Finding(ERROR, name, "folder is missing") for name in FOLDER_NAMES if not (film.root / name).is_dir()]
    for path in (film.film, film.lyric, film.notes, film.standing, film.job_log):
        if not path.is_file():
            found.append(Finding(ERROR, film.relative(path), "file is missing"))
    return found


def _inputs(film: FilmFolder, data: dict[str, Any], upcoming: int) -> list[Finding]:
    found: list[Finding] = []
    stems = data.get("stems") or {}
    for name, relative in stems.items():
        if relative and not (film.root / relative).is_file():
            gate = REQUIRED_STEMS.get(name)
            level = _need(gate, upcoming) if gate else TODO
            needed = f"needed by gate {gate_spec(gate).number} ({gate_spec(gate).title})" if gate else "optional"
            found.append(Finding(level, relative, f"{name} stem is missing; {needed}"))
    lyric = film.root / str(data.get("lyric") or film.lyric.name)
    if lyric.is_file() and not lyric.read_text(encoding="utf-8").strip():
        found.append(Finding(_need("board", upcoming), film.relative(lyric), "the lyric is empty; needed by the board"))
    for shot in data.get("lineup") or []:
        still = shot.get("still") if isinstance(shot, dict) else None
        if still and not (film.root / still).is_file():
            found.append(Finding(_need("board", upcoming), still, f"first frame of {shot.get('key')} is missing"))
    return found


def _stale(film: FilmFolder, data: dict[str, Any]) -> list[Finding]:
    found: list[Finding] = []
    origins_in = [film.root / str(p) for p in (data.get("stems") or {}).values() if p]
    origins_in.append(film.root / str(data.get("lyric") or film.lyric.name))
    made_files = _files(film.root / "analysis")
    for group, inputs in ((made_files, origins_in), (_files(film.root / "plan"), origins_in + made_files)):
        existing = [(p, p.stat().st_mtime) for p in inputs if p.is_file()]
        for path in group:
            made = path.stat().st_mtime
            newer = sorted(film.relative(p) for p, when in existing if when > made)
            if newer:
                shown = ", ".join(newer[:SHOW_NEWER]) + (" and more" if len(newer) > SHOW_NEWER else "")
                found.append(Finding(STALE, film.relative(path), f"older than {shown}; make it again"))
    keyframes = {s.get("key"): s.get("still") for s in data.get("lineup") or [] if isinstance(s, dict)}
    picked: list[Path] = []
    for key, number in (data.get("picks") or {}).items():
        take_file = film.take_file(key, int(number))
        if not take_file.is_file():
            found.append(Finding(ERROR, film.relative(take_file), f"the chosen render of {key} is missing"))
            continue
        picked.append(take_file)
        still = film.root / keyframes[key] if keyframes.get(key) else film.still(key)
        if still.is_file() and take_file.stat().st_mtime < still.stat().st_mtime:
            found.append(Finding(STALE, film.relative(take_file),
                                 f"older than its first frame {film.relative(still)}; the still changed after it"))
    cuts = [p for p in _files(film.root / "cuts") if CUT_NAME.fullmatch(p.name)]
    if cuts and picked:
        latest_cut = max(cuts, key=lambda p: int(CUT_NAME.fullmatch(p.name).group(1)))
        newest = _newest(picked)
        if latest_cut.stat().st_mtime < newest.stat().st_mtime:
            found.append(Finding(STALE, film.relative(latest_cut),
                                 f"older than the chosen render {film.relative(newest)}; assemble again"))
    return found


def _gates(film: FilmFolder, standing: Standing) -> list[Finding]:
    found: list[Finding] = []
    notes = film.notes.read_text(encoding="utf-8") if film.notes.is_file() else ""
    for record in standing.gates.records:
        for answer in record.answers:
            if quote(answer.words) not in notes:
                found.append(Finding(ERROR, film.relative(film.notes),
                                     f"the person's answer at gate {record.spec.number} ({answer.at}) is no longer "
                                     "in the notes word for word"))
    song = standing.song
    if song is not None:
        mix = film.root / song.file
        if not mix.is_file():
            found.append(Finding(ERROR, song.file, "the mix the person approved at gate 2 is gone"))
        elif fingerprint(mix, song.file).sha256 != song.sha256:
            found.append(Finding(ERROR, song.file, "this is not the mix the person approved at gate 2; "
                                                   "ask again before planning on it"))
    return found


def _job_log(film: FilmFolder) -> list[Finding]:
    from ..compare.ledger import read_job_log     # here, not at the top: compare reads project folders too

    if not film.job_log.is_file():
        return []
    return [Finding(ERROR, film.relative(film.job_log), problem)
            for problem in read_job_log(film.job_log, strict=False).problems]


def validate(film: FilmFolder | Path) -> tuple[Finding, ...]:
    """Every finding for the film folder, errors first."""
    folder = film if isinstance(film, FilmFolder) else FilmFolder(Path(film))
    found = _structure(folder)
    try:
        standing = load_standing(folder)
    except ProjectError as problem:
        found.append(Finding(ERROR, folder.relative(folder.standing), str(problem)))
        standing = None
    upcoming = standing.gates.next_gate() if standing else None
    number = upcoming.number if upcoming else len(GATES) + 1
    try:
        data = read_film(folder)
    except ProjectError as problem:
        found.append(Finding(ERROR, folder.relative(folder.film), str(problem)))
        data = None
    if data is not None:
        found += _inputs(folder, data, number) + _stale(folder, data)
    if standing is not None:
        found += _gates(folder, standing)
    found += _job_log(folder)
    order = {ERROR: 0, STALE: 1, TODO: 2}
    return tuple(sorted(found, key=lambda f: (order[f.level], f.path)))
