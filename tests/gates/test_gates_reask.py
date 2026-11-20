"""`ask --again`: an open gate asked with the wrong thing shown is asked again; the earlier ask stays on record."""

import pytest

from atomic_flix.gates import Answer, GateBook, GateRecord, GateRefused, gate_spec

T0 = "2026-11-20T10:00:00+00:00"
T1 = "2026-11-20T10:30:00+00:00"
T2 = "2026-11-20T11:00:00+00:00"


def person(words="yes", approves=True, at=T2):
    return Answer(words=words, by="Test Person", provenance="person", at=at, approves=approves)


def asked_with_pitches():
    return GateBook.empty().ask("concept", ["pitches.md"], at=T0, question="Which pitch is the film?")


def test_asking_again_replaces_shown_question_and_time_and_keeps_the_earlier_ask():
    book = asked_with_pitches().ask("concept", ["plot.md"], at=T1, question="Is this the film?", again=True)
    record = book.record("concept")
    assert record.state == "asked"
    assert (record.shown, record.question, record.asked_at) == (("plot.md",), "Is this the film?", T1)
    assert len(record.superseded) == 1
    earlier = record.superseded[0]
    assert (earlier.shown, earlier.question, earlier.asked_at, earlier.replaced_at) == (
        ("pitches.md",), "Which pitch is the film?", T0, T1)


def test_asking_again_keeps_what_is_not_given():
    book = asked_with_pitches().ask("concept", [], at=T1, question="Is this the film?", again=True)
    assert book.record("concept").shown == ("pitches.md",)
    book = asked_with_pitches().ask("concept", ["plot.md"], at=T1, again=True)
    assert book.record("concept").question == "Which pitch is the film?"


def test_the_earlier_ask_survives_a_save_and_a_load():
    book = asked_with_pitches().ask("concept", ["plot.md"], at=T1, question="Is this the film?", again=True)
    loaded = GateBook.from_dict(book.to_dict()).record("concept")
    assert loaded == book.record("concept")
    assert loaded.superseded[0].shown == ("pitches.md",)


def test_a_stored_record_without_earlier_asks_still_loads():
    data = GateRecord("concept").to_dict()
    data.pop("superseded")
    assert GateRecord.from_dict(data).superseded == ()


def test_asking_again_is_refused_after_a_yes():
    book = asked_with_pitches().answer("concept", person())
    with pytest.raises(GateRefused, match="reopen"):
        book.ask("concept", ["plot.md"], at=T2, again=True)


def test_asking_again_is_refused_after_a_no():
    book = asked_with_pitches().answer("concept", person("not this", approves=False))
    with pytest.raises(GateRefused, match="answered"):
        book.ask("concept", ["plot.md"], at=T2, again=True)


def test_asking_again_is_refused_when_never_asked():
    with pytest.raises(GateRefused, match="never been asked"):
        GateBook.empty().ask("concept", ["plot.md"], at=T1, again=True)


def test_asking_again_after_reopening_is_refused_and_plain_ask_works():
    book = asked_with_pitches().answer("concept", person()).reopen("concept", "changed my mind", at=T2)
    with pytest.raises(GateRefused):
        book.ask("concept", ["plot.md"], at=T2, again=True)
    assert book.ask("concept", ["plot.md"], at=T2).record("concept").state == "asked"


def test_asking_again_may_not_be_dated_before_the_earlier_ask():
    with pytest.raises(GateRefused, match="before"):
        asked_with_pitches().ask("concept", ["plot.md"], at="2026-11-20T09:00:00+00:00", again=True)


def test_an_answer_dated_before_the_new_ask_is_refused():
    book = asked_with_pitches().ask("concept", ["plot.md"], at=T2, question="Is this the film?", again=True)
    with pytest.raises(GateRefused, match="before the question"):
        book.answer("concept", person(at=T1))
    assert book.answer("concept", person(at="2026-11-20T11:30:00+00:00")).passed("concept")


def test_asking_again_still_takes_one_question():
    with pytest.raises(GateRefused, match="one question"):
        asked_with_pitches().ask("concept", ["plot.md"], at=T1, question="Is it? Or not?", again=True)


def test_plain_ask_on_an_open_gate_still_points_at_again():
    with pytest.raises(GateRefused, match="--again"):
        asked_with_pitches().ask("concept", ["plot.md"], at=T1)


def test_the_gate_default_question_is_used_when_the_first_ask_had_none():
    book = GateBook.empty().ask("concept", ["pitches.md"], at=T0).ask("concept", ["plot.md"], at=T1, again=True)
    assert book.record("concept").question == gate_spec("concept").question
