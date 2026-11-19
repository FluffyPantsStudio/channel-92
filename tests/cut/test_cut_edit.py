import json

import pytest

from atomic_flix.cut.bars import beat_count
from atomic_flix.cut.edit import Cut, Edit, EditError, Placed, load_edit, sung_intervals


def _edit(cuts, takes, start=0.0, end=4.0, **extra):
    return Edit(fps=24, size=(192, 108), song=None, start=start, end=end, cuts=tuple(cuts), takes=takes, **extra)


def test_take_time_follows_a_single_point_at_1x():
    placed = Placed(key="A", file="a.mp4", map=((10.0, 0.5),))
    assert placed.take_time(10.0) == pytest.approx(0.5)
    assert placed.take_time(11.25) == pytest.approx(1.75)


def test_take_time_interpolates_points_and_keeps_1x_outside():
    placed = Placed(key="A", file="a.mp4", map=((2.0, 1.0), (4.0, 4.0)))
    assert placed.take_time(3.0) == pytest.approx(2.5)
    assert placed.take_time(5.0) == pytest.approx(5.0)
    assert placed.take_time(1.0) == pytest.approx(0.0)
    assert placed.rates_between(2.0, 4.0) == [pytest.approx(1.5)]


def test_shift_adds_seconds_to_take_time():
    placed = Placed(key="A", file="a.mp4", map=((0.0, 1.0),), shift=0.03)
    assert placed.take_time(0.0) == pytest.approx(1.03)


def test_map_must_run_forward():
    with pytest.raises(EditError):
        Placed(key="A", file="a.mp4", map=((2.0, 1.0), (3.0, 0.5)))


def test_shots_span_frames_from_cut_to_cut():
    takes = {"A": Placed("A", "a.mp4", ((0.0, 0.5),)), "B": Placed("B", "b.mp4", ((2.0, 0.5),))}
    edit = _edit([Cut("A", 0.0), Cut("B", 2.0)], takes)
    shots = edit.shots()
    assert [(s.key, s.frame_in, s.end_frame) for s in shots] == [("A", 0, 48), ("B", 48, 96)]
    assert shots[1].start == pytest.approx(2.0) and shots[1].end == pytest.approx(4.0)


def test_two_cuts_at_one_time_is_an_error():
    takes = {"A": Placed("A", "a.mp4", ((0.0, 0.5),)), "B": Placed("B", "b.mp4", ((2.0, 0.5),))}
    with pytest.raises(EditError, match="one time"):
        _edit([Cut("A", 1.0), Cut("B", 1.0)], takes).shots()


def test_cut_without_a_placed_take_is_an_error():
    with pytest.raises(EditError, match="no placed take"):
        _edit([Cut("A", 0.0)], {}).shots()


def test_load_edit_resolves_paths_against_its_folder(tmp_path):
    (tmp_path / "plan").mkdir()
    (tmp_path / "plan" / "cuts.json").write_text(json.dumps({"cuts": [{"key": "S02", "at": 1.0, "grid": "one"}]}),
                                                  encoding="utf-8")
    spec = {"fps": 24, "size": [192, 108], "song": "audio/mix.wav", "start": 1.0, "end": 3.0,
            "cuts": "plan/cuts.json",
            "takes": [{"key": "S02", "file": "renders/S02/r001.mp4", "map": [[1.0, 0.5]], "setup": "moon"}]}
    path = tmp_path / "edit.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    edit = load_edit(path)
    assert edit.song == tmp_path / "audio" / "mix.wav"
    assert edit.takes["S02"].file == tmp_path / "renders" / "S02" / "r001.mp4"
    assert edit.cuts[0].grid == "one" and edit.takes["S02"].setup == "moon"


def test_sung_intervals_remove_gaps():
    lines = {"lines": [{"id": "v01", "start": 1.0, "end": 3.0, "gaps": [[1.5, 1.8]]},
                       {"id": "v02", "start": 4.0, "end": 5.0}]}
    assert sung_intervals(lines) == [(1.0, 1.5), (1.8, 3.0), (4.0, 5.0)]


def test_beat_count_names_the_count_of_the_bar():
    beats = [0.5 * i for i in range(20)]
    assert beat_count(2.0, beats, downbeat_slot=0) == (1, pytest.approx(0.0))
    assert beat_count(2.5, beats, downbeat_slot=0)[0] == 2
    assert beat_count(3.0, beats, downbeat_slot=0)[0] == 3
    assert beat_count(3.0, beats, downbeat_slot=2)[0] == 1
    assert beat_count(3.2, beats, downbeat_slot=0)[0] is None
