"""`shoot` and `progress` for action shots staged in Blender: the control clip a take follows, the graph that must be
able to carry it, and what `progress` says is missing (docs/action.md)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from atomic_flix.cli import main
from atomic_flix.cli import shoot_steps
from atomic_flix.cli.common import Film, StepError
from atomic_flix.cli.project_steps import action_lines

pytestmark = pytest.mark.usefixtures("no_eval_hook")

JOB = {"scene": "scenes/N09.json", "out": "blender/N09", "guide": "depth"}
PLATE = {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "$wording"}},
         "2": {"class_type": "LoadImage", "inputs": {"image": "$opening_still"}},
         "3": {"class_type": "RandomNoise", "inputs": {"noise_seed": "$seed"}},
         "4": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "flix/$save_as"}}}
ACTION = {**PLATE, "5": {"class_type": "LoadVideo", "inputs": {"video": "$video"}}}


def _film(tmp_path: Path) -> Film:
    mix = tmp_path / "mix.wav"
    mix.write_bytes(b"RIFF fake")
    folder = tmp_path / "films" / "chase"
    assert main(["new", str(folder), "--song", str(mix), "--aspect", "16:9", "--by", "Test Person",
                 "--words", "wide"]) == 0
    return Film.open(folder)


def _graph(film: Film, name: str, graph: dict) -> str:
    path = film.root / "graphs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(graph), encoding="utf-8")
    return str(path)


def _clip(film: Film, name: str = "depth-ltx.mp4") -> Path:
    path = film.root / "blender" / "N09" / "controls" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"clip")
    return path


def _task() -> dict:
    return {"type": "cutaway", "route": "blender", "blender": JOB, "still": "stills/N09.png", "seconds": 5,
            "closing_still": None}


def _prompt(film: Film) -> None:
    (film.root / "plan").mkdir(exist_ok=True)
    (film.root / "plan" / "N09.prompt.txt").write_text("the android sprints", encoding="utf-8")


# the control clip -----------------------------------------------------------------------------------------------------

def test_a_blender_shot_without_a_control_clip_is_refused_with_the_commands_that_make_one(tmp_path):
    film = _film(tmp_path)
    with pytest.raises(StepError) as refused:
        shoot_steps.blender_clip(film, "N09", JOB)
    text = str(refused.value)
    assert "depth control clip" in text and "scenes capture scenes/N09.json blender/N09" in text
    assert "scenes controls blender/N09" in text


def test_the_clip_of_the_shots_guide_is_the_one_the_take_follows(tmp_path):
    film = _film(tmp_path)
    _clip(film, "pose-ltx.mp4")
    depth = _clip(film, "depth-ltx.mp4")
    assert shoot_steps.blender_clip(film, "N09", JOB) == film.folder.relative(depth)


def test_clips_of_two_models_are_not_guessed_between(tmp_path):
    film = _film(tmp_path)
    _clip(film, "depth-scail.mp4")
    _clip(film, "depth-ltx.mp4")
    with pytest.raises(StepError, match="2 depth clips"):
        shoot_steps.blender_clip(film, "N09", JOB)


def test_a_scene_edited_after_its_clip_was_made_is_refused(tmp_path):
    film = _film(tmp_path)
    clip = _clip(film)
    scene = film.root / "scenes" / "N09.json"
    scene.parent.mkdir()
    scene.write_text("{}", encoding="utf-8")
    later = clip.stat().st_mtime + 10
    os.utime(scene, (later, later))
    with pytest.raises(StepError, match="changed after depth-ltx.mp4"):
        shoot_steps.blender_clip(film, "N09", JOB)


@pytest.mark.parametrize("changed", [{"guide": "*"}, {"out": "../elsewhere"}, {"guide": "magic"}])
def test_a_plan_entry_edited_by_hand_is_refused_before_any_path_is_read(tmp_path, changed):
    film = _film(tmp_path)
    with pytest.raises(StepError, match="plan` again"):
        shoot_steps.blender_clip(film, "N09", {**JOB, **changed})


# the request ---------------------------------------------------------------------------------------------------------

def test_an_action_shot_renders_on_the_action_graph_with_its_clip_as_video(tmp_path):
    film = _film(tmp_path)
    _prompt(film)
    clip = _clip(film)
    graphs = {"vocal": None, "other": _graph(film, "plate.json", PLATE), "action": _graph(film, "action.json", ACTION)}
    (request,) = shoot_steps._requests(film, {"N09": _task()}, {"N09": 1}, graphs)
    assert request.graph.endswith("action.json")
    assert request.inputs["video"] == film.folder.relative(clip)
    assert request.inputs["opening_still"] == "stills/N09.png"


def test_an_action_shot_on_a_graph_with_no_video_slot_is_refused_rather_than_ignored(tmp_path):
    film = _film(tmp_path)
    _prompt(film)
    _clip(film)
    graphs = {"vocal": None, "other": None, "action": _graph(film, "plate.json", PLATE)}
    with pytest.raises(StepError, match="Blender's movement would be ignored"):
        shoot_steps._requests(film, {"N09": _task()}, {"N09": 1}, graphs)


def test_an_action_shot_needs_an_action_graph(tmp_path):
    film = _film(tmp_path)
    _prompt(film)
    graphs = {"vocal": None, "other": _graph(film, "plate.json", PLATE), "action": None}
    with pytest.raises(StepError, match="--action-graph"):
        shoot_steps._requests(film, {"N09": _task()}, {"N09": 1}, graphs)


def test_a_shot_that_is_not_on_the_blender_route_keeps_its_plate_graph(tmp_path):
    film = _film(tmp_path)
    _prompt(film)
    task = {**_task(), "route": None}
    task.pop("blender")
    graphs = {"vocal": None, "other": _graph(film, "plate.json", PLATE), "action": None}
    (request,) = shoot_steps._requests(film, {"N09": task}, {"N09": 1}, graphs)
    assert request.graph.endswith("plate.json") and "video" not in request.inputs


# progress ------------------------------------------------------------------------------------------------------------

def test_progress_says_which_action_shots_still_have_no_blender_scene(tmp_path):
    film = _film(tmp_path)
    film.lineup_rows.write_text("N09 cutaway\n  beat: the android sprints down the street\n", encoding="utf-8")
    lines = action_lines(film)
    assert len(lines) == 1 and lines[0].startswith("todo") and "N09" in lines[0]


def test_progress_ignores_a_shot_list_it_cannot_read(tmp_path):
    film = _film(tmp_path)
    film.lineup_rows.write_text("this is not a shot list\n", encoding="utf-8")
    assert action_lines(film) == []
