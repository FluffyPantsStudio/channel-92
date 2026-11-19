"""The six human gates as a state machine: order, refusals, person-only answers."""

import pytest

from atomic_flix.gates import GATES, Answer, GateBook, GateRefused, gate_spec

T0 = "2026-11-20T10:00:00+00:00"
T1 = "2026-11-20T10:30:00+00:00"
T2 = "2026-11-20T11:00:00+00:00"


def person(words="Drawer woman I like it", approves=True, scope="film", at=T1):
    return Answer(words=words, by="Test Person", provenance="person", at=at, scope=scope, approves=approves)


def through(book, last_gate):
    """Pass every gate up to and including LAST_GATE with a person's yes."""
    for spec in GATES:
        if spec.id == "v1":
            raise AssertionError("v1 needs a reviewed cut; pass it by hand in the test")
        book = book.ask(spec.id, ["something shown"], at=T0).answer(spec.id, person("yes"))
        if spec.id == last_gate:
            return book
    return book


def test_six_gates_in_order_each_with_one_question():
    assert [spec.id for spec in GATES] == ["concept", "song", "looks", "board", "spend", "v1"]
    assert [spec.number for spec in GATES] == [1, 2, 3, 4, 5, 6]
    for spec in GATES:
        assert spec.question.count("?") == 1
        assert spec.title and spec.shows


def test_unknown_gate_is_refused():
    with pytest.raises(GateRefused):
        gate_spec("colour")


def test_a_new_book_waits_on_the_concept():
    book = GateBook.empty()
    assert book.next_gate().id == "concept"
    assert not book.passed("concept")


def test_an_answer_needs_a_question_asked_first():
    with pytest.raises(GateRefused, match="not been asked"):
        GateBook.empty().answer("concept", person())


def test_ask_then_answer_passes_the_gate_and_moves_on():
    book = GateBook.empty().ask("concept", ["pitches/three.md"], at=T0)
    record = book.record("concept")
    assert record.state == "asked"
    assert record.shown == ("pitches/three.md",)
    assert record.question == gate_spec("concept").question
    book = book.answer("concept", person())
    assert book.passed("concept")
    assert book.next_gate().id == "song"
    assert book.record("concept").latest.words == "Drawer woman I like it"


def test_ask_and_answer_return_new_books():
    empty = GateBook.empty()
    asked = empty.ask("concept", ["x"], at=T0)
    assert empty.record("concept").state == "waiting"
    assert asked.record("concept").state == "asked"


@pytest.mark.parametrize("provenance", ["model", "claude", "judge", "driver", "", "Person"])
def test_an_answer_not_from_a_person_is_refused(provenance):
    with pytest.raises(GateRefused, match="person"):
        Answer(words="yes", by="Test Person", provenance=provenance, at=T1)


@pytest.mark.parametrize("by", ["Claude", "claude-opus-5-5", "the judge", "a subagent", "Sonnet 5.5", ""])
def test_an_answer_signed_by_a_model_is_refused(by):
    with pytest.raises(GateRefused):
        Answer(words="yes", by=by, provenance="person", at=T1)


def test_empty_words_or_bad_scope_or_time_are_refused():
    with pytest.raises(GateRefused):
        Answer(words="   ", by="Test Person", provenance="person", at=T1)
    with pytest.raises(GateRefused):
        Answer(words="yes", by="Test Person", provenance="person", at=T1, scope="always")
    with pytest.raises(GateRefused):
        Answer(words="yes", by="Test Person", provenance="person", at="yesterday")


def test_words_are_kept_exactly():
    words = "do rounds of fixing unting reviewer is satisfied,\n  then use me as a human gate "
    assert person(words).words == words


def test_gates_cannot_be_asked_out_of_order():
    with pytest.raises(GateRefused, match="concept"):
        GateBook.empty().ask("song", ["audio/mix.wav"], at=T0)


def test_require_refuses_until_every_gate_up_to_it_has_passed():
    book = through(GateBook.empty(), "looks")
    book.require("looks")
    with pytest.raises(GateRefused, match="board"):
        book.require("spend")


def test_a_no_keeps_the_gate_open_and_needs_a_new_showing():
    book = GateBook.empty().ask("concept", ["three pitches"], at=T0)
    book = book.answer("concept", person("none of these", approves=False))
    assert not book.passed("concept")
    assert book.record("concept").state == "waiting"
    with pytest.raises(GateRefused):
        book.answer("concept", person("Drawer woman I like it"))
    book = book.ask("concept", ["three new pitches"], at=T2).answer("concept", person(at=T2))
    assert book.passed("concept")
    assert [a.approves for a in book.record("concept").answers] == [False, True]


def test_one_question_at_a_time():
    with pytest.raises(GateRefused, match="one question"):
        GateBook.empty().ask("concept", ["x"], at=T0, question="Which pitch? And which style?")
    with pytest.raises(GateRefused, match="shown"):
        GateBook.empty().ask("concept", [], at=T0)
    book = GateBook.empty().ask("concept", ["x"], at=T0)
    with pytest.raises(GateRefused, match="waiting"):
        book.ask("concept", ["y"], at=T1)


def test_a_passed_gate_is_not_asked_again_unless_reopened():
    book = through(GateBook.empty(), "board")
    with pytest.raises(GateRefused, match="passed"):
        book.ask("looks", ["new sheet"], at=T2)
    book = book.reopen("looks", "the person wants to change her image a bit", at=T2)
    assert book.next_gate().id == "looks"
    with pytest.raises(GateRefused):
        book.require("board")
    assert book.record("looks").reopened[0][1].startswith("the person")
    book = book.ask("looks", ["new sheet"], at=T2)
    assert book.record("looks").state == "asked"


def test_reopen_needs_a_reason_and_a_passed_gate():
    with pytest.raises(GateRefused):
        GateBook.empty().reopen("concept", "why", at=T0)
    book = through(GateBook.empty(), "concept")
    with pytest.raises(GateRefused):
        book.reopen("concept", " ", at=T0)


def test_standing_rule_scope_is_kept():
    book = GateBook.empty().ask("concept", ["x"], at=T0)
    book = book.answer("concept", person("no grain in masters", scope="standing"))
    assert book.record("concept").latest.scope == "standing"


def test_round_trip_through_a_dict():
    book = through(GateBook.empty(), "song")
    book = book.reviewed("cuts/v01.mp4", "reviewer-a", ["S04 freezes"], at=T1)
    again = GateBook.from_dict(book.to_dict())
    assert again == book


def test_a_stored_model_answer_refuses_to_load():
    data = through(GateBook.empty(), "concept").to_dict()
    data["gates"][0]["answers"][0]["provenance"] = "model"
    with pytest.raises(GateRefused):
        GateBook.from_dict(data)


def test_a_stored_pass_without_a_passing_answer_refuses_to_load():
    data = GateBook.empty().to_dict()
    data["gates"][0]["state"] = "passed"
    with pytest.raises(GateRefused):
        GateBook.from_dict(data)
