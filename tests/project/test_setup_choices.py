"""Setup choices made before anything is generated: the aspect (the director's) and the year (it only suggests)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import numpy as np
import pytest

from atomic_flix.cli import main
from atomic_flix.cli.common import Film, StepError
from atomic_flix.cli.shoot_steps import clear_to_shoot
from atomic_flix.lint import book_from_case, check_rule

WORDS = "Four by three, like the old sets.\nNo letterbox."


def _new(tmp_path: Path, *extra: str) -> Path:
    film = tmp_path / "films" / "sunny"
    assert main(["new", str(film), *extra]) == 0
    return film


def _film(folder: Path) -> dict:
    return json.loads((folder / "film.json").read_text(encoding="utf-8"))


def _progress(folder: Path, capsys) -> list[str]:
    capsys.readouterr()
    main(["progress", str(folder)])
    return capsys.readouterr().out.splitlines()


def test_choose_aspect_writes_setup_frame_and_size_and_the_words_word_for_word(tmp_path, capsys):
    folder = _new(tmp_path)
    assert main(["choose", str(folder), "aspect", "4:3", "--by", "Test Person", "--words", WORDS]) == 0
    data = _film(folder)
    assert data["setup"]["aspect"] == "4:3" and data["setup"]["tier"] == "standard"
    assert data["setup"]["aspect_by"] == "Test Person"
    assert data["frame"] == [1024, 768] and data["final_size"] == [1440, 1080]
    notes = (folder / "notes.md").read_text(encoding="utf-8")
    assert "> Four by three, like the old sets.\n> No letterbox.\n" in notes
    assert datetime.date.today().isoformat() in notes and "aspect 4:3" in notes


def test_the_draft_tier_renders_smaller_at_the_same_delivery(tmp_path):
    folder = _new(tmp_path)
    assert main(["choose", str(folder), "aspect", "16:9", "--tier", "draft", "--by", "P", "--words", "wide"]) == 0
    data = _film(folder)
    assert data["frame"] == [1024, 576] and data["final_size"] == [1920, 1080]


def test_choose_aspect_needs_the_person_and_a_known_aspect(tmp_path, capsys):
    folder = _new(tmp_path)
    with pytest.raises(SystemExit):
        main(["choose", str(folder), "aspect", "4:3"])
    assert main(["choose", str(folder), "aspect", "21:9", "--by", "P", "--words", "w"]) == 2
    assert "16:9, 4:3, 2.39:1, 9:16" in capsys.readouterr().err
    assert "setup" not in _film(folder)


def test_choose_year_records_it_and_only_suggests(tmp_path, capsys):
    folder = _new(tmp_path)
    capsys.readouterr()
    assert main(["choose", str(folder), "year", "1962"]) == 0
    out = capsys.readouterr().out
    data = _film(folder)
    assert data["setup"] == {"year": 1962}
    assert "4:3" in out and "suggest" in out
    assert "year 1962" in (folder / "notes.md").read_text(encoding="utf-8")


def test_a_year_outside_the_channel_is_refused_plainly(tmp_path, capsys):
    folder = _new(tmp_path)
    assert main(["choose", str(folder), "year", "1931"]) == 2
    assert "1950 to 2010" in capsys.readouterr().err
    assert "setup" not in _film(folder)


@pytest.mark.parametrize("argv", [["aspect", "4:3", "--by", "Claude", "--words", "square"],
                                  ["aspect", "4:3", "--by", "the model", "--words", "square"],
                                  ["year", "1962", "--by", "Agent007"]])
def test_choose_refuses_a_name_that_reads_as_a_machine(tmp_path, capsys, argv):
    folder = _new(tmp_path)
    before = (folder / "notes.md").read_bytes() if (folder / "notes.md").is_file() else None
    assert main(["choose", str(folder), *argv]) == 2
    assert "model or an agent" in capsys.readouterr().err
    assert "setup" not in _film(folder)
    assert ((folder / "notes.md").read_bytes() if (folder / "notes.md").is_file() else None) == before


def test_new_refuses_a_machine_name_before_any_folder_is_made(tmp_path, capsys):
    film = tmp_path / "films" / "sunny"
    with pytest.raises(SystemExit):
        main(["new", str(film), "--aspect", "16:9", "--by", "assistant", "--words", "wide"])
    assert "model or an agent" in capsys.readouterr().err and not film.exists()


def test_a_hand_edited_year_outside_the_channel_is_a_to_do_in_progress(tmp_path, capsys):
    folder = _new(tmp_path, "--aspect", "16:9", "--by", "P", "--words", "wide")
    data = _film(folder)
    data["setup"]["year"] = 2015
    (folder / "film.json").write_text(json.dumps(data), encoding="utf-8")
    lines = _progress(folder, capsys)
    year_line = next(line for line in lines if "2015" in line)
    assert year_line.startswith("todo") and "choose FILM year" in year_line


def test_new_takes_aspect_and_year(tmp_path):
    folder = _new(tmp_path, "--aspect", "9:16", "--year", "2004", "--by", "Test Person", "--words", "for phones")
    data = _film(folder)
    assert data["setup"]["aspect"] == "9:16" and data["setup"]["year"] == 2004
    assert data["frame"] == [704, 1280] and data["final_size"] == [1080, 1920]
    assert "> for phones" in (folder / "notes.md").read_text(encoding="utf-8")


def test_progress_lists_the_aspect_right_after_the_concept(tmp_path, capsys):
    folder = _new(tmp_path)
    lines = _progress(folder, capsys)
    structure = next(i for i, line in enumerate(lines) if "structure" in line and "gate 1" in line)
    assert lines[structure + 1].startswith("todo") and "aspect not chosen" in lines[structure + 1]
    main(["choose", str(folder), "aspect", "16:9", "--by", "P", "--words", "wide"])
    assert not any("aspect not chosen" in line for line in _progress(folder, capsys))


def test_a_frame_without_a_setup_block_is_not_taken_as_chosen(tmp_path, capsys):
    folder = _new(tmp_path)
    data = _film(folder)
    assert data["frame"] and data["final_size"] and "setup" not in data
    assert any("aspect not chosen" in line for line in _progress(folder, capsys))


def test_plan_refuses_in_one_sentence_while_the_aspect_is_unset(tmp_path, capsys):
    folder = _new(tmp_path)
    assert main(["plan", str(folder)]) == 2
    err = capsys.readouterr().err.strip()
    assert "aspect" in err and "choose" in err and err.count(". ") == 0


def test_shoot_refuses_while_the_aspect_is_unset(tmp_path, monkeypatch):
    folder = _new(tmp_path)
    monkeypatch.setattr("atomic_flix.cli.shoot_steps.require_gate", lambda *args, **kwargs: None)
    with pytest.raises(StepError, match="aspect"):
        clear_to_shoot(Film.open(folder))


def test_lint_refuses_a_still_or_frame_of_another_ratio():
    chosen = {"setup": {"aspect": "4:3"}, "frame": [1024, 768]}
    assert not check_rule("AR1", book_from_case({"film": chosen, "pictures": {"S01": [1024, 768]}}))
    wrong_still = check_rule("AR1", book_from_case({"film": chosen, "pictures": {"S01": [1280, 720]}}))
    assert [f.key for f in wrong_still] == ["S01"] and "still" in wrong_still[0].message
    wrong_frame = check_rule("AR1", book_from_case({"film": {**chosen, "frame": [1280, 704]}}))
    assert wrong_frame and "frame" in wrong_frame[0].message
    assert not check_rule("AR1", book_from_case({"film": {"frame": [1280, 704]}, "pictures": {"S01": [10, 99]}}))


def test_lint_reads_each_still_size_from_the_film_folder(tmp_path):
    from atomic_flix.cut.media import write_image
    from atomic_flix.lint import load_book

    folder = _new(tmp_path, "--aspect", "4:3", "--by", "P", "--words", "square")
    (folder / "shots.txt").write_text("N01 cutaway\n  beat: rain\n\nN02 cutaway\n  beat: sun\n", encoding="utf-8")
    write_image(folder / "stills" / "N01.png", np.zeros((768, 1024, 3), np.uint8))
    write_image(folder / "stills" / "N02.png", np.zeros((720, 1280, 3), np.uint8))
    book = load_book(folder)
    assert book.pictures == {"N01": (1024, 768), "N02": (1280, 720)}
    assert [finding.key for finding in check_rule("AR1", book)] == ["N02"]
