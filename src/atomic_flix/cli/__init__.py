"""Channel 92: a free kit for cinematic music films. One command for a whole film, verb by verb, each reading and
writing the film's own folder. The command is `channel92`; `atomic-flix` is the same command under its first name.

    channel92 VERB [ARGS]         channel92 VERB --help for each verb's own help (atomic-flix VERB works the same)

Film verbs in the order a film meets them, then the stage modules by name (their own command lines).
"""

from __future__ import annotations

import sys
from typing import Callable, Sequence

from . import (cut_steps, desk_steps, eval_steps, finish_steps, grade_steps, prereq_steps, project_steps, setup_steps,
               shoot_steps, sound_steps, structure_steps)
from .common import StepError

Handler = Callable[[Sequence[str]], int]
FILM_ORDER = ("new", "progress", "gate", "packet", "desk", "structure", "choose", "time", "bars", "plan", "lint",
              "budget", "eval", "shoot", "place", "cut",
              "grade", "review", "finish", "compare")


def _load_stage(name: str) -> Handler:
    def run(argv: Sequence[str]) -> int:
        stage_mod = __import__(f"atomic_flix.{name}.__main__", fromlist=["main"])
        result = stage_mod.main(list(argv))
        return int(result or 0)
    return run


def _plan(argv: Sequence[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: atomic-flix plan FILM\n\nPlan the cuts on the bar's one or three first, then each shot's render\n"
              "slice, steps, gated voice and soft copy, and write the render and still prompts into plan/.\n"
              "Reads film.json, shots.txt, analysis/voice-lines.json and analysis/pulse.json.")
        return 0
    setup_steps.require_aspect_of(argv)
    return _load_stage("plan")(argv)


def _either(film_step: Handler, stage_mod: str, module_verbs: tuple[str, ...]) -> Handler:
    """A film verb that shares its name with a stage module: the module's own verbs go to the module."""
    def run(argv: Sequence[str]) -> int:
        if argv and argv[0] in module_verbs:
            return _load_stage(stage_mod)(argv)
        return film_step(argv)
    return run


def _folder_verbs(argv: Sequence[str]) -> int:
    verbs = {"new": project_steps.COMMANDS["new"][1], "progress": project_steps.COMMANDS["progress"][1]}
    if argv and argv[0] in ("-h", "--help"):
        print("usage: atomic-flix folder new FILM ... | folder progress FILM")
        return 0
    if not argv or argv[0] not in verbs:
        print("usage: atomic-flix folder new FILM ... | folder progress FILM")
        return 2
    return verbs[argv[0]](argv[1:])


STEPS: dict[str, tuple[str, Handler]] = {
    **project_steps.COMMANDS, **desk_steps.COMMANDS, **structure_steps.COMMANDS, **setup_steps.COMMANDS,
    **sound_steps.COMMANDS, **shoot_steps.COMMANDS, **eval_steps.COMMANDS,
    "plan": ("plan cuts on the bar, each shot's slice, gated voice and prompts (plan/)", _plan),
    "cut": (cut_steps.COMMANDS["cut"][0], _either(cut_steps.COMMANDS["cut"][1], "cut", ("audit", "encode", "flash"))),
    "grade": (grade_steps.COMMANDS["grade"][0],
              _either(grade_steps.COMMANDS["grade"][1], "grade", ("measure", "apply"))),
    "review": (cut_steps.COMMANDS["review"][0],
               _either(cut_steps.COMMANDS["review"][1], "review", ("boards", "frames"))),
    **finish_steps.COMMANDS,
    "compare": cut_steps.COMMANDS["compare"],
    **prereq_steps.COMMANDS,
}

MODULES: dict[str, tuple[str, Handler]] = {
    "timing": ("the timing stage (same as `time`)", sound_steps.COMMANDS["time"][1]),
    "barmap": ("the beats-and-bars stage (same as `bars`)", sound_steps.COMMANDS["bars"][1]),
    "runner": ("the ComfyUI runner itself: ping, plan, budget, shoot, progress", _load_stage("runner")),
    "scenes": ("Blender building-block scenes: check, plan, capture, blend, controls", _load_stage("scenes")),
    "folder": ("a film folder: new, progress", _folder_verbs),
    "gates": ("the six gates (same as `gate`)", project_steps.COMMANDS["gate"][1]),
}


def overview() -> str:
    lines = [__doc__.strip(), "", f"Before the first film:\n  {'setup':<9} {STEPS['setup'][0]}", "", "Film verbs:"]
    lines += [f"  {verb:<9} {STEPS[verb][0]}" for verb in FILM_ORDER]
    lines += ["", "Stage modules (the film verbs `plan` to `compare` above are modules too):"]
    lines += [f"  {name:<9} {about}" for name, (about, _) in MODULES.items()]
    lines += ["", "A person decides at six gates (concept, the song by ear, her face, the board, render hours, v1);",
              "`shoot` refuses until gate 5 holds the person's yes, and gates 5 and 6 are not asked until a",
              "fresh `eval` is not BLOCKED for them. See docs/quickstart.md for a whole run."]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(overview())
        return 0
    verb, rest = args[0], args[1:]
    found = STEPS.get(verb) or MODULES.get(verb)
    if found is None:
        print(f"atomic-flix: no verb {verb!r}\n\n{overview()}", file=sys.stderr)
        return 2
    try:
        return found[1](rest)
    except StepError as problem:
        print(f"atomic-flix {verb}: {problem}", file=sys.stderr)
        return 2


__all__ = ["main", "overview", "StepError"]
