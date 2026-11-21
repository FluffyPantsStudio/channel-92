"""Checks on first-frame stills, from their records in stills/<key>.json.

The records say how a still was made and what a judge found when looking at it. Whether hands, a smile or a mark
are right in the picture is never guessed here: a judge or the person answers the reviewer questions
(`engine.review_items`) and the answers land in the record's judge items, which these checks then read.
"""

from __future__ import annotations

from ..aspects import ASPECTS, matches_aspect
from ..cast import PLACE_VIEWS, cast_of, missing_views, place_views, places_of, required_views, views_of
from .book import Book
from .registry import rule


def _records(book: Book):
    for shot in book.shots:
        yield shot, book.keyframes.get(shot.key)


def _item(record: dict | None, name: str) -> str | None:
    return (((record or {}).get("judge") or {}).get("items") or {}).get(name)


def _bad(answer: str | None) -> bool:
    return answer is not None and not answer.strip().upper().startswith("PASS")


def shows_body(book: Book, shot, record: dict | None) -> bool:
    """The still shows the person below the collar."""
    framing = (record or {}).get("crop_kind") or shot.framing
    if framing:
        return "collar" not in framing.lower() and "face" not in framing.lower()
    if shot.kind == "vocal":
        crop = shot.crop if shot.crop is not None else (record or {}).get("crop_keep")
        return crop is None or crop >= 0.75
    return True


@rule("L010")
def judged_at_full_size(book):
    for shot, record in _records(book):
        judge = (record or {}).get("judge")
        if not judge:
            yield shot.key, "no judge record for the first frame"
        elif str(judge.get("verdict", "")).upper() != "PASS" or not judge.get("full_size"):
            yield shot.key, f"judge record: {judge.get('verdict')}, full size {bool(judge.get('full_size'))}"


@rule("L014")
def smiling_still(book):
    for shot, record in _records(book):
        if shot.kind == "vocal" and _bad(_item(record, "mouth")):
            yield shot.key, f"the judge found the mouth: {_item(record, 'mouth')}"


@rule("L013")
def not_from_hero(book):
    figures = book.film.get("characters") or {}
    for shot, record in _records(book):
        if shot.view and shot.view != "front":
            continue                      # seen from another angle: CHR3 asks for that angle's view, not the hero
        refs = set((record or {}).get("refs") or [])
        for name in (record or {}).get("figures") or []:
            hero = (figures.get(name) or {}).get("hero")
            if hero and hero not in refs:
                yield shot.key, f"{name}'s still is not made from the hero still {hero}"


@rule("L015")
def face_not_last(book):
    for shot, record in _records(book):
        steps = [str(row.get("step")) for row in (record or {}).get("history") or []]
        if "face" in steps:
            last_face = len(steps) - 1 - steps[::-1].index("face")
            if "full" in steps[last_face + 1:]:
                yield shot.key, "a whole-picture edit after the face step"


@rule("L016b")
def flat_noise_rose(book):
    for shot, record in _records(book):
        noise = (record or {}).get("noise") or {}
        if noise.get("provenance") and noise.get("after") is not None and noise["after"] > noise["provenance"] * 1.25:
            yield shot.key, f"flat-area noise {noise['provenance']} in the source, {noise['after']} now"


@rule("L017")
def body_panel_missing(book):
    figures = book.film.get("characters") or {}
    for shot, record in _records(book):
        if not record or not shows_body(book, shot, record):
            continue
        refs = set(record.get("refs") or [])
        for name in record.get("figures") or []:
            body = (figures.get(name) or {}).get("body")
            if not body:
                yield shot.key, f"shows {name} below the collar and the film has no body panel for {name}"
            elif body not in refs:
                yield shot.key, f"shows {name} below the collar without the body panel {body}"


@rule("L018")
def marks_wrong(book):
    for shot, record in _records(book):
        if _bad(_item(record, "marks")):
            yield shot.key, f"the judge found the marks: {_item(record, 'marks')}"


@rule("L021")
def prop_without_reference(book):
    props = book.film.get("props") or {}
    for shot in book.shots:
        text = book.still_prompts.get(shot.key)
        if not text:
            continue
        refs = set((book.keyframes.get(shot.key) or {}).get("refs") or [])
        for name, data in props.items():
            words = tuple(w.lower() for w in [name] + list((data or {}).get("words") or []))
            if any(found_word in text.lower() for found_word in words) and (data or {}).get("ref") not in refs:
                yield shot.key, f"names the {name} without its reference {(data or {}).get('ref')}"


@rule("L022")
def identity_missing(book):
    figures = cast_of(book.film)
    for shot, record in _records(book):
        refs = set((record or {}).get("refs") or [])
        for name in (record or {}).get("figures") or []:
            person = figures.get(name) or {}
            if shot.view and shot.view != "front":
                identity = views_of(person).get(shot.view)      # seen from the side or back: that view is the identity
            else:
                identity = person.get("identity") or person.get("hero") or views_of(person).get("front")
            if not identity or identity not in refs:
                yield shot.key, f"shows {name} with no identity reference"


@rule("L104")
def blotchy_flat_area(book):
    median = book.film.get("flat_energy_median")
    if not median:
        return
    for shot, record in _records(book):
        energy = (record or {}).get("flat_energy")
        if energy is not None and energy > 1.5 * median:
            yield shot.key, f"flat-area energy {energy} against the film's median {median}"



def _shape(width: int, height: int) -> str:
    return f"{width}x{height} ({width / height:.2f})" if height else f"{width}x{height}"


@rule("AR1")
def picture_shape(book):
    chosen = (book.film.get("setup") or {}).get("aspect")
    if chosen not in ASPECTS:
        return
    frame = book.film.get("frame")
    shaped = isinstance(frame, (list, tuple)) and len(frame) == 2
    if shaped and not matches_aspect(int(frame[0]), int(frame[1]), chosen):
        yield None, f"the render frame is {_shape(*map(int, frame))}, not the chosen {chosen}"
    for shot in book.shots:
        size = book.pictures.get(shot.key)
        if size is not None and not matches_aspect(size[0], size[1], chosen):
            yield shot.key, f"the still is {_shape(*size)}, not the chosen {chosen}"


@rule("CHR1")
def sheet_incomplete(book):
    """Every character has a reference sheet: one picture per view, each a file in the film folder."""
    for name, person in cast_of(book.film).items():
        absent = missing_views(person, book.rules_dir)
        if absent:
            yield None, f"{name}'s sheet has no {', '.join(absent)} view"
        for view, path in views_of(person).items():
            if not book.exists(path):
                yield None, f"{name}'s {view} view {path} is not in the film folder"


def _measured(book: Book):
    """(name, view, path, measurement) for every sheet picture the film names and the folder holds."""
    for name, person in cast_of(book.film).items():
        for view, path in views_of(person).items():
            if path in book.plain:
                yield name, view, path, book.plain[path]


@rule("CHR2")
def sheet_has_environment(book):
    """Every view is the figure alone on a plain studio backdrop: a coarse screen measured on the picture (a busy
    place fails; a flat-coloured wall is for the judge and the person at gate 3)."""
    for name, view, path, found in _measured(book):
        if isinstance(found, str):
            yield None, (f"{name}'s {view} view cannot be checked for a plain background ({found}); save it as an "
                         "8-bit RGB PNG, not interlaced or indexed")
        elif found.environment():
            yield None, f"{name}'s {view} view {path}: {found.environment()}"


@rule("CHR4")
def figure_too_small(book):
    """Every view is a tall portrait picture the figure fills, not a figure standing small in a wide frame."""
    for name, view, path, found in _measured(book):
        if not isinstance(found, str) and found.small():
            yield None, f"{name}'s {view} view {path} {found.small()}"


def _view_problem(book: Book, shot, record: dict, name: str) -> str | None:
    views = views_of(cast_of(book.film).get(name) or {})
    refs = set(record.get("refs") or [])
    if shot.view not in required_views(book.rules_dir):
        return f"view {shot.view!r} is not one of {', '.join(required_views(book.rules_dir))}"
    wanted = views.get(shot.view)
    if not wanted:
        return f"{name} has no {shot.view} view on the sheet"
    if wanted not in refs:
        return f"is seen from the {shot.view} but {name}'s still lacks the {shot.view} view {wanted}"
    front = views.get("front")
    if shot.view == "back" and front and front in refs:
        return f"is seen from the back but {name}'s still carries the front view {front}, whose face is copied onto it"
    return None


@rule("CHR3")
def still_without_its_view(book):
    """A still seen from an angle takes that angle's reference, and a back view never carries the front face."""
    for shot, record in _records(book):
        if not shot.view or not record:
            continue
        for name in record.get("figures") or []:
            problem = _view_problem(book, shot, record, name)
            if problem:
                yield shot.key, problem


@rule("PL1")
def place_sheet_incomplete(book):
    """Every registered place has a wide picture, one from about 90 degrees round, a landmark close-up and the light's
    direction in one line, so every shot there matches the same place."""
    for name, place in places_of(book.film).items():
        views = place_views(place)
        absent = [view for view in PLACE_VIEWS if view not in views]
        if absent:
            yield None, f"the place {name} has no {', '.join(absent)} picture"
        for view, path in views.items():
            if not book.exists(path):
                yield None, f"the place {name}'s {view} picture {path} is not in the film folder"
        if not str(place.get("light") or "").strip():
            yield None, f"the place {name} has no `light` note (the practical light source and which side it is on)"


@rule("PL2")
def still_without_its_place(book):
    """A still of a shot in a registered place (`scene:` names it) carries that place's wide picture."""
    places = places_of(book.film)
    for shot, record in _records(book):
        place = places.get(shot.scene or "")
        wide = place_views(place or {}).get("wide")
        if place is not None and record and (not wide or wide not in (record.get("refs") or [])):
            yield shot.key, f"is in the place {shot.scene} but its still lacks the place's wide picture {wide or '(none)'}"
