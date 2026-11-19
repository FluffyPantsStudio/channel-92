"""The validator: missing files by the gate that needs them, stale derived files, a changed song."""

import json
import os
import shutil

import pytest

from atomic_flix.gates import Answer
from atomic_flix.project import answer_gate, ask_gate, create_project, validate

CREATED = "2026-11-20T09:00:00+00:00"
AT = "2026-11-20T12:00:00+00:00"
OLD, MID, NEW = 1_700_000_000, 1_700_000_500, 1_700_001_000


def said(words="yes"):
    return Answer(words=words, by="Test Person", provenance="person", at=AT)


@pytest.fixture
def film(tmp_path):
    return create_project(tmp_path, "atomic-sunshine", "Atomic Sunshine", created=CREATED)


def touch(path, when, payload=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    os.utime(path, (when, when))
    return path


def edit_film(film, **changes):
    data = json.loads(film.film.read_text(encoding="utf-8"))
    data.update(changes)
    film.film.write_text(json.dumps(data), encoding="utf-8")


def found(findings, level, fragment):
    return [f for f in findings if f.level == level and fragment in f.path]


def test_a_fresh_project_has_no_errors_only_things_to_do(film):
    findings = validate(film)
    assert not [f for f in findings if f.level == "error"]
    assert found(findings, "todo", "audio/mix.wav")
    assert found(findings, "todo", "audio/voice.wav")


def test_a_missing_folder_or_core_file_is_an_error(film):
    shutil.rmtree(film.root / "stills")
    film.lyric.unlink()
    findings = validate(film)
    assert found(findings, "error", "stills")
    assert found(findings, "error", "lyric.txt")


def test_a_missing_mix_is_an_error_once_the_song_gate_is_next(film):
    ask_gate(film, "concept", ["p"], at=AT)
    answer_gate(film, "concept", said())
    findings = validate(film)
    assert found(findings, "error", "audio/mix.wav")
    assert found(findings, "todo", "audio/voice.wav")


def test_broken_film_file_is_an_error(film):
    film.film.write_text("{not json", encoding="utf-8")
    assert found(validate(film), "error", "film.json")


def test_a_plan_older_than_the_stems_is_stale(film):
    os.utime(film.lyric, (OLD - 100, OLD - 100))
    touch(film.root / "audio" / "voice.wav", NEW)
    touch(film.root / "analysis" / "voice-lines.json", NEW + 10)
    touch(film.root / "plan" / "cuts.json", OLD)
    findings = validate(film)
    stale = found(findings, "stale", "plan/cuts.json")
    assert stale and "audio/voice.wav" in stale[0].message
    assert not found(findings, "stale", "analysis/voice-lines.json")


def test_analysis_older_than_the_lyric_is_stale(film):
    touch(film.root / "analysis" / "voice-lines.json", OLD)
    os.utime(film.lyric, (NEW, NEW))
    assert found(validate(film), "stale", "analysis/voice-lines.json")


def test_a_chosen_render_older_than_its_still_is_stale(film):
    touch(film.root / "stills" / "S02.png", NEW)
    touch(film.root / "renders" / "S02" / "r007.mp4", OLD)
    edit_film(film, lineup=[{"key": "S02", "type": "vocal", "still": "stills/S02.png"}], picks={"S02": 7})
    assert found(validate(film), "stale", "renders/S02/r007.mp4")


def test_a_chosen_render_that_is_missing_is_an_error(film):
    edit_film(film, picks={"S02": 3})
    assert found(validate(film), "error", "renders/S02/r003.mp4")


def test_the_newest_cut_older_than_a_chosen_render_is_stale(film):
    touch(film.root / "stills" / "S02.png", OLD)
    touch(film.root / "renders" / "S02" / "r007.mp4", NEW)
    touch(film.root / "cuts" / "v01.mp4", OLD)
    touch(film.root / "cuts" / "v02.mp4", MID)
    edit_film(film, lineup=[{"key": "S02", "type": "vocal", "still": "stills/S02.png"}], picks={"S02": 7})
    findings = validate(film)
    assert found(findings, "stale", "cuts/v02.mp4")
    assert not found(findings, "stale", "cuts/v01.mp4")


def test_a_still_missing_from_the_shotlist_is_needed_by_the_board(film):
    edit_film(film, lineup=[{"key": "N08", "type": "cutaway", "still": "stills/N08.png"}])
    assert found(validate(film), "todo", "stills/N08.png")


def test_a_mix_changed_after_the_song_gate_is_an_error(film):
    ask_gate(film, "concept", ["p"], at=AT)
    answer_gate(film, "concept", said())
    (film.root / "audio" / "mix.wav").write_bytes(b"the approved mix")
    ask_gate(film, "song", ["audio/mix.wav"], at=AT)
    answer_gate(film, "song", said("Sounds right"))
    assert not found(validate(film), "error", "audio/mix.wav")
    (film.root / "audio" / "mix.wav").write_bytes(b"a wrong version")
    errors = found(validate(film), "error", "audio/mix.wav")
    assert errors and "approved" in errors[0].message


def test_a_bad_ledger_line_is_an_error(film):
    film.job_log.write_text('{"job_id": "r1"}\n', encoding="utf-8")
    errors = found(validate(film), "error", "job-log.jsonl")
    assert errors and "line 1" in errors[0].message
