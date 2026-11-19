"""Cold review rounds before the person sees a cut, and how they gate v1."""

import pytest

from atomic_flix.gates import GATES, Answer, GateBook, GateRefused, ReviewLoop, ReviewRound
from atomic_flix.gates.review import MAX_ROUNDS

T0 = "2026-11-21T09:00:00+00:00"


def yes(words="yes", approves=True):
    return Answer(words=words, by="Test Person", provenance="person", at=T0, approves=approves)


def before_v1():
    book = GateBook.empty()
    for spec in GATES[:-1]:
        book = book.ask(spec.id, ["shown"], at=T0).answer(spec.id, yes())
    return book


def round_(cut, reviewer, errors=(), cold=True):
    return ReviewRound(cut=cut, reviewer=reviewer, at=T0, errors=tuple(errors), cold=cold)


def test_rounds_reviewers_and_open_errors_are_tracked():
    loop = ReviewLoop()
    loop = loop.add(round_("cuts/v01.mp4", "r1", ["S04 freezes at the end", "N08 does not walk"]))
    loop = loop.add(round_("cuts/v02.mp4", "r2", ["N08 does not walk"]))
    assert len(loop.rounds) == 2
    assert loop.reviewers == ("r1", "r2")
    assert loop.open_errors == ("N08 does not walk",)
    assert not loop.is_clean


def test_a_round_with_no_errors_is_clean_for_its_own_cut_only():
    loop = ReviewLoop().add(round_("cuts/v01.mp4", "r1", ["x"])).add(round_("cuts/v02.mp4", "r2"))
    assert loop.is_clean
    assert loop.ready_for("cuts/v02.mp4")
    assert not loop.ready_for("cuts/v01.mp4")
    assert not ReviewLoop().ready_for("cuts/v01.mp4")


def test_a_reviewer_is_fresh_only_once():
    loop = ReviewLoop().add(round_("cuts/v01.mp4", "r1", ["x"]))
    with pytest.raises(GateRefused, match="fresh"):
        loop.add(round_("cuts/v02.mp4", "r1"))


def test_a_reviewer_who_read_the_prompts_is_not_cold():
    with pytest.raises(GateRefused, match="prompts"):
        round_("cuts/v01.mp4", "r1", cold=False)


def test_progress_stops_when_errors_do_not_fall_over_two_rounds():
    loop = ReviewLoop()
    for n, count in enumerate([3, 2, 3], start=1):
        loop = loop.add(round_(f"cuts/v0{n}.mp4", f"r{n}", [f"e{i}" for i in range(count)]))
    assert loop.stalled
    assert "3" in loop.stalled
    assert loop.ready_for("cuts/v03.mp4")


def test_falling_errors_are_progress():
    loop = ReviewLoop()
    for n, count in enumerate([3, 2, 1], start=1):
        loop = loop.add(round_(f"cuts/v0{n}.mp4", f"r{n}", [f"e{i}" for i in range(count)]))
    assert loop.stalled is None
    assert not loop.ready_for("cuts/v03.mp4")


def test_too_many_rounds_is_a_stall():
    loop = ReviewLoop()
    for n in range(MAX_ROUNDS):
        errors = [f"e{i}" for i in range(MAX_ROUNDS - n)]
        loop = loop.add(round_(f"cuts/v{n:02d}.mp4", f"r{n}", errors))
    assert loop.stalled


def test_v1_is_refused_until_a_cold_reviewer_passes_that_cut():
    book = before_v1()
    with pytest.raises(GateRefused, match="review"):
        book.ask("v1", ["cuts/v01.mp4"], at=T0)
    book = book.reviewed("cuts/v01.mp4", "r1", ["S12 freezes"], at=T0)
    with pytest.raises(GateRefused, match="review"):
        book.ask("v1", ["cuts/v01.mp4"], at=T0)
    book = book.reviewed("cuts/v02.mp4", "r2", [], at=T0)
    with pytest.raises(GateRefused):
        book.ask("v1", ["cuts/v01.mp4"], at=T0)
    asked = book.ask("v1", ["cuts/v02.mp4", "review/v02/"], at=T0)
    assert asked.record("v1").state == "asked"
    assert asked.record("v1").open_errors == ()


def test_a_stalled_review_goes_to_the_person_with_its_list():
    book = before_v1()
    for n, count in enumerate([2, 2, 2], start=1):
        book = book.reviewed(f"cuts/v0{n}.mp4", f"r{n}", [f"N0{i} jumps" for i in range(count)], at=T0)
    asked = book.ask("v1", ["cuts/v03.mp4"], at=T0)
    assert asked.record("v1").open_errors == ("N00 jumps", "N01 jumps")


def test_the_persons_answer_on_v1_starts_a_new_review_loop():
    book = before_v1().reviewed("cuts/v01.mp4", "r1", [], at=T0)
    book = book.ask("v1", ["cuts/v01.mp4"], at=T0)
    book = book.answer("v1", yes("the star is on the wrong side", approves=False))
    assert book.review.rounds == ()
    assert len(book.past_reviews) == 1
    with pytest.raises(GateRefused, match="fresh"):
        book.reviewed("cuts/v02.mp4", "r1", [], at=T0)
    book = book.reviewed("cuts/v02.mp4", "r2", [], at=T0).ask("v1", ["cuts/v02.mp4"], at=T0)
    book = book.answer("v1", yes("video is ready, all good"))
    assert book.passed("v1")
    assert book.next_gate() is None
