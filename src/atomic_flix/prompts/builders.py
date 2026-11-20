"""Prompt text for renders and stills, written from the shots the person listed and the planned cuts.

Sung shots copy the order our first film settled on across its 25 singing shots (its record of the sung shots):
setting, standing behaviour, a single mood, a timeline of whole seconds, her face during the song, her appearance.
Each point below was paid for in rejected takes:
- quote her lyric word for word with the seconds it occupies, and put a period only where the stem goes silent;
- give each sung step one simple movement clause; for a vowel without words, a soft round mouth;
- describe the framing the still really has (collar-up when it is cropped close, chest-up otherwise);
- never mention hands or arms, never put a smile on the singing mouth, never stack moods;
- the single permitted negative is that she never turns away;
- write a camera sentence only for shots whose point is the move;
- grain and film-stock vocabulary never appear.
Still prompts close with the edge-to-edge sentence and the sentence that forbids lettering.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from ..plan.vocab import camera_moves, find
from ..plan.words import sung_words

TIGHT = 0.75
DEFAULT_TONE = "serious and soulful"
DEFAULT_STAR = "Nova"
EDGE_LINE = "The picture fills the whole frame edge to edge."
NO_TEXT_LINE = "No text, no letters, no logos."
KEEP_SCENE = "Colours, light and materials stay as in the first frame, and things move like real objects."
KEEP_PEOPLE = "Whoever is in the first frame stays the same person; nobody new appears."
EMPTY_SCENE = "Nobody appears in the picture."
CLOSE_REST = "she keeps swaying gently with the music, her eyes on us"


def framing_phrase(crop: float | None, framing: str | None = None) -> str:
    """How the prompt names the frame: a crop keeping under 75 % of the wide still is 'from the collar up'."""
    if framing:
        word = framing.lower()
        if "collar" in word:
            return "from the collar up"
        if "chest" in word:
            return "from the chest up"
        return framing
    return "from the collar up" if crop is not None and crop < TIGHT else "from the chest up"


def _star(film: Mapping) -> str:
    return (film.get("star") or {}).get("name") or DEFAULT_STAR


def _outfit(film: Mapping, shot) -> str:
    wardrobe = film.get("wardrobe") or {}
    if shot.outfit and shot.outfit in wardrobe:
        return wardrobe[shot.outfit]
    return next(iter(wardrobe.values()), "dressed as in the first frame")


def _sentence(text: str) -> str:
    text = " ".join(text.split()).rstrip(" .;,")
    return text[:1].upper() + text[1:] + "." if text else ""


def _need(shot, kind: str) -> None:
    if shot.kind != kind:
        raise ValueError(f"{shot.key} is a {shot.kind} shot, not {kind}")


def _sung_row(step: Sequence, folds: Sequence[bool]) -> str:
    start, end, part, words, clause = step
    if part == "rest":
        return f"{start}-{end}s: {clause}."
    opening = "her lips together at first, then she sings" if folds[0] else "she sings"
    row = f'{start}-{end}s: {opening} "{words}"; {clause}'
    if folds[1]:
        row += f"; then {CLOSE_REST}"
    return row + "."


def sung_prompt(film: Mapping, shot, task: Mapping, lines: Mapping | None = None) -> str:
    """A vocal render's prompt from its task (steps already carry the words and one clause each)."""
    _need(shot, "vocal")
    name, tone = _star(film), film.get("tone") or DEFAULT_TONE
    framing = framing_phrase(shot.crop, shot.framing)
    company = ("She is alone and moves" if shot.count <= 1
               else f"There are {shot.count} of her, the same woman each time, and nobody else; each one moves")
    moving = camera_moves(shot.cam_move)
    cam_move = "" if moving else " The camera is locked off and keeps one size."
    parts = [
        f"{name} sings to us from {shot.place or film.get('world') or 'a plain room'}.",
        "She faces us for the whole shot and sings with small, natural mouth movements, her eyes on us; she never "
        f"turns away. {company} with the music the whole time, her head and shoulders swaying gently and "
        f"continuously.{cam_move} She stays exactly the same size in the frame, {framing}, from the first frame to the "
        "last.",
        f"Her manner is {tone}.",
    ]
    folds = task.get("step_folds") or [[False, False]] * len(task["steps"])
    parts += [_sung_row(step, fold) for step, fold in zip(task["steps"], folds)]
    parts.append(f"Her face stays {tone} while she sings; her mouth only shapes the words.")
    if moving:
        parts.append(_sentence(f"Camera: {shot.cam_move}"))
    parts.append(f"{name} looks just as she does in the first frame, {_outfit(film, shot)}, with a natural body.")
    return "\n".join(parts)


def _scene_rows(task: Mapping) -> list[str]:
    return [f"{a}-{b}s: {text.rstrip('.')}." for a, b, _, _, text in task["steps"]]


def silent_prompt(film: Mapping, shot, task: Mapping) -> str:
    """She is on screen with her lips closed: a goal, the steps over the whole render, a keep-sentence."""
    _need(shot, "mute")
    name = _star(film)
    goal = shot.goal or (shot.beats[0] if shot.beats else "she is quiet and present")
    parts = [f"{name} is in {shot.place or film.get('world') or 'a plain room'}, her lips closed the whole time: "
             f"{goal.rstrip('.')}."]
    parts += _scene_rows(task)
    if camera_moves(shot.cam_move):
        parts.append(_sentence(f"Camera: {shot.cam_move}"))
    parts += [KEEP_SCENE, KEEP_PEOPLE, f"{name} looks just as she does in the first frame, {_outfit(film, shot)}."]
    return "\n".join(parts)


def plate_prompt(film: Mapping, shot, task: Mapping) -> str:
    """A cutaway: the goal, its events spread over what the cut shows, the camera only when it moves."""
    _need(shot, "cutaway")
    goal = shot.goal or (shot.beats[0] if shot.beats else shot.place or "the place as in the first frame")
    parts = [_sentence(goal)] + _scene_rows(task)
    if camera_moves(shot.cam_move):
        parts.append(_sentence(f"Camera: {shot.cam_move}"))
    parts.append(KEEP_SCENE)
    parts.append(KEEP_PEOPLE if shot.figures else EMPTY_SCENE)
    return "\n".join(parts)


def still_prompt(film: Mapping, shot, description: str | None = None) -> str:
    """A first-frame still for an image model. A person in it is described from canon; it ends with our two lines."""
    name = _star(film)
    who = (film.get("star") or {}).get("who")
    place = shot.place or film.get("world") or "a plain room"
    parts = []
    if shot.kind == "vocal":
        framing = framing_phrase(shot.crop, shot.framing)
        person = f"{name}, {who}" if who else name
        parts.append(f"Photograph of {person}, {_outfit(film, shot)}, in {place}, framed {framing}.")
        parts.append("She looks straight at us, her lips closed and relaxed, the corners of her mouth level, her face "
                     "clear and unblocked, her eyes calm.")
    elif shot.has_person:
        parts.append(_sentence(f"Photograph: {description or shot.goal or (shot.beats[0] if shot.beats else place)}")
                     if description or shot.goal or shot.beats else f"Photograph of a person in {place}.")
        parts.append(_sentence(f"The setting is {place}"))
    else:
        parts.append(_sentence(f"Photograph of {description or shot.goal or place}"))
    wears = (shot.extra or {}).get("wears")
    if wears:
        parts.append(_sentence(f"She wears {wears}"))
    elif shot.has_person and shot.kind != "vocal" and find("water", place):
        parts.append(_sentence(f"She is {_outfit(film, shot)}"))
    if film.get("world"):
        parts.append(_sentence(film["world"]))
    parts += [EDGE_LINE, NO_TEXT_LINE]
    return " ".join(parts)


def edit_prompt(change: str) -> str:
    """One change to an existing still, everything else kept, for an edit model given the still as reference 0."""
    return (f"The photograph in <ref_image_0>, exactly as it is, with one change: {change.rstrip('.')}. Everything else "
            f"stays exactly as it is. {EDGE_LINE} {NO_TEXT_LINE}")


def render_prompt(film: Mapping, shot, task: Mapping, lines: Mapping | None = None) -> str:
    """The right builder for the shot's kind."""
    if shot.kind == "vocal":
        return sung_prompt(film, shot, task, lines)
    if shot.kind == "mute":
        return silent_prompt(film, shot, task)
    return plate_prompt(film, shot, task)


def write_prompts(film: Mapping, shots: Sequence, tasks: Mapping[str, Mapping],
                  lines: Mapping | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """(render prompts, still prompts) for every shot of a plan."""
    take_files = {shot.key: render_prompt(film, shot, tasks[shot.key], lines) for shot in shots}
    keyframes = {shot.key: still_prompt(film, shot) for shot in shots}
    return take_files, keyframes


__all__ = ["edit_prompt", "framing_phrase", "plate_prompt", "render_prompt", "silent_prompt", "still_prompt",
           "sung_prompt", "sung_words", "write_prompts"]
