"""Renders in Blender 5.2, headless. Marked `blender`; skipped when Blender is not installed.

  .venv\\Scripts\\python -m pytest tests/scenes -m blender
"""

import json

import numpy as np
import pytest

from atomic_flix.scenes import imageio, plan as planmod, capture

from .conftest import EXAMPLES, FIXTURES, load_json

try:
    BLENDER_APP = capture.find_blender()
except FileNotFoundError:
    BLENDER_APP = None

pytestmark = [pytest.mark.blender, pytest.mark.skipif(BLENDER_APP is None, reason="Blender not installed")]


def _write(tmp_path, scene, name="scene.json"):
    p = tmp_path / name
    p.write_text(json.dumps(scene), encoding="utf-8")
    return p


def test_tiny_pathtrace_cpu_depth_is_right_at_the_box(tmp_path):
    out = tmp_path / "tiny"
    summary = capture.capture_scene(FIXTURES / "tiny.json", out)
    assert summary["frames_rendered"] == 3
    for f in (1, 2, 3):
        for rel in (f"shaded/{f:04d}.png", f"depth/{f:04d}.exr", f"depth/{f:04d}.png", f"facing/{f:04d}.png",
                    f"mist/{f:04d}.png", f"mask/target/{f:04d}.png"):
            assert (out / rel).exists(), rel
    z = imageio.read_exr(out / "depth" / "0002.exr")["Z"]
    assert z.shape == (36, 64)
    assert z[18, 32] == pytest.approx(5.0, rel=0.01)
    assert z[0, 0] == pytest.approx(100.0)            # sky is clip_end
    mask = imageio.read_png(out / "mask" / "target" / "0001.png")
    assert mask[18, 32] == 255 and mask[0, 0] == 0
    facing = imageio.read_png(out / "facing" / "0001.png").astype(int)
    assert facing[18, 32, 2] > 240                    # the face looks back at the camera
    rj = load_json(out / "capture.json")
    assert rj["renderer"] == "pathtrace" and rj["app_version"].startswith("5.")
    assert len(rj["frames"]) == 3 and all(fr["render_s"] > 0 for fr in rj["frames"])


def test_street_example_three_frames_eevee(tmp_path):
    scene = planmod.apply_overrides(load_json(EXAMPLES / "street.json"), size=(480, 264), samples=8)
    out = tmp_path / "street"
    summary = capture.capture_scene(_write(tmp_path, scene), out, frames=(1, 3))
    assert summary["frames_rendered"] == 3
    for f in (1, 2, 3):
        shaded = imageio.read_png(out / "shaded" / f"{f:04d}.png")
        assert shaded.shape[:2] == (264, 480)
        assert shaded.std() > 10, "shaded is blank"
        depth16 = imageio.read_png(out / "depth" / f"{f:04d}.png")
        assert depth16.max() > depth16.min()
        facing = imageio.read_png(out / "facing" / f"{f:04d}.png")
        assert facing.std() > 5
        mist = imageio.read_png(out / "mist" / f"{f:04d}.png")
        assert mist.max() > mist.min()
        mask = imageio.read_png(out / "mask" / "eye-on-stalk" / f"{f:04d}.png")
        assert 0 < (mask == 255).mean() < 0.5, "the eyes should cover part of the frame"
    cam = load_json(out / "viewpoint.json")
    assert len(cam["frames"]) == 145
    assert np.isfinite(load_json(out / "capture.json")["warm_mean_render_s"])
