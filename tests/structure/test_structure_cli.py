"""`atomic-flix structure FILM` on the synthetic song: the first analysis, before gate 1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atomic_flix.cli import FILM_ORDER, main
from atomic_flix.gates import gate_spec
from tool_loader import load_tool


@pytest.fixture
def film(tmp_path) -> tuple[Path, dict]:
    song = tmp_path / "song"
    truth = load_tool("synth_song").write_song(song)
    aim = tmp_path / "films" / "tiny-song"
    assert main(["new", str(aim), "--song", str(song / "mix.wav"), "--voice", str(song / "voice.wav"),
                 "--band", str(song / "band.wav"), "--drums", str(song / "drums.wav"),
                 "--lyric", str(song / "lyric.txt")]) == 0
    return aim, truth


def test_structure_runs_time_and_bars_when_missing_and_writes_both_files(film, capsys):
    aim, truth = film
    capsys.readouterr()
    assert main(["structure", str(aim), "--gap", "5"]) == 0
    out = capsys.readouterr().out
    assert "ran `time`" in out and "ran `bars`" in out
    assert (aim / "analysis/voice-lines.json").is_file() and (aim / "analysis/pulse.json").is_file()
    data = json.loads((aim / "analysis/structure.json").read_text(encoding="utf-8"))
    assert data["format"] == "atomic-flix/structure@1"
    assert [s["label"] for s in data["sections"]] == [
        "Instrumental 1", "Verse", "Instrumental 2", "Verse (continued)", "Instrumental 3", "Chorus",
        "Instrumental 4"]
    sung = [(x["start"], x["end"]) for x in truth["lines"]]
    expected = [sung[0], (sung[1][0], sung[2][1]), sung[3]]
    flat = [t for region in data["vocal_regions"] for t in region]
    assert flat == pytest.approx([t for region in expected for t in region], abs=0.15)
    ones = json.loads((aim / "analysis/pulse.json").read_text(encoding="utf-8"))["ones"]
    inner = [s["start"] for s in data["sections"][1:]]
    assert all(min(abs(t - o) for o in ones) < 0.01 for t in inner)
    assert len(data["pacing"]["story_gaps"]) == 3
    page = (aim / "plan/structure.md").read_text(encoding="utf-8")
    assert "three instrumental breaks of 5 s or more" in page and "Verse (continued)" in page


def test_structure_reuses_the_analysis_already_there(film, capsys):
    aim, _ = film
    assert main(["time", str(aim)]) == 0 and main(["bars", str(aim)]) == 0
    capsys.readouterr()
    assert main(["structure", str(aim)]) == 0
    out = capsys.readouterr().out
    assert "ran `time`" not in out and "ran `bars`" not in out
    assert "read analysis/voice-lines.json" in out and "read analysis/pulse.json" in out
    data = json.loads((aim / "analysis/structure.json").read_text(encoding="utf-8"))
    assert data["pacing"]["story_gaps"] == []


def test_structure_needs_the_lead_stem(tmp_path, capsys):
    aim = tmp_path / "films" / "bare"
    assert main(["new", str(aim)]) == 0
    assert main(["structure", str(aim)]) == 2
    assert "lead vocal" in capsys.readouterr().err


def test_progress_names_the_structure_first_and_gate_one_shows_its_page(film, capsys):
    aim, _ = film
    capsys.readouterr()
    main(["progress", str(aim)])
    out = capsys.readouterr().out
    assert "atomic-flix structure" in out and "before gate 1" in out
    assert "plan/structure.md" in out
    assert main(["structure", str(aim)]) == 0
    capsys.readouterr()
    main(["progress", str(aim)])
    assert "ok     plan/structure.md" in capsys.readouterr().out
    shows = gate_spec("concept").shows
    assert "plan/structure.md" in shows and gate_spec("concept").question == "Is this the film?"
    assert FILM_ORDER.index("structure") < FILM_ORDER.index("time")


def test_structure_has_plain_help(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["structure", "--help"])
    assert stop.value.code == 0
    assert "usage: atomic-flix structure" in capsys.readouterr().out
