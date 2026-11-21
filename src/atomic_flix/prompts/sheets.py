"""Prompts for a character's reference sheet, modelled on a studio reference board: head-and-shoulders views from every
side and full-length views, each a TALL PORTRAIT picture the figure fills, on a plain studio backdrop.

A reference with a street behind it carries the street into every shot made from it, and one picture of a face is the
only angle a model knows. A small figure in a wide frame teaches a model little of the face. So each view of each
character is a separate tall picture the figure fills (`cast.py` measures the shape and the fill on the picture). The
front view is made first; the other views are made from it with the still graph's image input, so they are the same
person.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from ..cast import cast_of, kind_of, required_views, views_of
from .builders import NO_TEXT_LINE

BACKGROUND = ("on a plain neutral studio backdrop, flat grey or softly lit, with no environment: no floor markings, "
              "no horizon, no props, no scenery, no other people")
BUST_LAYOUT = ("A tall portrait picture, three to four: the head and shoulders fill the picture from the top of the hair "
               "to the chest. One figure only. Soft even light.")
BODY_LAYOUT = ("A tall portrait picture, two to three: the whole figure from head to feet fills the height of the "
               "picture, standing in a relaxed neutral pose. One figure only. Soft even light.")
SIZES = {"bust": (1152, 1536), "body": (1024, 1536)}
VIEW_WORDS = {
    "front": "front view, straight on to the camera",
    "three_quarter": "three-quarter view, turned about 45 degrees from the camera",
    "profile": "side view in full profile, facing the left of the picture",
    "back": "back view, seen from directly behind, facing away from the camera so that no face shows",
    "body_front": "full-length front view, straight on to the camera",
    "body_three_quarter": "full-length three-quarter view, turned about 45 degrees from the camera",
    "body_back": "full-length back view, seen from directly behind, facing away so that no face shows",
}


RECIPE = (
    "An image-edit model keeps the FIRST reference's framing and pose: put the picture that sets the pose first.",
    "Head views from the front: the approved face as the only reference; say 'head and shoulders, the face filling the "
    "upper half'.",
    "Turned heads: a POSE PLATE as the first and only reference (a grey mannequin bust with a bald, faceless egg head, no "
    "hair), the person in words. A plate with a face or hair leaks that face into the character, and a face picture as a "
    "second reference pulls the head back to the front.",
    "Full-length views: reference 1 is any plain full-figure front plate (framing only), reference 2 the face, with the "
    "words 'take nothing else from reference 1'. Body plates are clothed in a plain grey coverall: never nude, for any "
    "character, and above all never for a child.",
    "Check every try: a face-similarity filter (CCIP) first, which tells characters apart but not a drifted face of the "
    "same character, then a cold judge at full size.",
)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "character"


def unique_slugs(names) -> dict[str, str]:
    """A file-name stem for each character, never the same for two (a second `Mira K` after `Mira-K` gets `-2`)."""
    taken: dict[str, str] = {}
    for name in names:
        stem, number = slug(name), 1
        while stem in taken.values():
            number += 1
            stem = f"{slug(name)}-{number}"
        taken[name] = stem
    return taken


def picture_path(stem: str, view: str) -> str:
    """Where a view's picture goes by default: refs/STEM-VIEW.png."""
    return f"refs/{stem}-{view.replace('_', '-')}.png"


def sheet_prompt(name: str, who: str, view: str, outfit: str = "", style: str = "") -> str:
    """The prompt for one view of one character; STYLE is the film's own drawing style, said once."""
    look = VIEW_WORDS.get(view, f"{view.replace('_', ' ')} view")
    layout = BODY_LAYOUT if kind_of(view) == "body" else BUST_LAYOUT
    parts = [f"A character reference picture of {name}: {' '.join(who.split()).rstrip(' .')}."]
    if outfit:
        parts.append(f"{name} is {' '.join(outfit.split()).rstrip(' .')}.")
    if style:
        parts.append(f"Drawn in {' '.join(style.split()).rstrip(' .')}.")
    parts += [f"{look[:1].upper()}{look[1:]}, {BACKGROUND}.", layout, NO_TEXT_LINE]
    return " ".join(parts)


def _outfit(film: Mapping, name: str, person: Mapping) -> str:
    if person.get("outfit"):
        return str(person["outfit"])
    star = (film.get("star") or {}).get("name")
    wardrobe = film.get("wardrobe") or {}
    return str(next(iter(wardrobe.values()), "")) if name == star else ""


def sheet_requests(film: Mapping, rules_dir: Path | None = None) -> list[dict]:
    """One row per character view the film has not named yet: name, view, prompt and the picture to make. A character
    with no `who` (the one sentence that says who they are) cannot be drawn, and is named in `problems`."""
    rows, problems = [], []
    cast = cast_of(film)
    stems = unique_slugs(cast)
    for name, person in cast.items():
        who = str(person.get("who") or "").strip()
        have = views_of(person)
        for view in required_views(rules_dir):
            if view in have:
                continue
            if not who:
                problems.append(f"{name} has no `who` in film.json: one sentence from canon saying who they are")
                break
            rows.append({"name": name, "view": view, "stem": stems[name], "picture": picture_path(stems[name], view),
                         "size": list(SIZES[kind_of(view)]),
                         "prompt": sheet_prompt(name, who, view, _outfit(film, name, person),
                                                str(film.get("style") or ""))})
    return [{"problems": sorted(set(problems))}] + rows if problems else rows


def write_sheet_prompts(film: Mapping, root: Path, rules_dir: Path | None = None,
                        overwrite: bool = False) -> list[tuple[dict, Path, bool]]:
    """plan/refs/STEM-VIEW.prompt.txt for every missing view, as (row, path, written). A prompt file that is there
    already is kept (a person may have edited it) unless OVERWRITE. A character with no `who` raises ValueError."""
    rows = sheet_requests(film, rules_dir)
    if rows and "problems" in rows[0]:
        raise ValueError("; ".join(rows[0]["problems"]))
    folder = Path(root) / "plan" / "refs"
    folder.mkdir(parents=True, exist_ok=True)
    made = []
    for row in rows:
        path = folder / f"{row['stem']}-{row['view'].replace('_', '-')}.prompt.txt"
        keep = path.exists() and not overwrite
        if not keep:
            path.write_text(row["prompt"] + "\n", encoding="utf-8", newline="\n")
        made.append((row, path, not keep))
    return made
