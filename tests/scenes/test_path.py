"""Camera paths, easing and the viewpoint.json maths (OpenCV convention)."""

import math

import numpy as np
import pytest

from atomic_flix.scenes import geom, path


def _cam(path_spec, lens=32.0):
    return {"lens": lens, "film_mm": 36.0, "near": 0.1, "far": 2000.0, "path": path_spec}


# ---------------------------------------------------------------- easing

def test_smooth35_matches_the_street_formula():
    for t in (0.0, 0.25, 0.5, 0.8, 1.0):
        s = t * t * (3 - 2 * t)
        assert path.ease("eased35", t) == pytest.approx(s * 0.35 + t * 0.65)
    assert path.ease("eased35", 0.0) == 0.0
    assert path.ease("eased35", 0.5) == pytest.approx(0.5)
    assert path.ease("eased35", 1.0) == pytest.approx(1.0)


@pytest.mark.parametrize("name", sorted(path.EASES))
def test_every_ease_runs_from_zero_to_one_and_never_goes_back(name):
    values = [path.ease(name, i / 50) for i in range(51)]
    assert values[0] == pytest.approx(0.0)
    assert values[-1] == pytest.approx(1.0)
    assert all(b >= a - 1e-12 for a, b in zip(values, values[1:]))


def test_unknown_ease_is_an_error():
    with pytest.raises(ValueError, match="wobble"):
        path.ease("wobble", 0.5)


# ---------------------------------------------------------------- presets

def test_push_hits_both_ends_and_has_one_record_per_frame():
    spec = {"move": "push", "from": [0, 0, 1.4], "to": [17, 0, 1.4], "pitch": 7, "yaw": 10.7, "ease": "eased35"}
    frames = path.viewpoint_frames(_cam(spec), frames=145, seed=1)
    assert [fr["f"] for fr in frames] == list(range(1, 146))
    assert frames[0]["pos"] == pytest.approx([0, 0, 1.4])
    assert frames[-1]["pos"] == pytest.approx([17, 0, 1.4])
    mid = frames[72]["pos"][0]
    assert mid == pytest.approx(17 * path.ease("eased35", 0.5))


def test_push_without_to_moves_along_the_heading():
    spec = {"move": "push", "from": [0, 0, 1], "distance": 10, "yaw": 90, "pitch": 0}
    frames = path.viewpoint_frames(_cam(spec), frames=5, seed=1)
    assert frames[-1]["pos"] == pytest.approx([0, 10, 1], abs=1e-9)


def test_pull_truck_and_crane_directions():
    base = {"from": [0, 0, 1], "distance": 4, "yaw": 0, "pitch": 0}
    pull = path.viewpoint_frames(_cam({"move": "pull", **base}), frames=3, seed=1)[-1]["pos"]
    truck = path.viewpoint_frames(_cam({"move": "truck", **base}), frames=3, seed=1)[-1]["pos"]
    crane = path.viewpoint_frames(_cam({"move": "crane", **base}), frames=3, seed=1)[-1]["pos"]
    assert pull == pytest.approx([-4, 0, 1], abs=1e-9)
    assert truck == pytest.approx([0, -4, 1], abs=1e-9)  # to the camera's right when it looks down +x
    assert crane == pytest.approx([0, 0, 5], abs=1e-9)


def test_still_holds():
    frames = path.viewpoint_frames(_cam({"move": "still", "pos": [1, 2, 3], "yaw": 30}), frames=4, seed=1)
    for fr in frames:
        assert fr["pos"] == pytest.approx([1, 2, 3])
        assert np.allclose(fr["rot"], frames[0]["rot"])


def test_orbit_keeps_radius_and_looks_at_the_centre():
    spec = {"move": "orbit", "center": [2, 1, 1], "radius": 5, "height": 1.5, "start": 0, "end": 90}
    frames = path.viewpoint_frames(_cam(spec), frames=9, seed=1)
    for fr in frames:
        dx, dy = fr["pos"][0] - 2, fr["pos"][1] - 1
        assert math.hypot(dx, dy) == pytest.approx(5)
        assert fr["pos"][2] == pytest.approx(1.5)
        forward = -np.asarray(fr["rot"])[:, 2]
        to_centre = np.array([2, 1, 1]) - np.array(fr["pos"])
        assert np.dot(forward, to_centre / np.linalg.norm(to_centre)) == pytest.approx(1.0)
    assert frames[0]["pos"] == pytest.approx([7, 1, 1.5])
    assert frames[-1]["pos"] == pytest.approx([2, 6, 1.5])


def test_handheld_is_seeded_small_and_smooth():
    spec = {"move": "handheld", "pos": [0, 0, 1.5], "amp_cm": 2, "amp_deg": 0.5}
    a = path.viewpoint_frames(_cam(spec), frames=48, seed=4)
    b = path.viewpoint_frames(_cam(spec), frames=48, seed=4)
    c = path.viewpoint_frames(_cam(spec), frames=48, seed=5)
    assert [fr["pos"] for fr in a] == [fr["pos"] for fr in b]
    assert [fr["pos"] for fr in a] != [fr["pos"] for fr in c]
    for fr in a:
        assert np.linalg.norm(np.subtract(fr["pos"], [0, 0, 1.5])) <= 0.02 * math.sqrt(3) + 1e-9
    steps = [np.linalg.norm(np.subtract(p["pos"], q["pos"])) for p, q in zip(a, a[1:])]
    assert max(steps) < 0.01


def test_keys_interpolate_with_per_segment_ease_and_lens():
    spec = {"keys": [
        {"f": 1, "pos": [0, 0, 1], "yaw": 0, "lens": 24},
        {"f": 11, "pos": [10, 0, 1], "yaw": 0, "lens": 50, "ease": "even"},
    ]}
    frames = path.viewpoint_frames(_cam(spec), frames=11, seed=1)
    assert frames[5]["pos"] == pytest.approx([5, 0, 1])
    assert frames[0]["lens"] == 24 and frames[-1]["lens"] == 50
    assert frames[5]["lens"] == pytest.approx(37)


def test_keys_hold_before_the_first_and_after_the_last():
    spec = {"keys": [{"f": 3, "pos": [1, 0, 1]}, {"f": 5, "pos": [3, 0, 1]}]}
    frames = path.viewpoint_frames(_cam(spec), frames=8, seed=1)
    assert frames[0]["pos"] == pytest.approx([1, 0, 1])
    assert frames[-1]["pos"] == pytest.approx([3, 0, 1])


def test_keys_with_look_point_the_camera():
    spec = {"keys": [{"f": 1, "pos": [0, 0, 0], "look": [0, 5, 0]}]}
    fr = path.viewpoint_frames(_cam(spec), frames=1, seed=1)[0]
    assert -np.asarray(fr["rot"])[:, 2] == pytest.approx([0, 1, 0], abs=1e-9)


def test_shake_can_ride_on_any_preset():
    spec = {"move": "push", "from": [0, 0, 1], "to": [5, 0, 1], "shake": {"amp_cm": 3}}
    shaken = path.viewpoint_frames(_cam(spec), frames=30, seed=2)
    plain = path.viewpoint_frames(_cam({k: v for k, v in spec.items() if k != "shake"}), frames=30, seed=2)
    assert any(abs(a["pos"][1] - b["pos"][1]) > 1e-4 for a, b in zip(shaken, plain))


# ---------------------------------------------------------------- rotation conventions

def test_yaw_pitch_matches_street_py_euler():
    """street.py sets rotation_euler = (90 + pitch, 0, -90 + yaw) in XYZ order."""
    pitch, yaw = 7.0, 10.7
    rx, rz = math.radians(90 + pitch), math.radians(-90 + yaw)
    mx = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
    mz = np.array([[math.cos(rz), -math.sin(rz), 0], [math.sin(rz), math.cos(rz), 0], [0, 0, 1]])
    expected = mz @ mx
    got = np.asarray(path.yaw_pitch_rotation(yaw, pitch, 0.0))
    assert np.allclose(got, expected, atol=1e-12)


def test_quaternion_round_trip():
    rot = path.yaw_pitch_rotation(33, -12, 5)
    q = geom.quat_from_matrix(rot)
    assert np.allclose(geom.matrix_from_quat(q), rot, atol=1e-12)
    assert np.linalg.norm(q) == pytest.approx(1.0)


# ---------------------------------------------------------------- camera.json records

def test_fx_for_32mm_lens_on_36mm_sensor_at_1920():
    k = path.intrinsics(32, 36, 1920, 1056)
    assert k[0][0] == pytest.approx(1706.6667, abs=1e-3)
    assert k[1][1] == pytest.approx(k[0][0])
    assert k[0][2] == 960 and k[1][2] == 528


def test_record_projects_a_known_point_to_the_pixel():
    spec = {"move": "still", "pos": [0, 0, 1.4], "yaw": 0, "pitch": 0}
    fr = path.viewpoint_frames(_cam(spec), frames=1, seed=1)[0]
    rec = path.camera_record(fr, 1920, 1056, 36.0)
    # straight ahead -> image centre
    assert path.to_screen(rec, [10, 0, 1.4]) == pytest.approx([960, 528])
    # 1 m to the left at 10 m: x right is -y world, so u = cx - fx * 1/10
    u, v = path.to_screen(rec, [10, 1, 1.4])
    assert u == pytest.approx(960 - 170.6667, abs=1e-3)
    assert v == pytest.approx(528)
    # 1 m up at 10 m: y down in OpenCV
    u, v = path.to_screen(rec, [10, 0, 2.4])
    assert v == pytest.approx(528 - 170.6667, abs=1e-3)
    # behind the camera
    assert path.to_screen(rec, [-3, 0, 1.4]) is None


def test_record_fields():
    spec = {"move": "still", "pos": [0, 0, 1.4], "yaw": 20, "pitch": 5}
    fr = path.viewpoint_frames(_cam(spec), frames=1, seed=1)[0]
    rec = path.camera_record(fr, 1920, 1056, 36.0)
    assert set(rec) == {"f", "pos", "quat_wxyz", "lens_mm", "fov_x_deg", "K", "to_view"}
    assert rec["fov_x_deg"] == pytest.approx(math.degrees(2 * math.atan(18 / 32)))
    w2c = np.asarray(rec["to_view"])
    assert w2c.shape == (4, 4)
    cam_origin = w2c @ np.array([0, 0, 1.4, 1.0])
    assert cam_origin[:3] == pytest.approx([0, 0, 0], abs=1e-12)


def test_unknown_preset_is_an_error():
    with pytest.raises(ValueError, match="zoom"):
        path.viewpoint_frames(_cam({"move": "zoom"}), frames=2, seed=1)
