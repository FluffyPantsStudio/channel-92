"""ACT5 (a still follows its Blender first frame) and PL1/PL2 (a place has a sheet and its shots carry it)."""

from __future__ import annotations

import json

import numpy as np

from atomic_flix.lint import load_book
from atomic_flix.lint.book import book_from_case
from atomic_flix.lint.registry import check_rule
from atomic_flix.scenes.imageio import write_png
from atomic_flix.scenes.overlay import OVERLAY_MIN, edge_match

PLACE = {"views": {"wide": "refs/places/a-wide.png", "reverse": "refs/places/a-rev.png",
                   "landmark": "refs/places/a-lm.png"}, "light": "a sodium lamp on the left wall"}


def _blockout(shift: int = 0, details: bool = False) -> np.ndarray:
    """A grey set of strong shapes. SHIFT moves the layout; DETAILS adds lines a redrawn picture would have."""
    picture = np.full((144, 256, 3), 128, np.uint8)
    picture[16:124, 20 + shift:70 + shift] = (235, 235, 235)
    picture[40:132, 100 + shift:150 + shift] = (20, 20, 20)
    picture[8:60, 170:240] = (240, 240, 240)
    picture[90:136, 180 + shift:236] = (15, 15, 15)
    if details:
        picture[30:34, 75:95] = (250, 250, 250)                   # lines the blockout never had
        picture[70:100, 160:164] = (10, 10, 10)
        picture[110:114, 10:60] = (250, 250, 250)
    return picture


def _png(path, array):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_png(path, array)
    return path


# edge agreement --------------------------------------------------------------------------------------------------------

def test_the_same_layout_with_more_lines_drawn_agrees(tmp_path):
    clay = _png(tmp_path / "clay.png", _blockout())
    redrawn = _png(tmp_path / "redrawn.png", _blockout(details=True))
    assert edge_match(redrawn, clay) >= OVERLAY_MIN


def test_a_recomposed_layout_does_not_agree(tmp_path):
    clay = _png(tmp_path / "clay.png", _blockout())
    moved = _png(tmp_path / "moved.png", _blockout(shift=60))
    assert edge_match(moved, clay) < OVERLAY_MIN


def test_a_picture_that_cannot_be_read_is_named(tmp_path):
    clay = _png(tmp_path / "clay.png", _blockout())
    (tmp_path / "bad.png").write_bytes(b"nope")
    try:
        edge_match(tmp_path / "bad.png", clay)
    except (ValueError, OSError) as problem:
        assert "bad.png" in str(problem) or "cannot identify" in str(problem) or "not a PNG" in str(problem)
    else:
        raise AssertionError("a bad picture was accepted")


# ACT5 ---------------------------------------------------------------------------------------------------------------------

def test_a_still_that_does_not_follow_its_blender_frame_warns_with_the_numbers():
    (finding,) = check_rule("ACT5", book_from_case({"kind": "cutaway", "overlay": {"S01": 0.3}}))
    assert finding.level == "warn" and "30% of the blockout's lines" in finding.message and "60% is the least" in finding.message


def test_a_still_that_follows_it_passes_and_a_reason_answers_the_warning():
    assert not check_rule("ACT5", book_from_case({"kind": "cutaway", "overlay": {"S01": 0.9}}))
    book = book_from_case({"kind": "cutaway", "overlay": {"S01": 0.3}, "film": {"reasons": {"ACT5:S01": "a close crop"}}})
    assert check_rule("ACT5", book)[0].reason == "a close crop"


def test_a_loaded_blender_shot_is_compared_with_its_first_frame(tmp_path):
    (tmp_path / "film.json").write_text(json.dumps({"name": "T"}), encoding="utf-8")
    (tmp_path / "shots.txt").write_text("N09 cutaway\n  beat: a car\n  blender: scenes/N09.json\n", encoding="utf-8")
    (tmp_path / "plan").mkdir()
    task = {"key": "N09", "type": "cutaway", "route": "blender", "still": "stills/N09.png",
            "blender": {"scene": "scenes/N09.json", "out": "blender/N09", "guide": "depth"}}
    (tmp_path / "plan" / "N09.task.json").write_text(json.dumps(task), encoding="utf-8")
    _png(tmp_path / "blender/N09/controls/first-ltx.png", _blockout())
    _png(tmp_path / "stills/N09.png", _blockout(shift=60))
    (finding,) = check_rule("ACT5", load_book(tmp_path))
    assert finding.key == "N09" and "does not follow" in finding.message
    _png(tmp_path / "stills/N09.png", _blockout(details=True))
    assert not check_rule("ACT5", load_book(tmp_path))


# places ----------------------------------------------------------------------------------------------------------------------

def test_a_place_with_one_picture_and_no_light_note_blocks():
    film = {"places": {"alley": {"views": {"wide": "refs/places/a-wide.png"}}}}
    messages = [f.message for f in check_rule("PL1", book_from_case({"film": film}))]
    assert any("no reverse, landmark picture" in m for m in messages) and any("no `light` note" in m for m in messages)


def test_a_whole_place_sheet_passes():
    assert not check_rule("PL1", book_from_case({"film": {"places": {"alley": PLACE}}}))


def test_a_place_view_that_is_not_in_the_folder_blocks():
    book = book_from_case({"film": {"places": {"alley": PLACE}}, "files": ["refs/places/a-wide.png"]})
    assert len(check_rule("PL1", book)) == 2


def _in_place(refs, scene="alley"):
    return book_from_case({"kind": "cutaway", "shot": {"scene": scene}, "film": {"places": {"alley": PLACE}},
                           "still": {"refs": refs}})


def test_a_still_in_a_registered_place_carries_its_wide_picture():
    (finding,) = check_rule("PL2", _in_place([]))
    assert "is in the place alley" in finding.message and "a-wide.png" in finding.message
    assert not check_rule("PL2", _in_place([PLACE["views"]["wide"]]))


def test_a_shot_in_no_registered_place_is_not_touched():
    assert not check_rule("PL2", _in_place([], scene="elsewhere"))
    assert not check_rule("PL2", book_from_case({"kind": "cutaway", "film": {"places": {"alley": PLACE}}}))
