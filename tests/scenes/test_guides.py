"""Control clips for the video models, made from the capture layers."""

import json
import shutil

import numpy as np
import pytest

from atomic_flix.scenes import guides, imageio, path


# ---------------------------------------------------------------- size rules

@pytest.mark.parametrize("model,size", [("ltx", (1152, 640)), ("ltx", (1280, 768)), ("scail", (864, 480)),
                                        ("wan", (832, 480)), ("scail", (1280, 704))])
def test_sizes_that_work(model, size):
    guides.check_guide_size(model, *size)


@pytest.mark.parametrize("model,size", [("ltx", (1280, 704)), ("ltx", (1920, 1056)), ("scail", (870, 480)),
                                        ("wan", (832, 470))])
def test_sizes_that_break_the_rule_are_errors(model, size):
    with pytest.raises(guides.GuideSizeError, match=str(size[0]) if size[0] % 32 else str(size[1])):
        guides.check_guide_size(model, *size)


def test_unknown_model():
    with pytest.raises(ValueError, match="sora"):
        guides.check_guide_size("sora", 1152, 640)


def test_parse_size():
    assert guides.parse_size("1152x640") == (1152, 640)
    with pytest.raises(ValueError):
        guides.parse_size("1152 by 640")


# ---------------------------------------------------------------- fitting frames

def test_cover_transform_fills_and_centres():
    s, ox, oy = guides.cover_transform(1920, 1056, 1152, 640)
    assert s == pytest.approx(640 / 1056)
    assert oy == pytest.approx(0)
    assert ox == pytest.approx((1920 * s - 1152) / 2)


def test_resize_cover_shape_and_values():
    a = np.tile(np.arange(40, dtype=np.float32), (20, 1))
    b = guides.resize_cover(a, 20, 10)
    assert b.shape == (10, 20)
    assert np.all(np.diff(b[5]) > 0)
    rgb = np.zeros((20, 40, 3), np.uint8)
    assert guides.resize_cover(rgb, 20, 10).shape == (10, 20, 3)


# ---------------------------------------------------------------- depth guide

def test_depth_guide_is_monotonic_fixed_and_sky_black():
    near = np.full((4, 4), 2.0, np.float32)
    far = np.full((4, 4), 20.0, np.float32)
    sky = np.full((4, 4), 100.0, np.float32)
    frames = [np.concatenate([near, far, sky], axis=1), np.concatenate([near * 0.5, far, sky], axis=1)]
    lo, hi = guides.depth_range(frames, far=100.0)
    out = [guides.depth_to_guide(z, lo, hi) for z in frames]
    assert out[0].dtype == np.uint8
    assert out[0][0, 10] == 0 and out[1][0, 10] == 0           # sky at the far value
    assert out[1][0, 0] == 255                                 # the nearest thing in the shot is white
    assert out[0][0, 0] > out[0][0, 5] > 0                     # nearer is brighter
    assert out[0][0, 5] == out[1][0, 5]                        # range fixed: the far wall does not pump


# ---------------------------------------------------------------- edges

def test_canny_finds_the_edges_of_a_square():
    img = np.zeros((40, 40), np.float32)
    img[10:30, 10:30] = 1.0
    e = guides.canny(img)
    assert e.dtype == np.uint8 and set(np.unique(e).tolist()) <= {0, 255}
    assert e[20, 8:12].max() == 255 and e[20, 28:32].max() == 255
    assert e[20, 15:25].max() == 0 and e[0:5, 0:5].max() == 0
    # thin: about one pixel wide on a straight edge
    assert (e[20, 5:15] > 0).sum() <= 2


def test_canny_on_rgb():
    img = np.zeros((30, 30, 3), np.uint8)
    img[:, 15:] = 200
    assert guides.canny(img)[15, 13:17].max() == 255


def test_edges_from_a_depth_step():
    z = np.full((20, 20), 5.0, np.float32)
    z[:, 10:] = 50.0
    e = guides.depth_edges(z)
    assert e[10, 9:11].max() == 255 and e[10, :7].max() == 0 and e[10, 13:].max() == 0


# ---------------------------------------------------------------- pose

def _record():
    fr = path.viewpoint_frames({"lens": 32, "film_mm": 36, "near": 0.1, "far": 100,
                             "path": {"move": "still", "pos": [0, 0, 1.4]}}, frames=1, seed=1)[0]
    return path.camera_record(fr, 1920, 1056, 36.0)


def test_pose_projection_and_behind_camera_dropped():
    rec = _record()
    pts = guides.project_joints({"neck": [10, 0, 1.4], "nose": [-2, 0, 1.4]}, rec, 1920, 1056, 1152, 640)
    s, ox, oy = guides.cover_transform(1920, 1056, 1152, 640)
    assert pts["neck"] == pytest.approx([960 * s - ox, 528 * s - oy])
    assert "nose" not in pts


def test_draw_pose_paints_sticks_on_black():
    pts = {"neck": (50, 20), "r_shoulder": (35, 22), "r_elbow": (30, 40), "nose": (50, 10)}
    img = guides.draw_pose(pts, 100, 60)
    assert img.shape == (60, 100, 3) and img.dtype == np.uint8
    assert img[0, 0].sum() == 0
    assert img[21, 42].sum() > 0          # on the neck-shoulder stick
    assert img[50, 90].sum() == 0


# ---------------------------------------------------------------- whole folder

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def _fake_out(tmp_path, n=3, w=96, h=54):
    out = tmp_path / "capture"
    rec_frames = []
    for f in range(1, n + 1):
        shaded = np.zeros((h, w, 3), np.uint8)
        shaded[:, w // 2:] = 180
        imageio.write_png(out / "shaded" / f"{f:04d}.png", shaded)
        z = np.full((h, w), 8.0 - f, np.float32)
        z[:5] = 50.0
        imageio.write_exr(out / "depth" / f"{f:04d}.exr", {"Z": z})
        fr = path.viewpoint_frames({"lens": 32, "film_mm": 36, "near": 0.1, "far": 50,
                                 "path": {"move": "still", "pos": [0, 0, 1.4]}}, frames=1, seed=1)[0]
        rec = path.camera_record({**fr, "f": f}, w, h, 36.0)
        rec_frames.append(rec)
    (out / "viewpoint.json").write_text(json.dumps({"format": "atomic-flix/viewpoint@1", "w": w, "h": h, "fps": 24,
                                                 "far": 50.0, "convention": "opencv",
                                                 "frames": rec_frames}), encoding="utf-8")
    rig = {"op": "rig", "block": "performer", "frames": [{"neck": [6, 0, 1.4], "r_shoulder": [6, -0.2, 1.4],
                                                          "nose": [6, 0, 1.6]}] * n}
    (out / "plan.json").write_text(json.dumps({"format": "atomic-flix/scene-plan@1", "ops": [rig]}), encoding="utf-8")
    return out


@needs_ffmpeg
def test_make_guides_writes_clips_and_a_record(tmp_path):
    out = _fake_out(tmp_path)
    info = guides.make_guides(out, "ltx", (256, 128))
    for key in ("depth", "canny", "edges", "pose", "first", "last"):
        assert (out / info["files"][key]).exists(), key
    rec = json.loads((out / "controls" / "controls-ltx.json").read_text(encoding="utf-8"))
    assert rec["size"] == [256, 128] and rec["frames"] == 3
    assert rec["depth"]["kind"] == "inverse"
    first = imageio.read_png(out / info["files"]["first"])
    assert first.shape == (128, 256, 3)


@needs_ffmpeg
def test_make_guides_refuses_a_bad_size(tmp_path):
    out = _fake_out(tmp_path)
    with pytest.raises(guides.GuideSizeError):
        guides.make_guides(out, "ltx", (1280, 704))


@needs_ffmpeg
def test_video_frames_round_trip(tmp_path):
    frames = [np.full((32, 48, 3), v, np.uint8) for v in (0, 128, 255)]
    p = tmp_path / "v.mp4"
    guides.write_video(frames, p, fps=24)
    back = list(guides.read_frames(p, 48, 32))
    assert len(back) == 3
    assert abs(int(back[1].mean()) - 128) <= 3
