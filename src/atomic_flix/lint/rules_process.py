"""Checks before any GPU time: the approved song, licences, re-rolls, the look gate and the hours."""

from __future__ import annotations

from collections import Counter

from ..plan.estimate import estimate_batch
from .book import Book
from .registry import rule

TEST_BATCH = 3


def batch_of(book: Book):
    takes = book.batch.get("takes")
    return estimate_batch(book.tasks, takes=takes, cards=int(book.batch.get("cards", 1)))


@rule("L006")
def song_changed(book):
    approved = book.gate("song").get("sha256")
    if not approved:
        yield None, "the song has no fingerprint from gate 2"
    elif not book.song_sha256:
        yield None, "the mix file was not found to compare with the approved fingerprint"
    elif book.song_sha256 != approved:
        yield None, f"the mix changed since gate 2 ({approved[:8]} approved, {book.song_sha256[:8]} now)"


@rule("L042")
def licence_bars_release(book):
    if book.film.get("mode") != "release":
        return
    for key, task in book.tasks.items():
        graph = task.get("graph")
        if graph and (book.graphs.get(graph) or {}).get("commercial_ok") is False:
            yield key, f"{graph} may not be used commercially"


@rule("L043")
def same_reject_again(book):
    rejects = book.film.get("rejects") or {}
    for shot in book.shots:
        idea = (shot.extra or {}).get("idea")
        counts = Counter(row.get("reason") for row in rejects.get(shot.key) or [] if row.get("idea") == idea)
        for reason, count in counts.items():
            if count >= 2:
                yield shot.key, f"rejected {count} times for {reason!r} on the same idea"


@rule("L091")
def look_not_approved(book):
    vocal = [shot for shot in book.shots if shot.kind == "vocal" and shot.key in book.tasks]
    if len(vocal) > TEST_BATCH and not book.gate("look").get("words"):
        yield None, f"{len(vocal)} vocal shots and gate 3 (the look) holds no words from the person"


@rule("L127")
def over_budget(book):
    if not book.tasks:
        return
    batch = batch_of(book)
    budget = book.gate("spend").get("budget_s")
    if budget is None:
        yield None, f"{batch.takes} takes, {batch.gpu_hours:.2f} GPU h, and no approved budget (gate 5)"
    elif batch.busy_s > budget:
        yield None, f"{batch.gpu_hours:.2f} GPU h over the approved {budget / 3600:.2f} h"
