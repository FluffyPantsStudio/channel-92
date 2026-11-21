"""Action shots are staged in Blender: the shot list's `blender:` and `no_blender:`, the plan's route, and which shots
count as action (docs/action.md)."""

from __future__ import annotations

import os

import pytest

from atomic_flix.plan import Line, PlanError, Pulse, ShotSpec, parse_shot_list, plan_film
from atomic_flix.plan.action import (NO_CLIP, NO_SCENE, NOT_CAPTURED, READY, STALE, action_words, may_need_blender,
                                     maybe_words, needs_blender, progress_lines, staging)

CHASE = "N09 cutaway\n  figures: yes\n  beat: the android sprints down the street and leaps the rail\n"


def _shot(**fields) -> ShotSpec:
    return ShotSpec(key="N09", kind="cutaway", **fields)


def _pulse() -> Pulse:
    return Pulse(beats=tuple(float(k) for k in range(40)), downbeat_slot=0)


# the shot list -------------------------------------------------------------------------------------------------------

def test_the_shot_list_reads_the_blender_scene_and_the_written_reason():
    text = CHASE + "  blender: scenes/N09-chase.json\n\nN10 cutaway\n  beat: she runs at once\n  no_blender: one frame\n"
    first, second = parse_shot_list(text)
    assert first.blender == "scenes/N09-chase.json" and first.no_blender is None
    assert second.no_blender == "one frame" and second.blender is None


# which shots are action ----------------------------------------------------------------------------------------------

def test_a_chase_beat_is_an_action_shot_that_needs_blender():
    shot = parse_shot_list(CHASE)[0]
    assert action_words(shot) == ["sprints"] and maybe_words(shot) == ["leaps"]
    assert needs_blender(shot)


@pytest.mark.parametrize("beat", ["dust drifts slowly through the light",
                                  "her heart races as the light fades",
                                  "a thought runs through her mind",
                                  "the tub walks toward us on long thin legs"])
def test_a_calm_or_figurative_beat_is_not_an_action_shot(beat):
    assert not needs_blender(_shot(beats=(beat,)))


@pytest.mark.parametrize("beat", ["a tear runs down her cheek", "the kick drum hits", "her heart leaps",
                                  "sunlight breaks through the clouds", "a crash cymbal rings",
                                  "mascara runs down her face", "a jump cut to the chorus"])
def test_a_figure_of_speech_never_blocks(beat):
    assert not needs_blender(_shot(beats=(beat,)))


def test_words_that_may_mean_action_ask_a_person():
    shot = _shot(beats=("a body falls out of frame in the distance",))
    assert may_need_blender(shot) and not needs_blender(shot)
    assert not may_need_blender(_shot(beats=("a body falls out of frame",), blender="scenes/N09.json"))


def test_what_she_does_in_a_sung_line_is_never_staged_in_blender():
    shot = ShotSpec(key="S01", kind="vocal", sings=("v01",), acts={"v01": "she punches the wall"})
    assert not needs_blender(shot) and not may_need_blender(shot)
    mute = ShotSpec(key="M01", kind="mute", acts={"v01": "she punches the wall"})
    assert needs_blender(mute)


def test_a_blender_scene_or_the_persons_reason_takes_a_shot_off_the_list():
    beats = ("the android sprints down the street",)
    assert not needs_blender(_shot(beats=beats, blender="scenes/N09.json"))
    assert not needs_blender(_shot(beats=beats, no_blender="a one-second glimpse, from the film's own footage"))
    assert needs_blender(_shot(beats=beats, no_blender="   "))


# the plan's route ----------------------------------------------------------------------------------------------------

def test_a_blender_shot_is_planned_on_the_blender_route():
    shots = [_shot(beats=("the android sprints down the street",), blender="scenes/N09.json"),
             ShotSpec(key="N10", kind="cutaway", beats=("dust drifts",))]
    plan = plan_film(shots, {}, _pulse(), ends_at=12.0)
    assert plan.tasks["N09"]["route"] == "blender"
    assert plan.tasks["N09"]["blender"] == {"scene": "scenes/N09.json", "out": "blender/N09", "guide": "depth"}
    assert "route" not in plan.tasks["N10"]


def test_the_shots_guide_picks_the_control_clip():
    shot = _shot(beats=("a fight",), blender="scenes/N09.json", extra={"guide": "Pose"})
    plan = plan_film([shot, ShotSpec(key="N10", kind="cutaway")], {}, _pulse(), ends_at=12.0)
    assert plan.tasks["N09"]["blender"]["guide"] == "pose"


def test_an_unknown_guide_is_refused_by_name():
    shot = _shot(blender="scenes/N09.json", extra={"guide": "magic"})
    with pytest.raises(PlanError, match="N09: guide 'magic'"):
        plan_film([shot, ShotSpec(key="N10", kind="cutaway")], {}, _pulse(), ends_at=12.0)


def test_a_sung_shot_cannot_be_staged_in_blender():
    shot = ShotSpec(key="S01", kind="vocal", sings=("v01",), blender="scenes/S01.json")
    line = Line(key="v01", part="lead", text="la la la", start=10.4, end=13.6)
    with pytest.raises(PlanError, match="cover the action with a cutaway"):
        plan_film([shot], {"v01": line}, _pulse(), ends_at=20.0)


# how far the staging has come ----------------------------------------------------------------------------------------

def test_staging_names_the_first_thing_a_blender_shot_still_lacks(tmp_path):
    shot = _shot(blender="scenes/N09.json")
    assert staging(tmp_path, shot) == NO_SCENE
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "N09.json").write_text("{}", encoding="utf-8")
    assert staging(tmp_path, shot) == NOT_CAPTURED
    out = tmp_path / "blender" / "N09"
    (out / "controls").mkdir(parents=True)
    (out / "capture.json").write_text("{}", encoding="utf-8")
    assert staging(tmp_path, shot) == NO_CLIP
    (out / "controls" / "pose-ltx.mp4").write_bytes(b"clip")
    assert staging(tmp_path, shot) == NO_CLIP                   # the shot's guide is depth, not pose
    (out / "controls" / "depth-ltx.mp4").write_bytes(b"clip")
    assert staging(tmp_path, shot) == READY


def test_a_scene_edited_after_its_capture_is_stale(tmp_path):
    shot = _shot(blender="scenes/N09.json")
    scene = tmp_path / "scenes" / "N09.json"
    scene.parent.mkdir()
    scene.write_text("{}", encoding="utf-8")
    capture = tmp_path / "blender" / "N09" / "capture.json"
    capture.parent.mkdir(parents=True)
    capture.write_text("{}", encoding="utf-8")
    later = capture.stat().st_mtime + 10
    os.utime(scene, (later, later))
    assert staging(tmp_path, shot) == STALE


def test_a_scene_path_that_leaves_the_film_folder_counts_as_missing(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    film = tmp_path / "film"
    film.mkdir()
    assert staging(film, _shot(blender="../outside.json")) == NO_SCENE


def test_progress_lists_action_shots_and_blender_shots_only(tmp_path):
    shots = [_shot(beats=("the android sprints down the street",)),
             ShotSpec(key="N10", kind="cutaway", beats=("dust drifts",), blender="scenes/N10.json"),
             ShotSpec(key="N11", kind="cutaway", beats=("dust drifts",))]
    lines = progress_lines(tmp_path, shots)
    assert len(lines) == 2
    assert lines[0].startswith("todo") and "N09" in lines[0] and "sprints" in lines[0] and "no_blender" in lines[0]
    assert lines[1].startswith("todo") and "N10" in lines[1] and NO_SCENE in lines[1]


def test_progress_asks_about_a_word_that_may_mean_action(tmp_path):
    (line,) = progress_lines(tmp_path, [_shot(beats=("a body falls out of frame",))])
    assert line.startswith("check") and "falls out of" in line
