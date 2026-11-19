"""vet and preflight over a whole book.

`vet` runs every rule. `preflight` runs every rule, lists every question that needs eyes on a picture, estimates the
batch's GPU hours, and is blocked when any rule blocks or any question is unanswered or failed. A blocked preflight
spends no GPU time.
"""

from __future__ import annotations

from .book import Book
from .findings import ReviewItem, Verdict
from .registry import RULE_DATA, run_rules
from .rules_process import batch_of
from .rules_still import shows_body

REVIEW = {item["id"]: item for item in RULE_DATA["reviewer"]}


def _ask(shot, item_id: str, record: dict | None, **fill) -> ReviewItem:
    data = REVIEW[item_id]
    answer = (((record or {}).get("judge") or {}).get("items") or {}).get(item_id)
    question = data["question"].format(**fill)
    return ReviewItem(key=shot.key, id=item_id, question=question, lessons=tuple(data["lessons"]), answer=answer)


def review_items(book: Book) -> list[ReviewItem]:
    """The questions a judge or the person must answer for each first frame before a batch."""
    characters = book.film.get("characters") or {}
    never = ", ".join(book.film.get("never") or [])
    props = book.film.get("props") or {}
    items = []
    previous = "none, it opens the film"
    for shot in book.shots:
        record = book.keyframes.get(shot.key)
        still = (book.tasks.get(shot.key) or {}).get("still") or shot.still_path
        figures = list((record or {}).get("figures") or [])
        fill = {"still": still, "figures": ", ".join(figures) or "the person", "gaze":
                (shot.extra or {}).get("gaze") or "not stated", "before": previous, "never": never}
        if shot.has_person:
            items.append(_ask(shot, "hands", record, **fill))
        if shot.kind == "vocal":
            items.append(_ask(shot, "mouth", record, **fill))
        marks = [f"{mark['name']} ({mark.get('side', 'any side')}, {mark.get('count', 1)})"
                 for name in figures for mark in (characters.get(name) or {}).get("marks") or []]
        if marks:
            items.append(_ask(shot, "marks", record, **{**fill, "marks": "; ".join(marks)}))
        if figures:
            items.append(_ask(shot, "identity", record, **fill))
        if shot.has_person:
            items.append(_ask(shot, "gaze", record, **fill))
        if figures and shows_body(book, shot, record):
            items.append(_ask(shot, "build", record, **fill))
        if never:
            items.append(_ask(shot, "never", record, **fill))
        text = (book.still_prompts.get(shot.key) or "").lower()
        named = [name for name, data in props.items()
                 if any(word.lower() in text for word in [name] + list((data or {}).get("words") or []))]
        if named:
            items.append(_ask(shot, "prop", record, **{**fill, "props": ", ".join(named)}))
        items.append(_ask(shot, "flat", record, **fill))
        previous = f"{shot.key}, gaze {(shot.extra or {}).get('gaze') or 'not stated'}"
    return items


def vet(book: Book, scopes=None):
    """Every rule's findings, without the reviewer gate or the hours."""
    return run_rules(book, scopes)


def preflight(book: Book) -> Verdict:
    """All checks over the whole book. Blocked means: do not queue anything."""
    findings = tuple(run_rules(book))
    review = tuple(review_items(book))
    batch = batch_of(book) if book.tasks else None
    blocked = any(f.level == "block" for f in findings) or any(not item.passed for item in review)
    return Verdict(blocked=blocked, findings=findings, review=review, batch=batch)


def after_batch_questions() -> list[dict]:
    """What a cold reviewer is asked about the takes once they exist (not part of preflight)."""
    return list(RULE_DATA.get("after_the_batch", []))
