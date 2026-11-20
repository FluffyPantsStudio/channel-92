"""`desk FILM GATE --reply TEXT --by NAME`: the director's typed reply from the phone, read and recorded."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from atomic_flix.cli import main
from atomic_flix.desk import DeskError, Mark, desk_line, parse_reply
from atomic_flix.project import FilmFolder, load_standing
from deskfilm import PERSON, ask_up_to

pytestmark = pytest.mark.usefixtures("no_eval_hook")


@pytest.mark.parametrize("text", ["yes", "Yes!", "  OK. ", "ok", "approve", "APPROVED.", "good",
                                  "Looks good!", "looks   good", "yes."])
def test_bare_yes_variants_pass(text):
    assert parse_reply(text).kind == "yes"


@pytest.mark.parametrize("text", ["yeah", "yes but fix 3", "accept", "looks good except 2", "sure", "no", "nope"])
def test_anything_else_is_a_redact(text):
    assert parse_reply(text).kind == "redact"


@pytest.mark.parametrize("text, marks", [
    ("fix 3: hand, 7: too dark", [(3, "hand"), (7, "too dark")]),
    ("3 hand wrong; 7 dark", [(3, "hand wrong"), (7, "dark")]),
    ("Fix #2: collar is open\n5) mouth smiles", [(2, "collar is open"), (5, "mouth smiles")]),
    ("the cut at 0:42 is too dark", [(None, "the cut at 0:42 is too dark")]),
    ("no", [(None, "no")]),
])
def test_item_marks_are_read_from_a_redact(text, marks):
    reply = parse_reply(text)
    assert reply.kind == "redact"
    assert [(mark.item, mark.note) for mark in reply.marks] == marks
    assert all(isinstance(mark, Mark) for mark in reply.marks)


def test_a_question_prefix_is_a_question_not_an_answer():
    reply = parse_reply("Question: is the tub too red?")
    assert reply.kind == "question" and reply.marks == ()


@pytest.mark.parametrize("text", ["", "   ", "!!!", "\n"])
def test_junk_is_refused(text):
    with pytest.raises(DeskError):
        parse_reply(text)


# Recording -----------------------------------------------------------------------------------------------------

@pytest.fixture
def film(desk_film) -> Path:
    ask_up_to(desk_film, "looks")
    return desk_film


def _desk(film: Path, gate: str, reply: str, by: str = PERSON) -> int:
    return main(["desk", str(film), gate, "--reply", reply, "--by", by])


def _director(film: Path) -> dict:
    return json.loads((film / "review" / "director.json").read_text(encoding="utf-8"))


def _record(film: Path, gate: str):
    return load_standing(FilmFolder(film)).gates.record(gate)


def test_a_yes_passes_the_gate_with_the_words_and_how_they_arrived(film):
    assert _desk(film, "looks", "Looks good!") == 0
    record = _record(film, "looks")
    assert record.state == "passed"
    assert (record.latest.words, record.latest.by, record.latest.provenance) == ("Looks good!", PERSON, "relayed")
    reply = _director(film)["replies"][-1]
    assert reply["outcome"] == "passed" and reply["via"] == "relayed in the Claude app"
    notes = (film / "notes.md").read_text(encoding="utf-8")
    assert "> Looks good!" in notes and "Claude app" in notes


def test_a_redact_answers_no_word_for_word_and_writes_the_fix_list(film):
    words = "fix 3: hand, 7: too dark"
    assert _desk(film, "looks", words) == 0
    record = _record(film, "looks")
    assert record.state == "waiting" and record.latest.approves is False and record.latest.words == words
    marks = _director(film)["marks"]
    assert [(m["gate"], m["item"], m["note"], m["reply"]) for m in marks] == [
        ("looks", 3, "hand", words), ("looks", 7, "too dark", words)]
    fixlist = (film / "review" / "fixlist.md").read_text(encoding="utf-8")
    assert "3: hand" in fixlist and "7: too dark" in fixlist


def test_a_question_goes_to_the_notes_and_leaves_the_gate_asked(film):
    assert _desk(film, "looks", "question: is that her old coat?") == 0
    assert _record(film, "looks").state == "asked"
    assert "question: is that her old coat?" in (film / "notes.md").read_text(encoding="utf-8")
    assert _director(film)["marks"] == []
    assert _director(film)["replies"][-1]["outcome"] == "question"


def test_director_json_is_append_only(film):
    assert _desk(film, "looks", "fix 3: hand") == 0
    first = _director(film)
    assert main(["gate", str(film), "ask", "looks", "--shown", "stills/S01.png"]) == 0
    assert _desk(film, "looks", "2 collar; 4 shoes") == 0
    second = _director(film)
    assert second["marks"][:len(first["marks"])] == first["marks"]
    assert second["replies"][:len(first["replies"])] == first["replies"]
    assert len(second["marks"]) == 3


def test_the_line_back_is_one_line_with_gate_outcome_words_and_open_marks(film, capsys):
    assert _desk(film, "looks", "fix 3: hand, 7: too dark") == 0
    capsys.readouterr()
    assert main(["desk", str(film), "--line"]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert re.fullmatch(r'gate 3 \(her face and looks\): redacted, "fix 3: hand, 7: too dark" '
                        r'\(Test Person, relayed in the Claude app\); 2 open marks\n', out), out
    assert desk_line(film) == out.strip()


def test_marks_close_when_the_gate_later_passes_and_progress_shows_them(film, capsys):
    assert _desk(film, "looks", "fix 3: hand") == 0
    capsys.readouterr()
    main(["progress", str(film)])
    assert "1 open director mark" in capsys.readouterr().out
    assert main(["gate", str(film), "ask", "looks", "--shown", "stills/S01.png"]) == 0
    assert _desk(film, "looks", "yes") == 0
    assert desk_line(film).endswith("; 0 open marks")


@pytest.mark.parametrize("args", [["colour", "--reply", "yes", "--by", PERSON],
                                  ["board", "--reply", "yes", "--by", PERSON],
                                  ["looks", "--reply", "yes", "--by", "Claude"],
                                  ["looks", "--reply", "   ", "--by", PERSON]])
def test_desk_refuses_an_unknown_gate_one_not_asked_a_machine_or_junk(film, args):
    before = (film / "standing.json").read_text(encoding="utf-8")
    assert main(["desk", str(film), *args]) == 2
    assert (film / "standing.json").read_text(encoding="utf-8") == before
    assert not (film / "review" / "director.json").exists()


def test_a_question_at_a_gate_not_asked_is_refused(film):
    assert _desk(film, "board", "question: which one is shot 4?") == 2
