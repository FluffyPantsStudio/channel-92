"""The desk's guards: what counts as a yes, number lists, hostile characters, the echo guard, a take that fails
whole, reply files and stdin, --at ordering, --out confinement, the stale final and the protocol whitelist."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from atomic_flix.cli import main
from atomic_flix.desk import DeskError, build_packet, desk_line, parse_reply, take_reply
from atomic_flix.project import FilmFolder, ask_gate, load_standing, reopen_gate
from deskfilm import AT, PERSON, SHOWN, ask_up_to
from ffmpeg_calls import assert_whitelisted, ffmpeg_calls

pytestmark = pytest.mark.usefixtures("no_eval_hook")
LATER = "2026-11-20T11:00:00+00:00"


@pytest.fixture
def film(desk_film) -> Path:
    ask_up_to(desk_film, "looks")
    return desk_film


def _record(film: Path, gate: str = "looks"):
    return load_standing(FilmFolder(film)).gates.record(gate)


def _files(film: Path) -> dict[str, bytes | None]:
    names = ("standing.json", "notes.md", "review/director.json", "review/fixlist.md")
    return {name: (film / name).read_bytes() if (film / name).is_file() else None for name in names}


# What counts as a yes ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["ok?", "yes?", "good?", "y?!", "Yes?.", "approve?", "y", "Y.", "yes,", ":yes",
                                  "looks good?"])
def test_a_question_mark_or_a_bare_y_is_never_a_yes(text):
    assert parse_reply(text).kind == "redact"


@pytest.mark.parametrize("text", ["yes", " Yes! ", "OK.", "approved!!", "looks good.", "Looks  good"])
def test_a_yes_may_end_in_a_full_stop_or_an_exclamation_mark(text):
    assert parse_reply(text).kind == "yes"


# Number lists ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, marks", [
    ("fix 2, 3 and 5: hand", [(2, "hand"), (3, "hand"), (5, "hand")]),
    ("2 3 5: too dark", [(2, "too dark"), (3, "too dark"), (5, "too dark")]),
    ("fix 2-4: collar; 7 dark", [(2, "collar"), (3, "collar"), (4, "collar"), (7, "dark")]),
    ("fix 3: hand, 7: too dark", [(3, "hand"), (7, "too dark")]),
    ("the sky is dull, 7: too red", [(None, "the sky is dull"), (7, "too red")]),
])
def test_number_lists_and_ranges_become_one_mark_per_item(text, marks):
    assert [(mark.item, mark.note) for mark in parse_reply(text).marks] == marks


def test_a_range_past_the_limit_is_kept_as_one_mark_with_no_item():
    reply = parse_reply("fix 1-900: everything")
    assert [(mark.item, mark.note) for mark in reply.marks] == [(None, "fix 1-900: everything")]


def test_too_many_marks_are_refused():
    with pytest.raises(DeskError, match="marks"):
        parse_reply("; ".join(f"{n} bad" for n in range(1, 200)))


# Hostile characters ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["fix 3\x1b[2J: hand", "ok\x00", "fix 3: hand\u202egnp.", "fix\u2028 3: hand",
                                  "fix 3: hand\x85"])
def test_control_bidi_and_line_separator_characters_are_refused(text):
    with pytest.raises(DeskError, match="character"):
        parse_reply(text)


def test_carriage_returns_become_new_lines_and_tabs_stay():
    reply = parse_reply("fix 3: hand\r\n5) mouth\rsmiles\tlate")
    assert reply.words == "fix 3: hand\n5) mouth\nsmiles\tlate"
    assert [mark.item for mark in reply.marks] == [3, 5, None]


def test_a_reply_over_four_kilobytes_is_refused():
    with pytest.raises(DeskError, match="4 KB"):
        parse_reply("fix 3: " + "a" * 5000)


@pytest.mark.parametrize("by", ["Ana\x1b[31m", "Ana; rm", "Ana<b>", "Ana\u202e", "12345"])
def test_by_is_letters_spaces_and_name_marks_only(film, by):
    before = _files(film)
    with pytest.raises(DeskError):
        take_reply(film, "looks", "yes", by)
    assert _files(film) == before


def test_a_name_with_name_marks_is_taken(film):
    take_reply(film, "looks", "yes", "Ana-Maria O'Neil Jr.")
    assert _record(film).state == "passed"


@pytest.mark.parametrize("at", ["2026-11-20T10:30:00\x1b", "not a time", "2026-11-20T10:30:00\u202e"])
def test_a_bad_at_is_refused_even_for_a_question(film, at):
    before = _files(film)
    with pytest.raises(DeskError):
        take_reply(film, "looks", "question: why?", PERSON, at=at)
    assert _files(film) == before


def test_quotes_in_the_notes_keep_every_line_after_a_carriage_return(film):
    take_reply(film, "looks", "question: first\rsecond", PERSON)
    notes = (film / "notes.md").read_text(encoding="utf-8")
    assert "> question: first\n> second\n" in notes and "\r" not in notes


def test_control_characters_in_a_hand_edited_ledger_are_not_printed(film, capsys):
    take_reply(film, "looks", "fix 3: hand", PERSON)
    path = film / "review" / "director.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["marks"][0]["note"] = "hand\x1b[2J\u202e"
    path.write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()
    main(["progress", str(film)])
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\u202e" not in out and "hand" in out


# The echo guard ----------------------------------------------------------------------------------------------

def test_the_packets_card_lines_captions_and_question_are_refused_even_inside_a_reply(film):
    packet = build_packet(film, "looks")
    caption = packet.files[0].caption
    card_line = next(line for line in packet.card.splitlines() if line.startswith("Reply in one message"))
    question = _record(film).question
    before = _files(film)
    for text in (caption, f"ok {caption} ok", card_line, f"yes. {card_line}", question, f"{question} yes"):
        with pytest.raises(DeskError, match="packet's own text"):
            take_reply(film, "looks", text, PERSON)
    assert _files(film) == before


def test_an_unreadable_manifest_stops_the_desk(film):
    build_packet(film, "looks")
    (film / "desk" / "looks" / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(DeskError, match="manifest"):
        take_reply(film, "looks", "yes", PERSON)
    assert _record(film).state == "asked"


# A take fails whole ------------------------------------------------------------------------------------------

def test_a_corrupt_director_json_refuses_before_anything_is_written(film):
    (film / "review").mkdir(exist_ok=True)
    (film / "review" / "director.json").write_text("{broken", encoding="utf-8")
    before = _files(film)
    assert main(["desk", str(film), "looks", "--reply", "fix 3: hand", "--by", PERSON]) == 2
    assert _files(film) == before
    assert _record(film).state == "asked"


def test_a_gate_answer_that_fails_rolls_the_reply_back(film, monkeypatch):
    def refuse(*args, **kwargs):
        from atomic_flix.project import ProjectError
        raise ProjectError("the eval says no")
    monkeypatch.setattr("atomic_flix.desk.take.answer_gate", refuse)
    before = _files(film)
    with pytest.raises(DeskError, match="the eval says no"):
        take_reply(film, "looks", "fix 3: hand", PERSON)
    assert _files(film) == before


# Reply files and stdin ---------------------------------------------------------------------------------------

AWKWARD = "fix 3: costs $5, `rm -rf` and \"quotes\" 'too'\n$(whoami) ${HOME}"


def test_a_reply_file_arrives_unchanged(film, tmp_path):
    reply = tmp_path / "reply.txt"
    reply.write_text(AWKWARD + "\n", encoding="utf-8")         # a heredoc ends in one new line
    assert main(["desk", str(film), "looks", "--reply-file", str(reply), "--by", PERSON]) == 0
    assert _record(film).latest.words == AWKWARD


def test_a_reply_on_stdin_arrives_unchanged(film, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO((AWKWARD + "\n").encode("utf-8")),
                                                       encoding="utf-8"))
    assert main(["desk", str(film), "looks", "--reply", "-", "--by", PERSON]) == 0
    assert _record(film).latest.words == AWKWARD


def _posix_shell() -> str | None:
    """sh on the PATH, else the one Git for Windows ships beside git."""
    found = shutil.which("sh")
    git = shutil.which("git")
    beside_git = Path(git).resolve().parent.parent / "bin" / "sh.exe" if git else None
    return found or (str(beside_git) if beside_git and beside_git.is_file() else None)


SHELL = _posix_shell()


@pytest.mark.skipif(SHELL is None, reason="needs a POSIX shell for the heredoc")
def test_the_gate_sessions_heredoc_passes_dollars_and_backticks_through(film):
    shell = str(SHELL)
    script = (f'"{sys.executable}" -m atomic_flix.cli desk "{film.as_posix()}" looks --by "{PERSON}" --reply - '
              f"<<'CHANNEL92_REPLY_END'\n{AWKWARD}\nCHANNEL92_REPLY_END\n")
    done = subprocess.run([shell, "-c", script], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    assert _record(film).latest.words == AWKWARD


def test_reply_and_reply_file_together_are_refused(film, tmp_path):
    reply = tmp_path / "reply.txt"
    reply.write_text("yes", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["desk", str(film), "looks", "--reply", "yes", "--reply-file", str(reply), "--by", PERSON])


# --at ordering -----------------------------------------------------------------------------------------------

def test_an_at_before_the_question_is_refused(film):
    with pytest.raises(DeskError, match="before"):
        take_reply(film, "looks", "question: when?", PERSON, at="2026-11-20T09:00:00+00:00")


def test_an_at_before_the_gates_last_answer_is_refused(film):
    take_reply(film, "looks", "fix 3: hand", PERSON, at=LATER)
    ask_gate(film, "looks", SHOWN["looks"], at=AT)
    with pytest.raises(DeskError, match="before"):
        take_reply(film, "looks", "yes", PERSON, at="2026-11-20T10:30:00+00:00")


def test_a_mark_closes_only_on_a_yes_that_comes_after_it(film):
    take_reply(film, "looks", "yes", PERSON, at=AT)
    reopen_gate(film, "looks", "the director changed her mind", at=AT)
    ask_gate(film, "looks", SHOWN["looks"], at=AT)
    take_reply(film, "looks", "fix 3: hand", PERSON, at=AT)        # same second as the earlier yes
    assert desk_line(film).endswith("; 1 open mark")
    ask_gate(film, "looks", SHOWN["looks"], at=AT)
    take_reply(film, "looks", "yes", PERSON, at=AT)
    assert desk_line(film).endswith("; 0 open marks")


# --out confinement and clean-up ------------------------------------------------------------------------------

@pytest.mark.parametrize("out", ["plan", ".", "desk", "../elsewhere", "stills/x"])
def test_out_may_only_be_a_folder_under_the_desk_folder(film, out):
    with pytest.raises(DeskError, match="desk"):
        build_packet(film, "looks", out=out)


def test_out_under_the_desk_folder_is_taken_and_no_work_folder_is_left(film):
    packet = build_packet(film, "looks", out="desk/phone-a")
    assert packet.folder == (film / "desk" / "phone-a").resolve()
    assert not [p for p in packet.folder.iterdir() if p.name.startswith(".work")]


def test_a_work_folder_that_was_there_before_is_left_alone(film):
    mine = film / "desk" / "looks" / ".work"
    mine.mkdir(parents=True)
    (mine / "keep.txt").write_text("mine", encoding="utf-8")
    build_packet(film, "looks")
    assert (mine / "keep.txt").read_text(encoding="utf-8") == "mine"


def test_a_packet_that_fails_any_way_leaves_nothing_behind(film, monkeypatch):
    from atomic_flix.desk import builders

    def broken(ctx, sink):
        sink.picture("first", builders.placeholder(64, 36, "X"), "a picture", "pictures")
        raise RuntimeError("the disk is full")
    monkeypatch.setitem(builders.BUILDERS, "looks", broken)
    with pytest.raises(RuntimeError):
        build_packet(film, "looks")
    folder = film / "desk" / "looks"
    assert not folder.exists() or list(folder.iterdir()) == []


def test_the_cleaner_only_removes_packet_files(film):
    folder = film / "desk" / "looks"
    folder.mkdir(parents=True)
    (folder / "mine.txt").write_text("mine", encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps({"files": [{"file": "mine.txt"}, {"file": "../../film.json"}]}),
                                          encoding="utf-8")
    build_packet(film, "looks")
    assert (folder / "mine.txt").is_file() and (film / "film.json").is_file()


# Gate 6: symlinked sheets and a stale final ------------------------------------------------------------------

@pytest.fixture
def v1_film(desk_film) -> Path:
    return desk_film


def test_a_stale_final_is_skipped_and_the_card_says_so(v1_film):
    film = v1_film
    final = film / "cuts" / "v01-final.mp4"
    final.write_bytes((film / "cuts" / "v01.mp4").read_bytes())
    toned = film / "cuts" / "v01-toned.mp4"
    toned.write_bytes((film / "cuts" / "v01.mp4").read_bytes())
    os.utime(final, (1_000_000_000, 1_000_000_000))                  # finished before the re-grade
    ask_up_to(film, "v1")
    packet = build_packet(film, "v1")
    assert "v01-toned.mp4" in packet.files[0].caption
    assert "v01-final.mp4" in packet.card and "older" in packet.card


def test_review_sheets_that_are_links_or_lead_outside_are_skipped(v1_film, tmp_path):
    film = v1_film
    outside = tmp_path / "secret.jpg"
    outside.write_bytes((film / "review" / "v01" / "01-S01-strip.jpg").read_bytes())
    link = film / "review" / "v01" / "03-link.jpg"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("this machine cannot make symbolic links")
    ask_up_to(film, "v1")
    packet = build_packet(film, "v1")
    assert len([item for item in packet.files if item.kind == "image"]) == 2
    assert any("03-link.jpg" in note for note in packet.notes)


# The protocol whitelist --------------------------------------------------------------------------------------

@pytest.mark.parametrize("gate", ["song", "looks", "board", "v1"])
def test_every_ffmpeg_call_of_a_packet_whitelists_its_inputs(desk_film, monkeypatch, gate):
    (desk_film / "cuts" / "v01-final.mp4").write_bytes((desk_film / "cuts" / "v01.mp4").read_bytes())
    ask_up_to(desk_film, gate)
    calls = ffmpeg_calls(monkeypatch)
    build_packet(desk_film, gate)
    assert_whitelisted(calls)
