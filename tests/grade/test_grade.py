"""The grade: each shot toward the film's own black, white and colour strength, one look over all, no grain."""

import json
import sys

import numpy as np
import pytest

from atomic_flix.grade import (DEFAULT_LOOK, NEUTRAL_LOOK, Look, ShotSpan, grade_cut, luma_table, measure_shots,
                               plan_corrections, spread)
from atomic_flix.grade.correct import COLOUR_GAIN, MAX_LEVEL_MOVE, Levels
from atomic_flix.grade.measure import sample_frames
from gradeclips import FPS, ramp_shot, write_shots


def _levels(key, black, white, colour):
    return Levels(key=key, black=black, white=white, colour=colour)


def test_each_shot_moves_seventy_percent_toward_the_film_median_capped():
    levels = [_levels("A", 0.05, 0.90, 0.10), _levels("B", 0.10, 0.80, 0.10), _levels("C", 0.40, 0.95, 0.10)]
    plan = {c.key: c for c in plan_corrections(levels)}
    assert plan["B"].new_black == pytest.approx(0.10)                 # B is the median: it stays
    assert plan["A"].new_black == pytest.approx(0.05 + 0.7 * 0.05)
    assert plan["C"].new_black == pytest.approx(0.40 - MAX_LEVEL_MOVE)  # 0.7 * 0.30 is over the cap
    assert all(abs(c.new_white - c.white) <= MAX_LEVEL_MOVE + 1e-9 for c in plan.values())


def test_a_flat_shot_keeps_its_levels_and_colour_gain_is_bounded():
    levels = [_levels("flat", 0.40, 0.55, 0.01), _levels("B", 0.05, 0.90, 0.20), _levels("C", 0.06, 0.92, 0.22)]
    plan = {c.key: c for c in plan_corrections(levels)}
    assert (plan["flat"].new_black, plan["flat"].new_white) == (0.40, 0.55)
    assert COLOUR_GAIN[0] <= plan["flat"].gain <= COLOUR_GAIN[1]
    assert plan["flat"].gain == pytest.approx(COLOUR_GAIN[1])


def test_the_luma_table_is_monotonic_and_stays_in_video_range():
    correction = plan_corrections([_levels("A", 0.05, 0.90, 0.1), _levels("B", 0.2, 0.7, 0.1)])[0]
    table = luma_table(correction, DEFAULT_LOOK)
    assert np.all(np.diff(table.astype(int)) >= 0)
    assert table.min() >= 16 and table.max() <= 235


def test_samples_are_two_a_second_and_skip_a_quarter_second_at_each_end():
    frames = sample_frames(ShotSpan("A", 0, 96), FPS)      # 4 s
    assert frames == [12, 24, 36, 48, 60, 72, 84]           # 0.5 to 3.5 s, not 0 s and not past 3.75 s
    assert sample_frames(ShotSpan("B", 10, 13), FPS)        # a shot shorter than half a second still gets one


def test_two_grey_shots_at_different_levels_come_closer(tmp_path):
    clip, spans = write_shots(tmp_path / "cut.mp4", [ramp_shot(2.0, 0.05, 0.70), ramp_shot(2.0, 0.25, 0.95, seed=2),
                                                     ramp_shot(2.0, 0.10, 0.80, seed=3)])
    shots = [ShotSpan(k, a, b) for k, (a, b) in zip("ABC", spans)]
    result = grade_cut(clip, tmp_path / "toned.mp4", shots, FPS, x264_speed="ultrafast")
    for key in ("black", "white"):
        assert result.spread_after[key] < result.spread_before[key]
    assert all(abs(c.new_black - c.black) <= MAX_LEVEL_MOVE + 1e-9 for c in result.corrections)
    account = json.loads((tmp_path / "toned.tone.json").read_text(encoding="utf-8"))
    assert account["grain"] is None and account["spread_before"] and account["spread_after"]
    assert len(account["shots"]) == 3


def test_colour_strength_evens_out_and_each_palette_keeps_its_hue(tmp_path):
    warm = ramp_shot(2.0, 0.1, 0.8, colour=(1.0, 0.75, 0.55))
    cool = ramp_shot(2.0, 0.1, 0.8, colour=(0.85, 0.95, 1.0), seed=2)
    middle = ramp_shot(2.0, 0.1, 0.8, colour=(1.0, 0.9, 0.8), seed=3)
    clip, spans = write_shots(tmp_path / "cut.mp4", [warm, cool, middle])
    shots = [ShotSpan(k, a, b) for k, (a, b) in zip(("warm", "cool", "middle"), spans)]
    before = {m.key: m for m in measure_shots(clip, shots, FPS)}
    result = grade_cut(clip, tmp_path / "toned.mp4", shots, FPS, look=NEUTRAL_LOOK, x264_speed="ultrafast")
    assert result.spread_after["colour"] < result.spread_before["colour"]
    hues = {}
    for name, path in (("before", clip), ("after", tmp_path / "toned.mp4")):
        hues[name] = {m.key: m.hue for m in measure_shots(path, shots, FPS)}
    for key in before:
        assert abs(hues["after"][key] - hues["before"][key]) < 0.05    # radians: the world keeps its palette


def test_no_grain_a_flat_picture_stays_flat(tmp_path):
    flat = np.full((48, 108, 192, 3), 128, np.uint8)
    clip, spans = write_shots(tmp_path / "cut.mp4", [flat])
    grade_cut(clip, tmp_path / "toned.mp4", [ShotSpan("A", *spans[0])], FPS, x264_speed="ultrafast")
    from atomic_flix.cut.media import read_frames
    frames = read_frames(tmp_path / "toned.mp4", grey=True).astype(float)
    assert frames.std(axis=(1, 2)).max() < 0.6


def test_a_look_file_replaces_the_default_look(tmp_path):
    path = tmp_path / "look.json"
    path.write_text(json.dumps({"lift": 0.0, "ceiling": 1.0, "bend": 0.0, "shadow_tint": [0, 0],
                                "light_tint": [0, 0]}), encoding="utf-8")
    look = Look.from_file(path)
    assert look == NEUTRAL_LOOK
    with pytest.raises(ValueError, match="grain"):
        bad = tmp_path / "grainy.json"
        bad.write_text(json.dumps({"grain": 5}), encoding="utf-8")
        Look.from_file(bad)


def test_hooks_receive_the_graded_film_and_the_measurements(tmp_path):
    from atomic_flix.grade.hooks import run_hooks
    hooks = tmp_path / "hooks" / "tone.d"
    hooks.mkdir(parents=True)
    seen = tmp_path / "seen.txt"
    (hooks / "10-note.py").write_text(
        "import sys, pathlib\n"
        f"pathlib.Path(r'{seen}').write_text(sys.argv[1] + '|' + sys.argv[2], encoding='utf-8')\n", encoding="utf-8")
    (hooks / "20-fail.py").write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    problems = run_hooks(hooks, tmp_path / "toned.mp4", tmp_path / "toned.tone.json")
    assert seen.read_text(encoding="utf-8") == f"{tmp_path / 'toned.mp4'}|{tmp_path / 'toned.tone.json'}"
    assert len(problems) == 1 and "20-fail.py" in problems[0] and "3" in problems[0]


def test_spread_is_the_population_deviation():
    levels = [_levels("A", 0.0, 1.0, 0.1), _levels("B", 0.2, 1.0, 0.1)]
    assert spread(levels) == {"black": pytest.approx(0.1), "white": 0.0, "colour": 0.0}


def test_module_command_line_measures_and_applies(tmp_path, capsys):
    from atomic_flix.grade.__main__ import main
    clip, spans = write_shots(tmp_path / "cut.mp4", [ramp_shot(1.0, 0.05, 0.7), ramp_shot(1.0, 0.25, 0.95, seed=2)])
    edit = {"fps": FPS, "size": [192, 108], "start": 0.0, "end": spans[-1][1] / FPS,
            "cuts": [{"key": "A", "at": 0.0}, {"key": "B", "at": spans[1][0] / FPS}],
            "takes": [{"key": "A", "file": "a.mp4", "map": [[0.0, 0.5]]}, {"key": "B", "file": "b.mp4", "map": [[1.0, 0.5]]}]}
    (tmp_path / "cut.edit.json").write_text(json.dumps(edit), encoding="utf-8")
    assert main(["measure", str(clip), "--edit", str(tmp_path / "cut.edit.json")]) == 0
    assert "spread across shots" in capsys.readouterr().out
    out = tmp_path / "toned.mp4"
    assert main(["apply", str(clip), str(out), "--edit", str(tmp_path / "cut.edit.json"), "--speed", "ultrafast"]) == 0
    assert out.is_file() and out.with_suffix(".tone.json").is_file()
    assert main(["apply", str(clip), str(out), "--edit", str(tmp_path / "missing.json")]) == 2
