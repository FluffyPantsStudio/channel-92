import numpy as np
import pytest

from atomic_flix.timing.level import frame_db, running_median, working_level, quiet_line

from voice_synth import voice


def test_full_scale_sine_reads_minus_three_dbfs():
    rate = 48000
    t = np.arange(rate) / rate
    sine = np.sin(2 * np.pi * 1000 * t)
    db = frame_db(sine, rate)
    assert np.median(db) == pytest.approx(-3.0, abs=0.05)


def test_frames_are_ten_milliseconds():
    rate = 16000
    db = frame_db(np.zeros(rate * 2), rate)
    assert len(db) == 200


def test_stereo_level_counts_both_channels_without_cancelling():
    rate = 16000
    t = np.arange(rate) / rate
    sine = np.sin(2 * np.pi * 500 * t)
    assert np.median(frame_db(np.stack([sine, sine], axis=1), rate)) == pytest.approx(-3.0, abs=0.05)
    # Opposite channels cancel in a mono fold; the level must still read the sound.
    assert np.median(frame_db(np.stack([sine, -sine], axis=1), rate)) == pytest.approx(-3.0, abs=0.05)


def test_silence_has_a_floor_not_minus_infinity():
    db = frame_db(np.zeros(1600), 16000)
    assert np.all(np.isfinite(db))
    assert np.all(db <= -100)


def test_working_level_ignores_silence_and_follows_the_loud_part():
    x = voice(10.0, [(1.0, 3.0, -14.0), (5.0, 6.0, -20.0)])
    db = frame_db(x, 16000)
    work = working_level(db)
    assert -15.5 < work < -12.5
    assert quiet_line(work) == pytest.approx(work - 18.0)


def test_working_level_needs_some_sound():
    with pytest.raises(ValueError):
        working_level(np.full(100, -90.0))


def test_running_median_removes_a_one_frame_spike():
    db = np.full(20, -40.0)
    db[10] = 0.0
    assert running_median(db, 5)[10] == -40.0
    assert len(running_median(db, 5)) == 20
