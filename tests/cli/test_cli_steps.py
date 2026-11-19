"""The film verbs one at a time: what each refuses, and what `new --dry-run` reports."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from atomic_flix.cli import main
from atomic_flix.cli.common import Film, StepError
from atomic_flix.cli.cut_steps import pick
from atomic_flix.cli.shoot_steps import gate_facts
from atomic_flix.gates import Answer
from atomic_flix.project import answer_gate, ask_gate

LYRIC = "[Verse]\nThe sun comes up atomic\n(ooh ooh)\nAnd it shines on you\n"


def _new(tmp_path: Path, *extra: str) -> Path:
    lyric = tmp_path / "lyric.txt"
    lyric.write_text(LYRIC, encoding="utf-8")
    film = tmp_path / "films" / "sunny"
    assert main(["new", str(film), "--lyric", str(lyric), *extra]) == 0
    return film


def test_dry_run_reports_every_missing_input_and_writes_nothing(tmp_path, capsys):
    lyric = tmp_path / "lyric.txt"
    lyric.write_text(LYRIC, encoding="utf-8")
    aim = tmp_path / "films" / "atomic-sunshine"
    assert main(["new", str(aim), "--lyric", str(lyric), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert not aim.exists()
    assert "dry run" in out
    for missing in ("audio/mix.wav", "audio/voice.wav", "audio/band.wav", "audio/drums.wav", "shots.txt",
                    "singer.name"):
        assert missing in out, missing
    assert "3 sung lines (choir, lead)" in out


def test_new_copies_stems_and_names_them_in_film_json(tmp_path):
    mix = tmp_path / "mix.wav"
    mix.write_bytes(b"RIFF fake")
    film = _new(tmp_path, "--song", str(mix), "--star", "Frankie", "--who", "an android")
    data = json.loads((film / "film.json").read_text(encoding="utf-8"))
    assert data["stems"]["mix"] == "audio/mix.wav" and (film / "audio/mix.wav").read_bytes() == b"RIFF fake"
    assert data["star"] == {"name": "Frankie", "who": "an android"}
    assert (film / "lyric.txt").read_text(encoding="utf-8") == LYRIC


def test_new_refuses_a_missing_stem_file(tmp_path, capsys):
    assert main(["new", str(tmp_path / "x"), "--voice", str(tmp_path / "none.wav")]) == 2
    assert "--voice" in capsys.readouterr().err


def test_steps_refuse_a_folder_that_is_not_a_film(tmp_path, capsys):
    for verb in ("time", "bars", "plan", "lint", "budget", "place", "cut", "review", "progress"):
        assert main([verb, str(tmp_path)]) == 2, verb
    assert "not a film folder" in capsys.readouterr().err


def test_time_and_bars_say_which_stem_is_missing(tmp_path, capsys):
    film = _new(tmp_path)
    assert main(["time", str(film)]) == 2
    assert "voice stem" in capsys.readouterr().err
    assert main(["bars", str(film)]) == 2
    assert "drum, band or mix" in capsys.readouterr().err


def test_gate_five_cannot_be_asked_before_the_budget(tmp_path, capsys):
    film = _new(tmp_path)
    assert main(["gate", str(film), "ask", "spend"]) == 2
    assert "budget" in capsys.readouterr().err


def test_gates_are_asked_in_order_and_answers_need_a_person(tmp_path, capsys):
    film = _new(tmp_path)
    assert main(["gate", str(film), "ask", "looks", "--shown", "stills/S01.png"]) == 2
    assert "gate 1" in capsys.readouterr().err
    assert main(["gate", str(film), "ask", "concept", "--shown", "pitches.md"]) == 0
    assert main(["gate", str(film), "answer", "concept", "--by", "Claude", "--words", "yes"]) == 2
    assert "model or an agent" in capsys.readouterr().err
    assert main(["gate", str(film), "answer", "concept", "--by", "Test Person", "--words", "the second one"]) == 0
    assert "> the second one" in (film / "notes.md").read_text(encoding="utf-8")


def test_gate_facts_come_from_standing_and_film_json_wins(tmp_path):
    mix = tmp_path / "mix.wav"
    mix.write_bytes(b"RIFF fake")
    film_dir = _new(tmp_path, "--song", str(mix))
    at = "2026-11-20T10:00:00+00:00"
    for gate, words in (("concept", "one"), ("song", "yes, the one is right"), ("looks", "that is her")):
        ask_gate(film_dir, gate, ["shown"], at=at)
        answer_gate(film_dir, gate, Answer(words=words, by="Test Person", provenance="person", at=at))
    data = json.loads((film_dir / "film.json").read_text(encoding="utf-8"))
    data["gates"] = {"spend": {"budget_s": 3600.0}}
    (film_dir / "film.json").write_text(json.dumps(data), encoding="utf-8")
    facts = gate_facts(Film.open(film_dir))
    assert len(facts["song"]["sha256"]) == 64 and facts["bars"]["by_ear"] is True
    assert facts["look"]["words"] == "that is her"
    assert facts["spend"] == {"budget_s": 3600.0}


def test_pick_needs_the_person_when_a_shot_has_several_renders(tmp_path):
    film_dir = _new(tmp_path)
    for number in (1, 2):
        (film_dir / "renders/S01").mkdir(parents=True, exist_ok=True)
        (film_dir / f"renders/S01/r00{number}.mp4").write_bytes(b"x")
        (film_dir / f"renders/S01/r00{number}.fit.json").write_text("{}", encoding="utf-8")
    film = Film.open(film_dir)
    with pytest.raises(StepError, match="no pick"):
        pick(film, "S01")
    with pytest.raises(StepError, match="no placed render"):
        pick(film, "S02")
    data = {**film.data, "picks": {"S01": 2}}
    assert pick(film.save(data), "S01") == (2, "picks")
    with pytest.raises(StepError, match="r003"):
        pick(film.save({**data, "picks": {"S01": 3}}), "S01")


def test_module_verbs_reach_the_stage_modules(tmp_path, capsys):
    film = _new(tmp_path)
    assert main(["runner", "progress", str(film)]) == 0
    assert main(["cut", "flash", str(tmp_path / "none.mp4")]) == 1
    assert main(["review", "boards", str(tmp_path / "none.json"), "x.mp4", str(tmp_path / "out")]) == 1
    assert main(["folder", "progress", str(film)]) in (0, 1)
    assert main(["folder"]) == 2
    assert main(["folder", "--help"]) == 0
    assert main(["plan", "--help"]) == 0
    assert "usage: atomic-flix plan" in capsys.readouterr().out


def test_every_verb_has_plain_help(capsys):
    for verb in ("new", "progress", "gate", "time", "bars", "lint", "budget", "shoot", "place", "cut", "review"):
        with pytest.raises(SystemExit) as stop:
            main([verb, "--help"])
        assert stop.value.code == 0
        assert f"usage: atomic-flix {verb}" in capsys.readouterr().out


def test_the_console_script_runs():
    done = subprocess.run([sys.executable, "-m", "atomic_flix.cli", "--help"], capture_output=True, text=True,
                          encoding="utf-8")
    assert done.returncode == 0 and "Film verbs" in done.stdout
