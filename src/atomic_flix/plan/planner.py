"""The plan of a whole film: cuts first, then one task per shot in the core spec's file format."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from ..setups import reads_as_jump, size_note
from .cuts import PIN_EXIT, Cut, first_sound, last_sound, plan_cuts
from .model import Line, PlanError, Pulse, ShotSpec
from .slices import gate_span, phrases_in_slice, slice_bounds, spread_steps, whole_second_steps
from .vocab import camera_moves
from .words import is_wordless, sung_words
from ..formats import stamped

HELD_NOTE = 2.0       # a wordless line this long is a held note
ROUND_MOUTH = "her lips in a soft round oo"
OPEN_REST = "she looks at us with her lips together"
CLOSE_REST = "she keeps swaying gently with the music, her eyes on us"
MOVES = ("she sways gently with the music", "her head tilts a little", "she lifts her chin a little")


@dataclass
class Plan:
    cuts: list[Cut]
    tasks: dict[str, dict]
    notes: list[str] = field(default_factory=list)
    ends_at: float = 0.0

    def cut_of(self, key: str) -> Cut:
        for cut in self.cuts:
            if cut.key == key:
                return cut
        raise KeyError(key)

    def cut_table(self) -> str:
        rows = []
        for cut in self.cuts:
            grid = "OFF GRID" if cut.grid == "off" else cut.grid
            rows.append(f"{cut.key:<6} {cut.at:8.2f}  {grid:<8} {cut.note}".rstrip())
        return "\n".join(rows)

    def cuts_json(self) -> dict:
        out = []
        for cut in self.cuts:
            row = {"key": cut.key, "at": round(cut.at, 3), "grid": cut.grid}
            if cut.note:
                row["note"] = cut.note
            out.append(row)
        return {"cuts": out}


def _role(shot: ShotSpec) -> str:
    if shot.kind == "vocal":
        return "sung"
    if shot.kind == "mute":
        return "silent"
    return "cutaway" if shot.figures else "plate"


def _clause(shot: ShotSpec, keys: Sequence[str], lines: Mapping[str, Line], index: int) -> str:
    act = shot.acts.get(keys[0], "")
    if any(is_wordless(lines[key].text) for key in keys):
        return act if "round oo" in act else ROUND_MOUTH
    return act or MOVES[index % len(MOVES)]


def _vocal_task(shot: ShotSpec, on: tuple[float, float], lines: Mapping[str, Line], names: Sequence[str]) -> dict:
    first, last = first_sound(shot, lines), last_sound(shot, lines)
    slice_start, seconds, notes = slice_bounds(on, first)
    own = [lines[key] for key in shot.sings]
    items = [(line.start - slice_start, line.end - slice_start, line.key) for line in own]
    shown = (on[0] - slice_start, on[1] - slice_start)
    steps, step_lines, folds = [], [], []
    sung_index = 0
    for index, step in enumerate(whole_second_steps(items, seconds, shown)):
        if not step.lines:
            clause = OPEN_REST if index == 0 else CLOSE_REST
            steps.append([step.start, step.end, "rest", None, clause])
        else:
            later = [line.start for line in own if line.start > max(lines[k].start for k in step.lines)]
            words = sung_words(step.lines, lines, names, min(later) if later else None)
            steps.append([step.start, step.end, lines[step.lines[0]].part, words,
                          _clause(shot, step.lines, lines, sung_index)])
            sung_index += 1
        step_lines.append(list(step.lines))
        folds.append([step.folded_head, step.folded_tail])
    pin = shot.pin or "full"
    exit_after = round(on[1] - last, 3)
    if pin == "full" and exit_after > PIN_EXIT:
        notes.append(f"pinned and on screen {exit_after:.2f} s after her last sound: move the cut earlier (P1)")
    for line in own:
        if is_wordless(line.text) and line.end - line.start >= HELD_NOTE:
            notes.append(f"held note {line.key} ({line.end - line.start:.1f} s): a soft round mouth, soft copy heard")
    still = shot.still_path
    return {"key": shot.key, "type": "vocal", "role": "sung", "slice_start": slice_start, "seconds": seconds,
            "shown_at": [round(on[0], 3), round(on[1], 3)], "vocal_spans": phrases_in_slice(own, slice_start),
            "steps": steps, "step_lines": step_lines, "step_folds": folds,
            "gate": list(gate_span(shot.sings, lines)), "audio": f"plan/{shot.key}.voice-soft.wav",
            "still": still, "closing_still": shot.closing_still or (still if pin in ("full", "soft") else None),
            "pin": pin, "run_up": round(first - slice_start, 3), "first_sound": first, "last_sound": last,
            "exit_after_last": exit_after, "notes": notes}


def _scene_task(shot: ShotSpec, on: tuple[float, float]) -> dict:
    slice_start, seconds, notes = slice_bounds(on, None)
    shown = (on[0] - slice_start, on[1] - slice_start)
    events = list(shot.beats) or [shot.goal or "the scene holds as in the first frame"]
    spans = spread_steps(len(events), seconds, shown)
    part = "silent" if shot.kind == "mute" else "event"
    steps = [[a, b, part, None, text] for (a, b), text in zip(spans, events)]
    moving = camera_moves(shot.cam_move)
    pin = shot.pin or ("none" if moving else "full")
    still = shot.still_path
    return {"key": shot.key, "type": shot.kind, "role": _role(shot), "slice_start": slice_start, "seconds": seconds,
            "shown_at": [round(on[0], 3), round(on[1], 3)], "vocal_spans": [], "steps": steps,
            "step_lines": [[] for _ in steps], "step_folds": [[False, False] for _ in steps], "gate": None,
            "audio": None, "still": still, "closing_still": shot.closing_still or (still if pin == "full" else None),
            "pin": pin, "figures": shot.has_person, "cam_move": shot.cam_move or "locked", "notes": notes}


def _size_notes(shots: Sequence[ShotSpec]) -> list[str]:
    """Neighbouring vocal shots, also across one cutaway, on one setup need clearly different sizes (C1)."""
    notes = []
    vocal = [(index, shot) for index, shot in enumerate(shots) if shot.kind == "vocal"]
    for (i, left), (j, right) in zip(vocal, vocal[1:]):
        if j - i > 2 or not left.setup or left.setup != right.setup:
            continue
        if reads_as_jump(left.setup, left.crop, right.setup, right.crop):
            notes.append(f"{left.key} and {right.key} are on one setup ({left.setup}) at "
                         f"{size_note(left.crop, right.crop)}: make them differ more (C1)")
    return notes


def plan_film(shots: Sequence[ShotSpec], lines: Sequence[Line] | Mapping[str, Line], pulse: Pulse,
              ends_at: float | None = None, names: Sequence[str] = ()) -> Plan:
    """Cuts on the bar first, then each shot's slice, steps, phrases, gate and pin."""
    table = dict(lines) if isinstance(lines, Mapping) else {line.key: line for line in lines}
    if ends_at is None:
        finishes = [line.end for line in table.values() if line.timed] + list(pulse.beats[-1:])
        ends_at = max(finishes) + 2.0 if finishes else 0.0
    cuts = plan_cuts(shots, table, pulse, ends_at)
    tasks: dict[str, dict] = {}
    notes: list[str] = []
    for index, (shot, cut) in enumerate(zip(shots, cuts)):
        end = cuts[index + 1].at if index + 1 < len(cuts) else ends_at
        on = (cut.at, end)
        if end - cut.at < 1.6:
            notes.append(f"{shot.key} is on screen {end - cut.at:.2f} s, under 1.6 s")
        task = _vocal_task(shot, on, table, names) if shot.kind == "vocal" else _scene_task(shot, on)
        if cut.note:
            task["notes"] = [f"cut: {cut.note}"] + task["notes"]
            notes.append(f"{shot.key}: {cut.note}")
        if shot.scene:
            task["scene"] = shot.scene         # optional; a task without it belongs to no scene
        tasks[shot.key] = task
    notes.extend(_size_notes(shots))
    return Plan(cuts=cuts, tasks=tasks, notes=notes, ends_at=ends_at)


def write_plan(plan: Plan, root: Path, voice: Path | None = None) -> list[Path]:
    """plan/cuts.json and plan/<key>.task.json; with the voice stem, each vocal shot's gated WAV and soft copy."""
    from ..wav import read_wav, save_wav
    from .voice import OUT_RATE, edge_levels, gated_voice, soft_copy

    folder = Path(root) / "plan"
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    stem = read_wav(voice) if voice else None
    for key, task in plan.tasks.items():
        out = dict(task)
        if stem is not None and task["type"] == "vocal":
            samples, rate = stem
            gated = gated_voice(samples, rate, task["slice_start"], task["seconds"], tuple(task["gate"]))
            written.append(save_wav(folder / f"{key}.voice.wav", gated, OUT_RATE))
            written.append(save_wav(folder / f"{key}.voice-soft.wav", soft_copy(gated, OUT_RATE), OUT_RATE))
            out["gate_edges_db"] = edge_levels(samples, rate, tuple(task["gate"]))
        path = folder / f"{key}.task.json"
        path.write_text(json.dumps(stamped("task", out), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    cuts = folder / "cuts.json"
    cuts.write_text(json.dumps(stamped("cuts", plan.cuts_json()), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    written.append(cuts)
    return written


__all__ = ["Plan", "PlanError", "plan_film", "write_plan"]
