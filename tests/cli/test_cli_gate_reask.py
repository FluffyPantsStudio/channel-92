"""`gate FILM ask GATE --again`: a gate asked with the wrong thing shown is asked again from the command line, the
earlier ask kept in standing.json, and `progress` names what is asked now."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atomic_flix.cli import main
from atomic_flix.gates import Answer, GateRefused
from atomic_flix.project import FilmFolder, answer_gate, ask_gate, load_standing

AT = "2026-11-20T10:00:00+00:00"
LATER = "2026-11-20T10:30:00+00:00"


@pytest.fixture
def film(tmp_path: Path) -> Path:
    mix = tmp_path / "mix.wav"
    mix.write_bytes(b"RIFF fake")
    folder = tmp_path / "films" / "sunny"
    assert main(["new", str(folder), "--song", str(mix), "--aspect", "16:9", "--by", "Test Person",
                 "--words", "wide"]) == 0
    assert main(["gate", str(folder), "ask", "concept", "--shown", "pitches.md", "--question",
                 "Which pitch is the film?", "--at", AT]) == 0
    return folder


def _standing(film: Path) -> dict:
    return json.loads((film / "standing.json").read_text(encoding="utf-8"))


def test_again_replaces_what_is_shown_and_asked_and_progress_shows_it(film, capsys):
    assert main(["gate", str(film), "ask", "concept", "--again", "--shown", "plot.md", "--question",
                 "Is this the film?", "--at", LATER]) == 0
    record = load_standing(FilmFolder(film)).gates.record("concept")
    assert (record.shown, record.question, record.asked_at) == (("plot.md",), "Is this the film?", LATER)
    assert record.superseded[0].shown == ("pitches.md",)
    stored = _standing(film)["gates"]["gates"][0]["superseded"]
    assert stored == [{"shown": ["pitches.md"], "question": "Which pitch is the film?", "asked_at": AT,
                       "replaced_at": LATER}]
    capsys.readouterr()
    main(["progress", str(film)])
    out = capsys.readouterr().out
    assert "Shows: plot.md" in out and "Asks: \"Is this the film?\"" in out
    assert "Which pitch" in out             # the earlier ask is named as superseded, not hidden


def test_plain_ask_on_an_open_gate_is_refused_and_names_again(film, capsys):
    assert main(["gate", str(film), "ask", "concept", "--shown", "plot.md"]) == 2
    assert "--again" in capsys.readouterr().err


def test_again_after_an_answer_is_refused_with_a_plain_sentence(film, capsys):
    answer_gate(FilmFolder(film), "concept", Answer(words="yes", by="Test Person", provenance="person", at=LATER))
    assert main(["gate", str(film), "ask", "concept", "--again", "--shown", "plot.md"]) == 2
    err = capsys.readouterr().err
    assert "reopen" in err
    assert load_standing(FilmFolder(film)).gates.record("concept").superseded == ()


def test_again_on_a_gate_never_asked_is_refused(film, capsys):
    answer_gate(FilmFolder(film), "concept", Answer(words="yes", by="Test Person", provenance="person", at=LATER))
    assert main(["gate", str(film), "ask", "song", "--again", "--shown", "audio/mix.wav"]) == 2
    assert "never been asked" in capsys.readouterr().err


def test_again_keeps_the_eval_hold_on_gates_five_and_six(film, monkeypatch):
    for gate in ("concept", "song", "looks", "board"):
        if gate != "concept":
            ask_gate(film, gate, ["shown"], at=AT)
        answer_gate(film, gate, Answer(words="yes", by="Test Person", provenance="person", at=LATER))
    monkeypatch.setattr("atomic_flix.project.actions.require_eval", lambda *args, **kwargs: None)
    ask_gate(film, "spend", ["plan/report.md"], at=LATER)

    def held(*args, **kwargs):
        raise GateRefused("held by the eval")

    monkeypatch.setattr("atomic_flix.project.actions.require_eval", held)
    with pytest.raises(GateRefused, match="held"):
        ask_gate(film, "spend", ["plan/budget.json"], at=LATER, again=True)
    assert load_standing(FilmFolder(film)).gates.record("spend").shown == ("plan/report.md",)
