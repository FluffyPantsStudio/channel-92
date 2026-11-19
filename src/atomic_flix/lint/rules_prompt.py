"""Checks on the words sent to a model: render prompts (vocal, silent, cutaway) and first-frame still prompts."""

from __future__ import annotations

import re
from typing import Iterator

from ..plan.vocab import camera_moves, pattern, terms
from ..plan.words import is_wordless
from ..prompts.builders import EDGE_LINE, NO_TEXT_LINE, framing_phrase
from .book import Book
from .registry import rule
from .text import found, near_after, quoted, sentences, step_rows, strip_quoted

HANDLE_VERBS = re.compile(r"\b(hold|holds|holding|held|carr(?:y|ies|ying)|brings?|bringing|picks? up|offers?|"
                          r"offering|shows?|showing|grips?|clutch(?:es)?)\b", re.IGNORECASE)
SKIP_WORDS = {"a", "an", "the", "her", "his", "its", "our", "their", "out", "up", "forward", "one", "two", "both",
              "small", "little", "tiny", "big", "large", "in", "front", "of", "to", "toward", "towards", "each",
              "other", "other's"}
VAGUE = {"something", "anything", "object", "it", "thing", "things", "stuff"}
NOT_OBJECTS = {"gaze", "chin", "head", "breath", "eyes", "eye", "pose", "note", "line", "position", "still", "us",
               "look", "stare", "face", "smile", "posture", "hands", "hand", "arms", "lips", "mouth"}
NAME_WORD = re.compile(r"\b[A-Z][\w'-]*[a-z][\w'-]*\b")


def _rd(book: Book):
    return book.rules_dir


def clip_prompts(book: Book, kinds: tuple[str, ...] | None = None) -> Iterator[tuple]:
    for shot in book.shots:
        text = book.prompts.get(shot.key)
        if text and (kinds is None or shot.kind in kinds):
            yield shot, text


def keyframes(book: Book) -> Iterator[tuple]:
    for shot in book.shots:
        text = book.still_prompts.get(shot.key)
        if text:
            yield shot, text


def every_prompt(book: Book) -> Iterator[tuple]:
    yield from clip_prompts(book)
    yield from keyframes(book)


def _listed(words: list[str]) -> str:
    return ", ".join(dict.fromkeys(word.lower() for word in words))


@rule("H1")
def hands_named(book):
    for shot, text in clip_prompts(book, ("vocal",)):
        words = found("hands", strip_quoted(text), _rd(book))
        if words:
            yield shot.key, f"names {_listed(words)} in a vocal prompt"


@rule("H2")
def smile_on_her_mouth(book):
    negation = pattern(terms("negation", _rd(book)))
    smiles = pattern(terms("smile", _rd(book)))
    for shot, text in clip_prompts(book, ("vocal",)):
        bare = strip_quoted(text)
        hits = []
        for sentence in sentences(bare):
            low = sentence.lower()
            for match in smiles.finditer(sentence):
                if "in her eyes" in low or "her eyes smile" in low:
                    continue
                if negation.search(sentence[max(0, match.start() - 25): match.start()]):
                    continue                  # a forbidden smile is H3's finding
                hits.append(match.group(0))
        hits += found("warm", bare, _rd(book))
        if hits:
            yield shot.key, f"smile or warmth while she sings: {_listed(hits)}"


@rule("H3")
def face_negative(book):
    for shot, text in clip_prompts(book):
        if not shot.has_person:
            continue
        hits = [match.group(0) for match in near_after("negation", "face-acts", strip_quoted(text), 25, _rd(book))]
        if hits:
            yield shot.key, f"says what her face must not do: {'; '.join(hits)}"


@rule("M1")
def more_than_one_mood(book):
    tone = (book.film.get("tone") or "").lower()
    for shot, text in clip_prompts(book, ("vocal",)):
        bare = strip_quoted(text).lower()
        has_tone = bool(tone) and tone in bare
        rest = bare.replace(tone, " ") if tone else bare
        moods = list(dict.fromkeys(found("mood", rest, _rd(book))))
        if (has_tone and moods) or len(moods) >= 2:
            yield shot.key, f"mood words beside the tone: {', '.join(moods)}"


@rule("F1")
def framing_matches_crop(book):
    for shot, text in clip_prompts(book, ("vocal",)):
        crop = shot.crop if shot.crop is not None else (book.keyframes.get(shot.key) or {}).get("crop_keep")
        if crop is None and not shot.framing:
            continue
        want = framing_phrase(crop, shot.framing)
        low = text.lower()
        says = [phrase for phrase in ("from the chest up", "from the collar up") if phrase in low]
        if not says:
            yield shot.key, f"no framing phrase; the still is {want}"
        elif says != [want]:
            yield shot.key, f"says {' and '.join(says)} but the still (crop {crop}) is {want}"


@rule("V1")
def facing_clause(book):
    for shot, text in clip_prompts(book, ("vocal",)):
        low = text.lower()
        if "never turns away" not in low and "faces us for the whole shot" not in low:
            yield shot.key, "no facing clause ('she never turns away')"


@rule("Q1")
def equipment_named(book):
    for shot, text in every_prompt(book):
        words = found("equipment", strip_quoted(text), _rd(book))
        if words:
            yield shot.key, f"names equipment: {_listed(words)}"


@rule("N2")
def off_screen_person(book):
    figures = pattern(terms("persons-off", _rd(book)))
    away = pattern(terms("off-screen", _rd(book)))
    for shot, text in clip_prompts(book):
        for sentence in sentences(strip_quoted(text)):
            if figures.search(sentence) and away.search(sentence):
                yield shot.key, f"names someone off screen: {sentence!r}"


def _context(book: Book, shot) -> str:
    props = " ".join(book.film.get("props") or {})
    record = book.keyframes.get(shot.key) or {}
    return " ".join(filter(None, [shot.goal, shot.place, record.get("description"), props,
                                  (shot.extra or {}).get("props")])).lower()


@rule("A1")
def object_from_nowhere(book):
    for shot, text in clip_prompts(book):
        context = _context(book, shot)
        bare = strip_quoted(text)
        for match in HANDLE_VERBS.finditer(bare):
            following = re.findall(r"[a-z][a-z-]*", bare[match.end(): match.end() + 60].lower())
            words = [word for word in following if word not in SKIP_WORDS][:2]
            if not words or words[0] in NOT_OBJECTS:
                continue
            if words[0] in VAGUE:
                yield shot.key, f"'{match.group(0)} {words[0]}': an object with no source"
            elif not any(word.rstrip("s") in context for word in words):
                yield shot.key, f"'{match.group(0)} {' '.join(words)}' is not in the goal, the still or the props"


@rule("MK1")
def mark_not_in_still(book):
    for shot, text in clip_prompts(book):
        visible = set((book.keyframes.get(shot.key) or {}).get("visible_marks") or [])
        bare = strip_quoted(text)
        for person in (book.film.get("characters") or {}).values():
            for mark in person.get("marks") or []:
                words = mark.get("words") or [mark["name"]]
                if pattern(tuple(w.lower() for w in words)).search(bare) and mark["name"] not in visible:
                    yield shot.key, f"names the {mark['name']}, which the still does not show"


def _prop_words(book: Book) -> list[str]:
    words = []
    for name, data in (book.film.get("props") or {}).items():
        words += [name] + list((data or {}).get("words") or [])
    return [word.lower() for word in words]


@rule("L040")
def prop_negative(book):
    props = _prop_words(book)
    if not props:
        return
    prop_pattern = pattern(tuple(props))
    acts = re.compile(r"\b(never|not|no|without)\b.{0,20}\b(lift|slip|fall|move|turn|open|change|shift|tilt)s?\b",
                      re.IGNORECASE)
    for shot, text in clip_prompts(book):
        for sentence in sentences(strip_quoted(text)):
            if prop_pattern.search(sentence) and acts.search(sentence):
                yield shot.key, f"tells a prop what not to do: {sentence!r}"


@rule("L044")
def people_contradicted(book):
    nobody = re.compile(r"\bno (people|faces|one|person)\b|\bnobody appears\b|\bno one appears\b", re.IGNORECASE)
    name = ((book.film.get("star") or {}).get("name") or "").strip()
    for shot, text in clip_prompts(book):
        if shot.has_person and nobody.search(text):
            yield shot.key, "says nobody appears, but the shot has people"
        if name and shot.count > 1 and re.search(rf"\bonly one {re.escape(name)}\b", text, re.IGNORECASE):
            yield shot.key, f"says only one {name}, but the shot has {shot.count}"


@rule("L051")
def closing_rest_holds(book):
    for shot, text in clip_prompts(book, ("vocal",)):
        rows = step_rows(text)
        if not rows:
            continue
        body = strip_quoted(rows[-1][2])
        if quoted(rows[-1][2]):
            if "then " not in body:
                continue
            body = body.rsplit("then ", 1)[1]
        words = found("hold", body, _rd(book))
        if words:
            yield shot.key, f"the closing rest says {_listed(words)}"


@rule("L054")
def wordless_without_round_mouth(book):
    for shot, text in clip_prompts(book, ("vocal",)):
        for start, end, body in step_rows(text):
            if any(is_wordless(words) for words in quoted(body)) and "round oo" not in body.lower():
                yield shot.key, f"{start}-{end}s: a wordless note without 'her lips in a soft round oo'"


def _camera_line(text: str) -> str:
    rows = [row for row in (text or "").splitlines() if row.strip().lower().startswith("camera:")]
    return " ".join(rows)


@rule("CM1")
def move_without_end_still(book):
    for shot, text in clip_prompts(book):
        cam_move = shot.cam_move or _camera_line(text)
        if camera_moves(cam_move, _rd(book)) and (not shot.closing_still or shot.closing_still == shot.still_path):
            yield shot.key, f"the camera moves ({cam_move.strip()!r}) with no drawn end still"


@rule("L090")
def outfit_incomplete(book):
    for shot, text in clip_prompts(book, ("vocal",)):
        if "collar" in framing_phrase(shot.crop, shot.framing):
            continue
        worn = re.search(r"\bwearing\b([^.;]*)", strip_quoted(text), re.IGNORECASE)
        if not worn:
            yield shot.key, "no outfit stated ('wearing ...')"
            continue
        garments = set(word.lower() for word in found("garments", worn.group(1), _rd(book)))
        if len(garments) < 2:
            yield shot.key, f"the outfit names {len(garments)} garment(s) for a frame wider than the collar"


@rule("K1")
def grain_words(book):
    for shot, text in every_prompt(book):
        words = found("grain", strip_quoted(text), _rd(book))
        if words:
            yield shot.key, f"grain or texture words: {_listed(words)}"


@rule("L003")
def never_list(book):
    never = [word.lower() for word in book.film.get("never") or []]
    if not never:
        return
    variants = tuple(dict.fromkeys(v for word in never for v in (word, word + "s", word + "es")))
    hits_of = pattern(variants)
    for shot, text in every_prompt(book):
        hits = [match.group(0) for match in hits_of.finditer(strip_quoted(text))]
        if hits:
            yield shot.key, f"names what the film never shows: {_listed(hits)}"


@rule("S3")
def drawn_medium(book):
    if (book.film.get("look") or "photo") == "illustration":
        return
    for shot, text in every_prompt(book):
        words = found("medium", strip_quoted(text), _rd(book))
        if words:
            yield shot.key, f"a drawn or painted medium in a photographic film: {_listed(words)}"


@rule("W1")
def water_without_clothes(book):
    for shot, text in keyframes(book):
        bare = strip_quoted(text)
        person = shot.has_person or found("person", bare, _rd(book))
        if person and found("water", bare, _rd(book)) and not found("garments", bare, _rd(book)):
            yield shot.key, "a person in water with no garment named"


@rule("IMG1")
def still_ending(book):
    tail = f"{EDGE_LINE} {NO_TEXT_LINE}"
    for shot, text in keyframes(book):
        if not " ".join(text.split()).endswith(tail):
            yield shot.key, "is missing its closing frame-filling and no-lettering sentences"


@rule("S1")
def posture_rules(book):
    for shot, text in clip_prompts(book, ("vocal",)):
        words = found("posture", strip_quoted(text), _rd(book))
        if words:
            yield shot.key, f"posture rules in a performance: {_listed(words)}"


@rule("S2")
def sung_step_without_movement(book):
    for shot, text in clip_prompts(book, ("vocal",)):
        for start, end, body in step_rows(text):
            if not quoted(body):
                continue
            after = strip_quoted(body).split('""', 1)[-1]
            if not re.search(r"[a-z]{3,}", after.lower()):
                yield shot.key, f"{start}-{end}s: a sung step with no movement clause"


@rule("T1")
def steps_whole_and_contiguous(book):
    for shot, text in clip_prompts(book):
        rows = step_rows(text)
        if not rows:
            yield shot.key, "no timed steps"
            continue
        seconds = (book.tasks.get(shot.key) or {}).get("seconds")
        problems = []
        if rows[0][0] != 0:
            problems.append(f"starts at {rows[0][0]} s")
        for (a, b, _), (c, _, _) in zip(rows, rows[1:]):
            if b != c:
                problems.append(f"{a}-{b}s is followed by a step from {c} s")
        problems += [f"{a}-{b}s is empty" for a, b, _ in rows if b <= a]
        if seconds is not None and rows[-1][1] != seconds:
            problems.append(f"ends at {rows[-1][1]} s, the render is {seconds} s")
        if problems:
            yield shot.key, "; ".join(problems)


@rule("T3")
def stop_without_pause(book):
    for shot, text in clip_prompts(book, ("vocal",)):
        task = book.tasks.get(shot.key) or {}
        spans = {(row[0], row[1]): keys for row, keys in zip(task.get("steps", []), task.get("step_lines", []))}
        for start, end, body in step_rows(text):
            for words in quoted(body):
                if not re.search(r"\.\s+\w", words):
                    continue
                keys = [k for k in (spans.get((start, end)) or shot.sings) if k in book.lines]
                lines = sorted((book.lines[k] for k in keys), key=lambda line: line.start)
                paused = any(b - a >= 0.25 for line in lines for a, b in line.gaps)
                paused |= any(right.start - left.end >= 0.25 for left, right in zip(lines, lines[1:]))
                if lines and not paused:
                    yield shot.key, f"{start}-{end}s: a full stop in words sung straight through"


@rule("N1")
def names_not_allowed(book):
    allow = {name.lower() for name in book.film.get("allow") or []}
    allow |= {((book.film.get("star") or {}).get("name") or "").lower()}
    allow |= {name.lower() for name in (book.film.get("characters") or {})}
    allow |= {word.lower() for word in ("I", "Camera", "Photograph", "OK")}
    for shot, text in every_prompt(book):
        names = []
        for sentence in sentences(strip_quoted(text).replace("<ref_image_0>", "")):
            for match in NAME_WORD.finditer(sentence):
                if match.start() == 0 or sentence[: match.start()].strip() in ("", "-"):
                    continue
                if match.group(0).lower() not in allow:
                    names.append(match.group(0))
        if names:
            yield shot.key, f"names not on the allow list: {', '.join(dict.fromkeys(names))}"
