"""The whole book a preflight reads: film settings, shots, plan, prompts, stills' records, lines and grid.

A book comes from a film folder (`load_book`), from a plan in memory (`book_from_plan`), or from a small case dict in
a rule's test (`book_from_case`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from ..plan import Line, Pulse, ShotSpec, lines_from_json, parse_shot_list, pulse_from_json


@dataclass
class Book:
    film: dict
    shots: list[ShotSpec]
    tasks: dict[str, dict] = field(default_factory=dict)
    prompts: dict[str, str] = field(default_factory=dict)
    still_prompts: dict[str, str] = field(default_factory=dict)
    keyframes: dict[str, dict] = field(default_factory=dict)
    lines: dict[str, Line] = field(default_factory=dict)
    pulse: Pulse | None = None
    cuts: list[dict] = field(default_factory=list)
    ends_at: float | None = None
    sung_db: float | None = None
    song_sha256: str | None = None
    graphs: dict[str, dict] = field(default_factory=dict)
    batch: dict = field(default_factory=dict)
    files: frozenset | None = None
    root: Path | None = None
    rules_dir: Path | None = None

    def exists(self, path: str | None) -> bool:
        if not path:
            return False
        if self.files is not None:
            return path in self.files
        if self.root is not None:
            return (self.root / path).exists()
        return True

    def shot(self, key: str) -> ShotSpec:
        for shot in self.shots:
            if shot.key == key:
                return shot
        raise KeyError(key)

    def gate(self, name: str) -> dict:
        return (self.film.get("gates") or {}).get(name) or {}


def _shot(data: Mapping) -> ShotSpec:
    fields = dict(data)
    for name in ("sings", "beats"):
        if name in fields:
            fields[name] = tuple(fields[name])
    return ShotSpec(**fields)


def _line(data: Mapping) -> Line:
    return Line(key=data["key"], part=data.get("part", "lead"), text=data.get("text", ""), start=data.get("start"),
                end=data.get("end"), gaps=tuple(tuple(g) for g in data.get("gaps", [])),
                provenance=data.get("provenance", "level"), flags=tuple(data.get("flags", [])))


DEFAULT_FILM = {"name": "Test Film", "star": {"name": "Frankie"}, "tone": "serious and soulful",
                "wardrobe": {"main": "wearing a white jacket over a black top"}, "look": "photo"}
DEFAULT_LINE = {"key": "v01", "text": "la la la", "start": 10.4, "end": 13.6}


def _default_task(shot: ShotSpec) -> dict:
    if shot.kind == "vocal":
        return {"key": shot.key, "type": "vocal", "slice_start": 9.7, "seconds": 5, "shown_at": [10.0, 14.4],
                "steps": [[0, 1, "rest", None, "she looks at us with her lips together"],
                          [1, 5, "lead", "la la la", "she sways gently with the music"]],
                "step_lines": [[], list(shot.sings[:1])], "gate": [10.33, 13.85],
                "audio": f"plan/{shot.key}.voice-soft.wav", "still": shot.still_path, "closing_still": shot.still_path,
                "pin": "full", "first_sound": 10.4, "last_sound": 13.6}
    return {"key": shot.key, "type": shot.kind, "slice_start": 9.75, "seconds": 5, "shown_at": [10.0, 14.4],
            "steps": [[0, 5, "event", None, "dust drifts through the light"]], "step_lines": [[]], "gate": None,
            "audio": None, "still": shot.still_path, "closing_still": shot.still_path, "pin": "full",
            "figures": shot.has_person}


def book_from_case(case: Mapping) -> Book:
    """A small book for one rule's test. Missing parts take defaults: one shot S01 of the case's kind (vocal unless
    said), one line v01 sung 10.4 to 13.6 s, a five-second task that passes every plan rule."""
    film = {**DEFAULT_FILM, **case.get("film", {})}
    if "shots" in case:
        shots = [_shot(row) for row in case["shots"]]
    else:
        kind = case.get("kind", "vocal")
        fields = {"key": "S01", "kind": kind, **({"sings": ["v01"]} if kind == "vocal" else {}),
                  **case.get("shot", {})}
        shots = [_shot(fields)]
    tasks = {shot.key: _default_task(shot) for shot in shots}
    if "task" in case:
        tasks[shots[0].key] = {**tasks[shots[0].key], **case["task"]}
    tasks.update(case.get("tasks", {}))
    prompts, still_prompts = {}, {}
    if "prompt" in case:
        aim = still_prompts if case.get("prompt_kind") == "still" else prompts
        aim[shots[0].key] = case["prompt"]
    keyframes = dict(case.get("keyframes", {}))
    if "still" in case:
        keyframes[shots[0].key] = case["still"]
    pulse = None
    if "pulse" in case:
        data = case["pulse"]
        pulse = Pulse(beats=tuple(data["beats"]), downbeat_slot=data.get("downbeat_slot", 0),
                      grounds=MappingProxyType(dict(data.get("grounds", {}))))
    lines = {row["key"]: _line(row) for row in case.get("lines", [DEFAULT_LINE])}
    return Book(film=film, shots=shots, tasks=tasks, prompts=prompts, still_prompts=still_prompts, keyframes=keyframes,
                lines=lines, pulse=pulse, cuts=list(case.get("cuts", [])), ends_at=case.get("ends_at"),
                sung_db=case.get("sung_db"), song_sha256=case.get("song_sha256"),
                graphs=dict(case.get("graphs", {})), batch=dict(case.get("batch", {})),
                files=frozenset(case["files"]) if "files" in case else None)


def book_from_plan(film: Mapping, shots: Sequence[ShotSpec], plan, lines: Sequence[Line] | Mapping[str, Line],
                   pulse: Pulse | None, prompts: Mapping[str, str] | None = None,
                   still_prompts: Mapping[str, str] | None = None, keyframes: Mapping[str, dict] | None = None,
                   **extra) -> Book:
    """A book from a plan made in memory."""
    table = dict(lines) if isinstance(lines, Mapping) else {line.key: line for line in lines}
    return Book(film=dict(film), shots=list(shots), tasks=dict(plan.tasks), prompts=dict(prompts or {}),
                still_prompts=dict(still_prompts or {}), keyframes=dict(keyframes or {}), lines=table, pulse=pulse,
                cuts=plan.cuts_json()["cuts"], ends_at=plan.ends_at, **extra)


def _read(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def sha256_of(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_book(root: Path) -> Book:
    """Everything a film folder holds that the checks read."""
    root = Path(root)
    film = _read(root / "film.json")
    if film is None:
        raise FileNotFoundError(f"{root / 'film.json'} not found")
    shots = parse_shot_list((root / film.get("lineup_rows", "shots.txt")).read_text(encoding="utf-8"))
    voice_lines = _read(root / "analysis" / "voice-lines.json") or {}
    lines = {line.key: line for line in lines_from_json(voice_lines)}
    pulse_data = _read(root / "analysis" / "pulse.json")
    pulse = pulse_from_json(pulse_data, film.get("downbeat_slot")) if pulse_data else None
    plan_dir = root / "plan"
    tasks = {shot.key: _read(plan_dir / f"{shot.key}.task.json") for shot in shots}
    tasks = {key: task for key, task in tasks.items() if task is not None}
    prompts, still_prompts, keyframes, graphs = {}, {}, {}, {}
    for shot in shots:
        prompt_file = plan_dir / f"{shot.key}.prompt.txt"
        still = plan_dir / f"{shot.key}.still-prompt.txt"
        if prompt_file.exists():
            prompts[shot.key] = prompt_file.read_text(encoding="utf-8")
        if still.exists():
            still_prompts[shot.key] = still.read_text(encoding="utf-8")
        record = _read(root / "stills" / f"{shot.key}.json")
        if record is not None:
            keyframes[shot.key] = record
    for task in tasks.values():
        graph = task.get("graph")
        if graph and graph not in graphs:
            graphs[graph] = _read(root / Path(graph).with_suffix(".meta.json")) or {}
    mix = (film.get("stems") or {}).get("mix")
    rules_dir = root / "rules"
    return Book(film=film, shots=shots, tasks=tasks, prompts=prompts, still_prompts=still_prompts, keyframes=keyframes,
                lines=lines, pulse=pulse, cuts=(_read(plan_dir / "cuts.json") or {}).get("cuts", []),
                ends_at=film.get("ends_at"), sung_db=voice_lines.get("sung_db"),
                song_sha256=sha256_of(root / mix) if mix else None, graphs=graphs,
                batch=dict(film.get("batch") or {}), root=root, rules_dir=rules_dir if rules_dir.exists() else None)
