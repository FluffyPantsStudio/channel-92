"""What an eval reads, and its fingerprint: every input file's SHA-256, so a report older than its inputs is stale.

Inputs are the film's own files the checks read, by group, so each row carries the hash of what its family read:
the globbed folders, plus every file a task points at (its still, closing still, audio and graph sidecar), recorded
as "missing" when it is not there, so a file that goes or comes changes the table. The kit's rule data and version
(`kit/...`) are inputs too: a new rules map, word list or kit makes a report stale. Paths are only ever read inside
the film folder; a path in film.json or a task that points elsewhere is recorded as refused, never read.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping

import atomic_flix

from ..cast import cast_of, place_views, places_of, views_of
from ..lint.book import graph_sidecar
from ..plan.vocab import DATA
from ..runner.places import film_file
from ..runner.template import TemplateError

KIT_INPUTS = ("rules-map.json", "lessons.json", "rules/*.txt")
TASK_FILES = ("still", "closing_still", "audio")
GROUPS: Mapping[str, tuple[str, ...]] = {
    "lint": ("film.json", "standing.json", "@lineup", "@mix", "analysis/*.json", "plan/*.json", "plan/*.txt",
             "plan/*.wav", "stills/*.json", "rules/*.txt", "scenes/*.json", "@views", "renders/*/r*.job.json", "@tasks"),
    "sent": ("film.json", "@lineup", "rules/*.txt", "renders/*/r*.job.json"),
    "ledger": ("standing.json", "@lineup", "stills/*.json", "renders/*/r*.job.json"),
    "scene": ("film.json", "@lineup", "plan/*.task.json", "stills/*.json", "stills/*.png", "@views", "@tasks"),
    "cut": ("cuts/*.json", "cuts/*.mp4"),
}
MISSING = "missing"
REFUSED = "refused:"
CHUNK = 1 << 20


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None             # the checks say why it cannot be read; here the file is hashed as it is


def _named(root: Path, value: object, what: str) -> list[str]:
    """VALUE as a film-relative name, or a `refused:` entry when it is no path inside the film."""
    try:
        return [film_file(root, value, what).relative_to(root.resolve()).as_posix()]
    except (TemplateError, ValueError) as problem:
        return [f"{REFUSED}{what}: {problem}"]


def _task_files(root: Path) -> list[str]:
    names = []
    for path in sorted(root.glob("plan/*.task.json")):
        task = _json(path)
        if not isinstance(task, dict):
            continue
        for field in TASK_FILES:
            if task.get(field):
                names += _named(root, task[field], f"{path.name} {field}")
        if task.get("graph"):
            try:
                names.append(graph_sidecar(root, task["graph"]).relative_to(root.resolve()).as_posix())
            except (TemplateError, ValueError) as problem:
                names.append(f"{REFUSED}{path.name} graph: {problem}")
    return names


def _expand(root: Path, pattern: str, film: object) -> list[str]:
    film = film if isinstance(film, dict) else {}
    if pattern == "@lineup":
        return _named(root, film.get("lineup_rows") or "shots.txt", "lineup_rows")
    if pattern == "@mix":
        stems = film.get("stems")
        mix = stems.get("mix") if isinstance(stems, dict) else None
        return _named(root, mix, "stems.mix") if mix else []
    if pattern == "@tasks":
        return _task_files(root)
    if pattern == "@views":
        pictures = [path for person in cast_of(film).values() for path in views_of(person).values()]
        pictures += [path for place in places_of(film).values() for path in place_views(place).values()]
        return [name for path in pictures for name in _named(root, path, "character or place view")]
    return [path.relative_to(root).as_posix() for path in sorted(root.glob(pattern)) if path.is_file()]


def group_files(root: Path, group: str) -> list[str]:
    """The names GROUP reads in ROOT now: film-relative paths, plus `refused:` entries for paths outside the film."""
    root = Path(root)
    film = _json(root / "film.json")
    return sorted({name for pattern in GROUPS[group] for name in _expand(root, pattern, film)})


def kit_table() -> dict[str, str]:
    table = {f"kit/{path.relative_to(DATA).as_posix()}": file_sha(path)
             for pattern in KIT_INPUTS for path in sorted(DATA.glob(pattern)) if path.is_file()}
    return {**table, "kit/version": atomic_flix.__version__}     # read now: an upgrade makes reports stale


def _entry(root: Path, name: str) -> str:
    if name.startswith(REFUSED):
        return "refused"
    path = root / name
    return file_sha(path) if path.is_file() else MISSING


def input_table(root: Path) -> dict[str, str]:
    """Every input of an eval of ROOT: name to SHA-256 (or `missing`, or `refused`), and the kit's own entries."""
    root = Path(root)
    names = sorted({name for group in GROUPS for name in group_files(root, group)})
    return {**{name: _entry(root, name) for name in names}, **kit_table()}


def digest(table: Mapping[str, str], names: Iterable[str] | None = None) -> str:
    """One hash over NAMES (all of TABLE when None) and their SHA-256s, plus the kit's entries."""
    chosen = sorted(set(table) if names is None else {*names, *(k for k in table if k.startswith("kit/"))})
    joined = "\n".join(f"{name} {table.get(name, MISSING)}" for name in chosen)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def changed(saved: Mapping[str, str], now: Mapping[str, str]) -> list[str]:
    """Inputs added, removed or changed between two tables, in order."""
    return sorted(name for name in set(saved) | set(now) if saved.get(name) != now.get(name))


def _rounds(loop: object) -> list:
    rounds = loop.get("rounds") if isinstance(loop, dict) else None
    return list(rounds) if isinstance(rounds, list) else [loop]


def standing_view(data: object, gate: str) -> str:
    """A hash of standing.json without what asking and answering GATE itself changes: the gate's own record; for
    gate 5 the batch its yes copies and planning draws on; for gate 6 the split of review rounds into loops (its
    answer closes the open loop). The hook compares it at the answer and before shooting, so nothing else may move."""
    view = dict(data) if isinstance(data, dict) else {"raw": data}
    gates = view.get("gates")
    if isinstance(gates, dict):
        gates = dict(gates)
        records = gates.get("gates")
        if isinstance(records, list):
            gates["gates"] = [r for r in records if not (isinstance(r, dict) and r.get("gate") == gate)]
        if gate == "v1":
            past = gates.pop("past_reviews", None)
            loops = (past if isinstance(past, list) else [past]) + [gates.pop("review", None)]
            gates["rounds"] = [r for loop in loops if loop is not None for r in _rounds(loop)]
        view["gates"] = gates
    if gate == "spend":
        view.pop("batch", None)
    text = json.dumps(view, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
