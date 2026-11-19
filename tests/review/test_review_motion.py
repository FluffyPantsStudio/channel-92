import numpy as np
import pytest

from atomic_flix.review.motion import (camera_drift, end_windows, jumps, mouth_energy, still_ends)
from reviewclips import FPS, HEIGHT, WIDTH, busy_box, panning, texture


def _grey(frames):
    return frames[..., 0].astype(np.float64) / 255


def test_drift_follows_a_pan():
    frames = _grey(panning(2.0, 2.0))
    drift = camera_drift(frames, FPS)
    assert drift.dx == pytest.approx(-94 / WIDTH, abs=0.02)
    assert abs(drift.dy) < 0.01
    assert drift.largest == pytest.approx(94 / WIDTH, abs=0.02)


def test_drift_of_a_locked_camera_is_near_zero():
    still = np.repeat(texture(WIDTH, HEIGHT)[None], 48, axis=0).astype(np.float64) / 255
    drift = camera_drift(still, FPS)
    assert drift.largest < 0.005


def test_a_small_moving_subject_is_not_camera_drift():
    base = texture(WIDTH, HEIGHT).astype(np.float64) / 255
    frames = np.repeat(base[None], 48, axis=0).copy()
    for number in range(48):
        frames[number, 70:100, 20 + 3 * number:50 + 3 * number] = 1.0
    assert camera_drift(frames, FPS).largest < 0.01


def test_still_tail_and_still_head_are_measured():
    moving_then_still = _grey(panning(3.0, 2.0, still_after=2.0))
    head, tail = still_ends(moving_then_still, FPS)
    assert head == pytest.approx(0.0, abs=0.05)
    assert tail == pytest.approx(1.0, abs=0.1)
    still_then_moving = moving_then_still[::-1]
    head, tail = still_ends(still_then_moving, FPS)
    assert head == pytest.approx(1.0, abs=0.1)
    assert tail == pytest.approx(0.0, abs=0.05)


def test_a_hard_change_inside_a_shot_is_a_jump():
    pan = _grey(panning(1.0, 1.0))
    held = np.repeat(pan[-1:], 24, axis=0)
    other = np.repeat(texture(WIDTH, HEIGHT, seed=2)[None], 24, axis=0).astype(np.float64) / 255
    frames = np.concatenate([pan, held, other])
    found = jumps(frames, FPS)
    assert found == [pytest.approx((24 + 24) / FPS, abs=0.05)]


def test_end_windows_flag_a_shot_that_settles_still():
    frames = _grey(panning(3.0, 2.0, still_after=2.4))
    account = end_windows(frames, FPS)
    assert account["opening"]["still"] is False
    assert account["closing"]["still"] is True


def test_mouth_energy_follows_singing():
    box = (0.4, 0.55, 0.2, 0.15)
    frames = _grey(busy_box(4.0, box, busy=[(1.0, 3.0)]))
    vocal_on = (np.arange(len(frames)) / FPS >= 1.0) & (np.arange(len(frames)) / FPS < 3.0)
    account = mouth_energy(frames, box, vocal_on, FPS)
    assert account["ratio"] > 3
    assert account["correlation"] > 0.5
    assert account["flags"] == []


def test_a_still_mouth_while_singing_is_flagged():
    box = (0.4, 0.55, 0.2, 0.15)
    frames = _grey(busy_box(4.0, box, busy=[]))
    vocal_on = np.arange(len(frames)) / FPS >= 1.0
    account = mouth_energy(frames, box, vocal_on, FPS)
    assert any("barely moves" in flag for flag in account["flags"])


def test_a_mouth_moving_through_silence_is_flagged():
    box = (0.4, 0.55, 0.2, 0.15)
    frames = _grey(busy_box(4.0, box, busy=[(0.0, 4.0)]))
    vocal_on = (np.arange(len(frames)) / FPS >= 1.0) & (np.arange(len(frames)) / FPS < 3.0)
    account = mouth_energy(frames, box, vocal_on, FPS)
    assert any("silence" in flag for flag in account["flags"])


def _walker(count=48, size=(110, 120), speed=3, top=40, seed=5):
    """A locked textured background with a big textured subject walking left to right through it."""
    base = texture(WIDTH, HEIGHT).astype(np.float64) / 255
    foreground = texture(size[1], size[0], seed=seed).astype(np.float64) / 255
    frames = np.repeat(base[None], count, axis=0).copy()
    for number in range(count):
        left = 10 + speed * number
        right = min(WIDTH, left + size[1])
        frames[number, top:top + size[0], left:right] = foreground[:, :right - left]
    return frames


def test_a_big_subject_walking_through_a_locked_frame_is_subject_motion_not_drift():
    frames = _walker()
    drift = camera_drift(frames, FPS)
    assert drift.largest < 0.01
    assert drift.foreground > 0.2          # a large share of the picture moves on its own


def test_a_pan_with_a_subject_in_it_still_reads_as_the_pan():
    pan = _grey(panning(2.0, 2.0))
    foreground = texture(80, 70, seed=9).astype(np.float64) / 255
    frames = pan.copy()
    for number in range(len(frames)):
        frames[number, 60:130, 120:200] = foreground   # held still on screen while the background pans
    drift = camera_drift(frames, FPS)
    assert drift.dx == pytest.approx(-94 / WIDTH, abs=0.02)


def test_a_background_mask_keeps_a_subject_at_the_edge_out_of_the_camera():
    frames = _walker(size=(170, 150), top=5, speed=2)
    background = np.ones((HEIGHT, WIDTH), bool)
    background[:, :] = True
    background[0:180, 0:260] = False                 # where the subject passes, from a performer mask
    drift = camera_drift(frames, FPS, background=background)
    assert drift.largest < 0.01
