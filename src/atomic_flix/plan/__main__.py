"""python -m atomic_flix.plan FILM_DIR

Reads film.json, the shot list (shots.txt), analysis/voice-lines.json and analysis/pulse.json; writes plan/cuts.json,
plan/<key>.task.json, each vocal shot's gated voice and soft copy, and the render and still prompts
(plan/<key>.prompt.txt, plan/<key>.still-prompt.txt). Prints every cut with its grid.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..prompts import write_prompts
from .model import PlanError, lines_from_json, pulse_from_json, read_json
from .planner import plan_film, write_plan
from .shotlist import parse_shot_list


def run(root: Path) -> int:
    film = read_json(root / "film.json")
    shots = parse_shot_list((root / film.get("lineup_rows", "shots.txt")).read_text(encoding="utf-8"))
    lines = lines_from_json(read_json(root / "analysis" / "voice-lines.json"))
    pulse = pulse_from_json(read_json(root / "analysis" / "pulse.json"), film.get("downbeat_slot"))
    names = [((film.get("star") or {}).get("name") or "")] + list(film.get("allow") or [])
    plan = plan_film(shots, lines, pulse, ends_at=film.get("ends_at"), names=names)
    voice = (film.get("stems") or {}).get("voice")
    write_plan(plan, root, voice=root / voice if voice and (root / voice).exists() else None)
    take_files, keyframes = write_prompts(film, shots, plan.tasks, {line.key: line for line in lines})
    for key, text in take_files.items():
        (root / "plan" / f"{key}.prompt.txt").write_text(text + "\n", encoding="utf-8")
    for key, text in keyframes.items():
        (root / "plan" / f"{key}.still-prompt.txt").write_text(text + "\n", encoding="utf-8")
    print(plan.cut_table())
    for note in plan.notes:
        print(f"note: {note}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m atomic_flix.plan", description=__doc__.split("\n\n")[1])
    parser.add_argument("film", type=Path, help="the film folder")
    args = parser.parse_args(argv)
    try:
        return run(args.film)
    except (PlanError, FileNotFoundError, KeyError) as problem:
        print(f"plan: nothing written past this point: {problem}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
