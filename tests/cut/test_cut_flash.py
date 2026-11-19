import numpy as np
import pytest

from atomic_flix.cut.flash import check_flashes, count_transitions, relative_luminance
from atomic_flix.cut.media import write_video
from cutclips import flashing_frames


def test_relative_luminance_of_black_white_and_mid_grey():
    rgb = np.array([[[0, 0, 0], [255, 255, 255], [128, 128, 128]]], np.uint8)
    lum = relative_luminance(rgb)
    assert lum[0, 0] == pytest.approx(0.0)
    assert lum[0, 1] == pytest.approx(1.0)
    assert lum[0, 2] == pytest.approx(0.2158, abs=0.002)


def test_same_direction_transitions_merge():
    lum = np.array([0.0, 0.2, 0.4, 0.6, 0.6, 0.3, 0.0]).reshape(-1, 1, 1) * np.ones((1, 4, 4))
    marks = count_transitions(lum)
    assert [direction for _, direction in marks] == [1, -1]


def test_full_frame_flashing_five_times_a_second_fails(tmp_path):
    clip = write_video(tmp_path / "f5.mp4", flashing_frames(3.0, 10.0), 24, crf=10)
    account = check_flashes(clip)
    assert account.passed is False
    assert account.worst_count > 3
    assert account.failing and account.failing[0][0] < 1.0
    assert "red" in account.note.lower()


def test_full_frame_flashing_twice_a_second_passes(tmp_path):
    clip = write_video(tmp_path / "f2.mp4", flashing_frames(3.0, 4.0), 24, crf=10)
    account = check_flashes(clip)
    assert account.passed is True
    assert account.flash_count >= 4


def test_a_small_square_flashing_fast_passes(tmp_path):
    clip = write_video(tmp_path / "sq.mp4", flashing_frames(3.0, 10.0, area=0.10), 24, crf=10)
    account = check_flashes(clip)
    assert account.passed is True
    assert account.flash_count == 0


def test_a_single_hard_cut_is_no_flash(tmp_path):
    frames = np.zeros((48, 54, 96, 3), np.uint8)
    frames[24:] = 255
    account = check_flashes(write_video(tmp_path / "cut.mp4", frames, 24, crf=10))
    assert account.passed is True and account.flash_count == 0
