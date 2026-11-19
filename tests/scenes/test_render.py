"""The Blender runner without Blender: command line, timing summary, CLI."""

import json
from pathlib import Path

import pytest

from atomic_flix.scenes import capture
from atomic_flix.scenes.__main__ import main


def test_blender_command_is_headless_factory_startup(tmp_path):
    cmd = capture.blender_command(Path("C:/b/blender.exe"), tmp_path / "job.json")
    assert cmd[0].endswith("blender.exe")
    assert cmd[1:3] == ["-b", "--factory-startup"]
    assert cmd[cmd.index("-P") + 1].endswith("blender_run.py")
    assert cmd[-2:] == ["--", str(tmp_path / "job.json")]


def test_find_blender_prefers_the_environment(tmp_path, monkeypatch):
    exe = tmp_path / "blender.exe"
    exe.write_text("")
    monkeypatch.setenv("FLIX_BLENDER", str(exe))
    assert capture.find_blender() == exe


def test_find_blender_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIX_BLENDER", str(tmp_path / "nope.exe"))
    with pytest.raises(FileNotFoundError, match="FLIX_BLENDER"):
        capture.find_blender()


def test_summary_of_frame_times():
    frames = [{"f": 1, "render_s": 3.0, "post_s": 0.5}, {"f": 2, "render_s": 0.4, "post_s": 0.3},
              {"f": 3, "render_s": 0.6, "post_s": 0.3}]
    s = capture.summarise(frames, renderer="raster", w=1920, h=1056)
    assert s["renderer"] == "raster"
    assert s["frames_rendered"] == 3
    assert s["warmup_s"] == 3.0
    assert s["mean_render_s"] == pytest.approx(4.0 / 3)
    assert s["warm_mean_render_s"] == pytest.approx(0.5)
    assert s["mean_total_s"] == pytest.approx((3.5 + 0.7 + 0.9) / 3)
    assert s["warm_fps"] == pytest.approx(1 / 0.8)


def test_summary_with_wall_time():
    frames = [{"f": 1, "render_s": 1.0, "post_s": 0.5}, {"f": 2, "render_s": 0.5, "post_s": 0.5}]
    s = capture.summarise(frames, renderer="raster", w=8, h=8, wall_s=4.0)
    assert s["wall_s"] == 4.0
    assert s["wall_fps"] == pytest.approx(0.5)
    assert "wall_fps" not in capture.summarise(frames, renderer="raster", w=8, h=8)


def test_summary_of_one_frame():
    s = capture.summarise([{"f": 1, "render_s": 2.0, "post_s": 1.0}], renderer="pathtrace", w=64, h=36)
    assert s["warm_mean_render_s"] == 2.0


def test_cli_check_and_plan(tmp_path, capsys):
    scene = Path(__file__).parent / "fixtures" / "tiny.json"
    assert main(["check", str(scene)]) == 0
    assert "tiny" in capsys.readouterr().out
    assert main(["plan", str(scene)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["format"] == "atomic-flix/scene-plan@1"


def test_cli_check_reports_errors(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": "atomic-flix/scene@1"}), encoding="utf-8")
    assert main(["check", str(bad)]) == 2
    assert "name" in capsys.readouterr().err


def test_cli_frames_argument():
    assert capture.parse_frames("10:12") == (10, 12)
    assert capture.parse_frames(None) is None
    with pytest.raises(ValueError):
        capture.parse_frames("12:10")
