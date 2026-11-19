"""Checks on first-frame stills, from their records in stills/<key>.json.

The records say how a still was made and what a judge found when looking at it. Whether hands, a smile or a mark
are right in the picture is never guessed here: a judge or the person answers the reviewer questions
(`engine.review_items`) and the answers land in the record's judge items, which these checks then read.
"""

from __future__ import annotations

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
    figures = book.film.get("characters") or {}
    for shot, record in _records(book):
        refs = set((record or {}).get("refs") or [])
        for name in (record or {}).get("figures") or []:
            person = figures.get(name) or {}
            identity = person.get("identity") or person.get("hero")
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

