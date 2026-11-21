"""Action shots: which shots of a shot list are action, and how far each one's Blender staging has come.

A shot is an action shot when what the list says it shows (its beats, its goal) names a fight, a chase, a sprint, a
collision (`data/rules/action.txt`). Such a shot is staged in Blender (`docs/action.md`): the movement is built as a
scene, captured, turned into control clips, and the video model follows a clip instead of inventing the movement.
Words that only sometimes mean action (`action-maybe.txt`: a tear that "runs down" a cheek, a kick drum) are a warning
for a person to read, not a block. The lint rules and `progress` both read this module, so they never disagree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .model import ShotSpec
from .vocab import find

GUIDES = ("depth", "canny", "edges", "pose")
DEFAULT_GUIDE = "depth"
READY = "ready"
NO_SCENE = "the scene file is missing"
NOT_CAPTURED = "the scene is not captured yet"
NO_CLIP = "the capture has no control clip for its guide yet"
STALE = "the scene changed after it was captured; capture it and make its control clips again"


def written(shot: ShotSpec) -> str:
    """What the shot list says the shot shows: its beats and goal, and for a shot where she is not singing what she
    does in each line. A sung shot's clauses are small movements, never an action to stage."""
    parts = [*shot.beats, shot.goal or ""]
    if shot.kind != "vocal":
        parts += shot.acts.values()
    return " ".join(parts)


def _words(name: str, shot: ShotSpec, rules_dir: Path | None) -> list[str]:
    return list(dict.fromkeys(word.lower() for word in find(name, written(shot), rules_dir)))


def action_words(shot: ShotSpec, rules_dir: Path | None = None) -> list[str]:
    """The sure action terms the shot's written text uses, each once, in order."""
    return _words("action", shot, rules_dir)


def maybe_words(shot: ShotSpec, rules_dir: Path | None = None) -> list[str]:
    """Terms that may mean action (or a figure of speech), each once, in order."""
    return _words("action-maybe", shot, rules_dir)


def has_reason(shot: ShotSpec) -> bool:
    """True when the person wrote why this action shot is not staged in Blender."""
    return bool((shot.no_blender or "").strip())


def _open(shot: ShotSpec) -> bool:
    return not shot.blender and not has_reason(shot)


def needs_blender(shot: ShotSpec, rules_dir: Path | None = None) -> bool:
    """An action shot with neither a Blender scene nor the person's written reason."""
    return _open(shot) and bool(action_words(shot, rules_dir))


def may_need_blender(shot: ShotSpec, rules_dir: Path | None = None) -> bool:
    """A shot with neither scene nor reason that uses only words which may mean action."""
    return _open(shot) and not action_words(shot, rules_dir) and bool(maybe_words(shot, rules_dir))


def guide_of(shot: ShotSpec) -> str:
    """The control clip that guides the shot's take: its `guide:`, else depth (not checked here)."""
    return str((shot.extra or {}).get("guide") or DEFAULT_GUIDE).strip().lower()


def staging(root: Path, shot: ShotSpec) -> str:
    """How far a Blender shot has come: READY, or the first thing it still lacks. Paths stay in the film folder."""
    root = Path(root).resolve()
    scene = (root / shot.blender).resolve() if shot.blender else None
    if scene is None or root not in scene.parents or not scene.is_file():
        return NO_SCENE
    out = (root / "blender" / shot.key).resolve()
    capture = out / "capture.json"
    if not capture.is_file():
        return NOT_CAPTURED
    if scene.stat().st_mtime > capture.stat().st_mtime:
        return STALE
    if not any((out / "controls").glob(f"{guide_of(shot)}-*.mp4")):
        return NO_CLIP
    return READY


def progress_lines(root: Path, shots: Sequence[ShotSpec], rules_dir: Path | None = None) -> list[str]:
    """`progress` lines for the shots that are action, may be action, or are already on the Blender route."""
    lines = []
    for shot in shots:
        if shot.blender:
            state = staging(root, shot)
            word = "ok    " if state == READY else "todo  "
            lines.append(f"{word} {shot.key}: Blender shot, {state if state != READY else 'its control clips are made'}")
        elif needs_blender(shot, rules_dir):
            lines.append(f"todo   {shot.key}: an action shot ({', '.join(action_words(shot, rules_dir))}) with no "
                         "Blender scene: add `blender: scenes/NAME.json` to the shot (or the person's `no_blender: reason`)")
        elif may_need_blender(shot, rules_dir):
            lines.append(f"check  {shot.key}: may be an action shot ({', '.join(maybe_words(shot, rules_dir))}); "
                         "stage it in Blender if it is")
    return lines
