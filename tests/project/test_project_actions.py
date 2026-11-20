"""Gate answers written word for word into the notes, the song's fingerprint, review rounds, the record."""

import pytest

from atomic_flix.gates import Answer, GateRefused
from atomic_flix.project import (
    ProjectError,
    answer_gate,
    ask_gate,
    create_project,
    load_standing,
    reopen_gate,
    require_gate,
    review_cut,
    set_record,
    validate,
    where_it_stands,
)

CREATED = "2026-11-20T09:00:00+00:00"
AT = "2026-11-20T12:00:00+00:00"


def said(words, approves=True, scope="film", at=AT):
    return Answer(words=words, by="Test Person", provenance="person", at=at, scope=scope, approves=approves)


@pytest.fixture
def film(tmp_path):
    return create_project(tmp_path, "glass-harbour", "Glass Harbour", created=CREATED)


def write_mix(film, payload=b"RIFF fake mix"):
    path = film.root / "audio" / "mix.wav"
    path.write_bytes(payload)
    return path


def test_the_answer_goes_into_the_notes_word_for_word(film):
    ask_gate(film, "concept", ["pitches.md"], at=AT, question="Which surreal pitch is the film?")
    words = "Drawer woman I like it\nbut less literal plumbing, ok?  "
    standing = answer_gate(film, "concept", said(words))
    notes = film.notes.read_text(encoding="utf-8")
    assert "> Drawer woman I like it\n> but less literal plumbing, ok?  \n" in notes
    assert "Which surreal pitch is the film?" in notes
    assert "pitches.md" in notes
    assert "Test Person" in notes
    assert "this film only" in notes
    assert standing.gates.passed("concept")
    assert load_standing(film).gates.passed("concept")


def test_a_standing_rule_is_marked_in_the_notes(film):
    ask_gate(film, "concept", ["pitches.md"], at=AT)
    answer_gate(film, "concept", said("Don't add any grain into masters", scope="standing"))
    assert "standing rule" in film.notes.read_text(encoding="utf-8")


def test_unicode_words_survive(film):
    ask_gate(film, "concept", ["pitches.md"], at=AT)
    words = "Ça va, давай \u2014 go"     # the person's words may hold any letter
    answer_gate(film, "concept", said(words))
    assert f"> {words}" in film.notes.read_text(encoding="utf-8")


def test_a_refused_answer_writes_nothing(film):
    before = film.notes.read_text(encoding="utf-8")
    with pytest.raises(GateRefused):
        answer_gate(film, "concept", said("yes"))
    assert film.notes.read_text(encoding="utf-8") == before
    assert not load_standing(film).gates.passed("concept")


def test_the_song_gate_fingerprints_the_mix(film):
    ask_gate(film, "concept", ["p"], at=AT)
    answer_gate(film, "concept", said("yes"))
    ask_gate(film, "song", ["audio/mix.wav"], at=AT)
    with pytest.raises(ProjectError, match="mix"):
        answer_gate(film, "song", said("Sounds right"))
    write_mix(film)
    standing = answer_gate(film, "song", said("Sounds right"))
    assert standing.song.file == "audio/mix.wav"
    assert len(standing.song.sha256) == 64
    assert standing.song.size == len(b"RIFF fake mix")


def test_require_gate_refuses_before_the_answer(film):
    with pytest.raises(GateRefused):
        require_gate(film, "spend")
    ask_gate(film, "concept", ["p"], at=AT)
    answer_gate(film, "concept", said("yes"))
    require_gate(film, "concept")


def test_review_rounds_are_kept_in_the_state_file(film):
    review_cut(film, "cuts/v01.mp4", "reviewer-1", ["S04 freezes"], at=AT)
    review_cut(film, "cuts/v02.mp4", "reviewer-2", [], at=AT)
    loop = load_standing(film).gates.review
    assert loop.reviewers == ("reviewer-1", "reviewer-2")
    assert loop.is_clean
    assert "2 review rounds" in where_it_stands(film)
    with pytest.raises(GateRefused):
        review_cut(film, "cuts/v03.mp4", "reviewer-1", [], at=AT)


def test_reopen_is_noted(film):
    ask_gate(film, "concept", ["p"], at=AT)
    answer_gate(film, "concept", said("yes"))
    reopen_gate(film, "concept", "the person asked for new pitches", at=AT)
    assert load_standing(film).gates.next_gate().id == "concept"
    assert "the person asked for new pitches" in film.notes.read_text(encoding="utf-8")


def test_record_values_are_typed_and_kept(film):
    set_record(film, finished_seconds=241.5, calls=900, cost_usd=120.0, median_tokens=98000, reshoot_passes=1)
    record = load_standing(film).record
    assert record["finished_seconds"] == 241.5
    assert record["calls"] == 900
    with pytest.raises(ProjectError):
        set_record(film, calls="many")
    with pytest.raises(ProjectError):
        set_record(film, mood=3)
    with pytest.raises(ProjectError):
        set_record(film, cost_usd=-1)


def test_answers_stay_valid_until_the_notes_lose_them(film):
    ask_gate(film, "concept", ["p"], at=AT)
    answer_gate(film, "concept", said("Drawer woman I like it"))
    def notes_errors():
        return [f for f in validate(film) if f.level == "error" and f.path == "notes.md"]

    assert not notes_errors()
    text = film.notes.read_text(encoding="utf-8").replace("Drawer woman I like it", "Drawer woman")
    film.notes.write_text(text, encoding="utf-8")
    assert notes_errors() and "word for word" in notes_errors()[0].message
