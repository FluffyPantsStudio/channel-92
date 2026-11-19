"""Splitting Blender's multi-layer EXR into the pass files, without Blender."""

import numpy as np
import pytest

from atomic_flix.scenes import imageio, layers, path


def _fake_render(tmp_path, h=12, w=16, sky_cols=4):
    z = np.full((h, w), 5.0, np.float32)
    z[:, :sky_cols] = 1e10                       # background, as Blender writes it
    facing = np.zeros((h, w, 3), np.float32)
    facing[:, sky_cols:] = [-1.0, 0.0, 0.0]      # faces pointing back at a camera that looks down +x
    mist = np.linspace(0, 1, w, dtype=np.float32)[None].repeat(h, 0)
    m1 = np.zeros((h, w), np.float32)
    m1[3:9, 6:12] = 1.0
    m1[2, 6:12] = 0.3                            # an anti-aliased edge below the threshold
    parts = {
        "ViewLayer.Depth": {"ViewLayer.Depth.Z": z},
        "ViewLayer.Normal": {f"ViewLayer.Normal.{c}": facing[..., i] for i, c in enumerate("XYZ")},
        "ViewLayer.Mist": {"ViewLayer.Mist.Z": mist},
        "ViewLayer.m1": {"ViewLayer.m1.X": m1},
    }
    exr = tmp_path / "frame.exr"
    imageio.write_exr_parts(exr, parts)
    return exr


def _meta():
    rot = path.yaw_pitch_rotation(0, 0, 0)
    return {"far": 100.0, "depth_range": [0.5, 100.0], "cam_rot": [list(r) for r in rot],
            "layers": ["shaded", "depth", "facing", "mist", "mask"],
            "masks": [{"index": 1, "name": "target", "aov": "m1"}]}


def test_split_frame_writes_every_pass(tmp_path):
    exr = _fake_render(tmp_path)
    written = layers.split_frame(exr, tmp_path / "out", 7, _meta())
    out = tmp_path / "out"
    for rel in ("depth/0007.exr", "depth/0007.png", "facing/0007.png", "mist/0007.png", "mask/target/0007.png"):
        assert (out / rel).exists(), rel
    assert set(written) == {"depth", "depth16", "facing", "mist", "mask/target"}


def test_depth_sky_becomes_clip_end_and_metres_survive(tmp_path):
    exr = _fake_render(tmp_path)
    layers.split_frame(exr, tmp_path / "out", 1, _meta())
    z = imageio.read_exr(tmp_path / "out" / "depth" / "0001.exr")["Z"]
    assert z[0, 0] == pytest.approx(100.0)
    assert z[0, 10] == pytest.approx(5.0)


def test_depth_png_is_16_bit_inverse_depth(tmp_path):
    exr = _fake_render(tmp_path)
    layers.split_frame(exr, tmp_path / "out", 1, _meta())
    d = imageio.read_png(tmp_path / "out" / "depth" / "0001.png")
    assert d.dtype == np.uint16
    assert d[0, 0] == 0                         # sky at the far end
    expected = (1 / 5 - 1 / 100) / (1 / 0.5 - 1 / 100)
    assert d[0, 10] / 65535 == pytest.approx(expected, abs=1e-4)


def test_inverse_depth_is_monotonic_and_clipped():
    z = np.array([0.1, 0.5, 1, 5, 50, 100, 1e10], np.float32)
    v = layers.inverse_depth(z, 0.5, 100.0)
    assert v[0] == 1.0 and v[1] == pytest.approx(1.0) and v[-1] == 0.0
    assert np.all(np.diff(v) <= 0)


def test_normals_move_to_camera_space(tmp_path):
    exr = _fake_render(tmp_path)
    layers.split_frame(exr, tmp_path / "out", 1, _meta())
    n = imageio.read_png(tmp_path / "out" / "facing" / "0001.png").astype(int)
    # a face looking back at the camera points along +z in camera space (x right, y up, z toward the viewer)
    assert n[5, 10].tolist() == pytest.approx([128, 128, 255], abs=1)


def test_camera_normals_function():
    rot = path.yaw_pitch_rotation(90, 0, 0)     # looking down +y
    n = np.array([[[0.0, -1.0, 0.0], [1.0, 0.0, 0.0]]], np.float32)
    c = layers.camera_normals(n, rot)
    assert c[0, 0] == pytest.approx([0, 0, 1], abs=1e-6)   # faces the camera
    assert c[0, 1] == pytest.approx([1, 0, 0], abs=1e-6)   # +x world is to the right when looking down +y


def test_mask_is_0_or_255(tmp_path):
    exr = _fake_render(tmp_path)
    layers.split_frame(exr, tmp_path / "out", 1, _meta())
    m = imageio.read_png(tmp_path / "out" / "mask" / "target" / "0001.png")
    assert set(np.unique(m).tolist()) == {0, 255}
    assert m[2, 8] == 0 and m[5, 8] == 255


def test_mist_is_8_bit(tmp_path):
    exr = _fake_render(tmp_path)
    layers.split_frame(exr, tmp_path / "out", 1, _meta())
    m = imageio.read_png(tmp_path / "out" / "mist" / "0001.png")
    assert m.dtype == np.uint8 and m[0, 0] == 0 and m[0, -1] == 255


def test_only_requested_passes(tmp_path):
    exr = _fake_render(tmp_path)
    meta = _meta()
    meta["layers"] = ["shaded", "depth"]
    written = layers.split_frame(exr, tmp_path / "out", 1, meta)
    assert set(written) == {"depth", "depth16"}
    assert not (tmp_path / "out" / "facing").exists()


def test_missing_channel_is_a_clear_error(tmp_path):
    exr = tmp_path / "e.exr"
    imageio.write_exr(exr, {"ViewLayer.Combined.R": np.zeros((2, 2), np.float32)})
    with pytest.raises(ValueError, match="Depth"):
        layers.split_frame(exr, tmp_path / "out", 1, _meta())
