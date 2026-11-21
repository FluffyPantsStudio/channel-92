"""`refs` and the cast lines of `progress`: what each character's sheet still lacks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atomic_flix.cli import main
from atomic_flix.cli.cast_steps import cast_lines
from atomic_flix.cli.common import Film
from sheet_samples import write_sheet

pytestmark = pytest.mark.usefixtures("no_eval_hook")


def _film(tmp_path: Path) -> Film:
    mix = tmp_path / "mix.wav"
    mix.write_bytes(b"RIFF fake")
    folder = tmp_path / "films" / "sheets"
    assert main(["new", str(folder), "--song", str(mix), "--star", "Nova", "--who", "a singer with silver hair",
                 "--aspect", "16:9", "--by", "Test Person", "--words", "wide"]) == 0
    return Film.open(folder)


def _with_views(film: Film, views: dict) -> Film:
    data = json.loads(film.folder.film.read_text(encoding="utf-8"))
    data["star"] = {**data["star"], "views": views}
    return film.save(data)


def test_refs_writes_a_prompt_per_missing_view_and_names_the_pictures(tmp_path, capsys):
    film = _film(tmp_path)
    capsys.readouterr()
    assert main(["refs", str(film.root)]) == 0
    out = capsys.readouterr().out
    for view in ("front", "three_quarter", "profile", "back", "body_front", "body_three_quarter", "body_back"):
        assert view in out
    assert "refs/nova-back.png" in out and "1024x1536" in out and "1152x1536" in out
    assert "POSE PLATE" in out and "never nude" in out and "CCIP" in out
    assert (film.root / "plan" / "refs" / "nova-back.prompt.txt").is_file()


def test_refs_says_so_when_the_sheet_is_whole(tmp_path, capsys):
    film = _with_views(_film(tmp_path), write_sheet(tmp_path / "films" / "sheets", "Nova"))
    capsys.readouterr()
    assert main(["refs", str(film.root)]) == 0
    assert "names all its views" in capsys.readouterr().out
    assert not (film.root / "plan" / "refs").exists()


def test_progress_says_what_the_sheet_lacks(tmp_path):
    (line,) = cast_lines(_film(tmp_path))
    assert line.startswith("todo") and "Nova" in line and "front, three_quarter, profile, back, body_front" in line
    assert "atomic-flix refs" in line


def test_progress_is_ok_for_a_whole_plain_sheet(tmp_path):
    film = _with_views(_film(tmp_path), write_sheet(tmp_path / "films" / "sheets", "Nova"))
    (line,) = cast_lines(film)
    assert line.startswith("ok") and "plain backdrops" in line


def test_progress_names_a_view_with_an_environment(tmp_path):
    film = _with_views(_film(tmp_path), write_sheet(tmp_path / "films" / "sheets", "Nova", busy=True))
    (line,) = cast_lines(film)
    assert line.startswith("todo") and "back has an environment behind the figure" in line


def test_progress_names_a_view_that_is_too_small(tmp_path):
    film = _with_views(_film(tmp_path), write_sheet(tmp_path / "films" / "sheets", "Nova", wide=True))
    (line,) = cast_lines(film)
    assert "front is too small" in line and "environment" not in line


def test_refs_board_makes_one_board_per_complete_sheet(tmp_path, capsys):
    film = _with_views(_film(tmp_path), write_sheet(tmp_path / "films" / "sheets", "Nova"))
    capsys.readouterr()
    assert main(["refs", str(film.root), "--board"]) == 0
    assert "refs/boards/nova-board.png" in capsys.readouterr().out
    assert (film.root / "refs" / "boards" / "nova-board.png").stat().st_size > 1000


def test_refs_board_names_a_sheet_with_a_view_missing(tmp_path, capsys):
    film = _film(tmp_path)
    capsys.readouterr()
    assert main(["refs", str(film.root), "--board"]) == 1
    assert "no board" in capsys.readouterr().out
