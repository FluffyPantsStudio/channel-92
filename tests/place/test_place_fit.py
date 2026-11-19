"""Placing a render on the song by its sound: synthetic shifts, stretches, drift, pauses and unrelated audio."""

from __future__ import annotations

import numpy as np
import pytest

from atomic_flix.place.features import levels_db, resample, sound_features
from atomic_flix.place.fit import fit_by_sound, render_time_at, voiced_phrases
from place_signals import RATE, band, delayed, sung, to_rate

VOCAL_SPANS = [(0.5, 2.5), (3.1, 5.0)]


@pytest.fixture(scope="module")
def sent() -> np.ndarray:
    return sung(6.0, VOCAL_SPANS)


def test_a_full_scale_1k_sine_reads_minus_3_dbfs():
    t = np.arange(RATE) / RATE
    levels = levels_db(np.sin(2 * np.pi * 1000 * t), RATE)
    assert np.median(levels) == pytest.approx(-3.01, abs=0.05)


def test_resample_keeps_length_and_a_tone():
    t = np.arange(48_000) / 48_000
    tone = np.sin(2 * np.pi * 440 * t)
    out = resample(tone, 48_000, 16_000)
    assert len(out) == 16_000
    spectrum = np.abs(np.fft.rfft(out))
    assert np.argmax(spectrum) == pytest.approx(440, abs=1)


def test_features_ignore_level(sent):
    loud = sound_features(sent, RATE)
    quiet = sound_features(sent * 10 ** (-8 / 20), RATE)
    similarity = np.sum(loud * quiet, axis=1)
    assert np.median(similarity) > 0.999


def test_voiced_phrases_find_the_sung_stretches(sent):
    found = voiced_phrases(sent, RATE)
    assert len(found) == 2
    for (start, end), (want_start, want_end) in zip(found, VOCAL_SPANS):
        assert start == pytest.approx(want_start, abs=0.06)
        assert end == pytest.approx(want_end, abs=0.1)


def test_same_audio_delayed_and_8_db_down_places_at_the_delay(sent):
    clip = to_rate(delayed(sent, 0.3, trim_db=-8.0), RATE, 44_100)
    fit = fit_by_sound(sent, RATE, clip, 44_100)
    assert fit["how"] == "sound"
    assert len(fit["vocal_spans"]) == 2
    assert all(p["cost"] < 0.05 for p in fit["vocal_spans"])
    assert fit["offset"] == pytest.approx(0.30, abs=0.02)
    assert all(p["rate"] == pytest.approx(1.0, abs=0.03) for p in fit["vocal_spans"])
    assert fit["added_rests"] == []


def test_the_map_carries_song_time_to_render_time(sent):
    clip = delayed(sent, 0.3)
    fit = fit_by_sound(sent, RATE, clip, RATE, slice_start=187.0)
    assert render_time_at(fit, 188.0) == pytest.approx(1.3, abs=0.02)
    assert render_time_at(fit, 190.5) == pytest.approx(3.8, abs=0.02)
    times = [song for song, _ in fit["map"]]
    take_files = [r for _, r in fit["map"]]
    assert times == sorted(times) and take_files == sorted(take_files)
    assert render_time_at(fit, 300.0) - render_time_at(fit, 299.0) == pytest.approx(1.0), "1x outside the points"


def test_given_phrases_are_used_as_given(sent):
    clip = delayed(sent, 0.3)
    fit = fit_by_sound(sent, RATE, clip, RATE, vocal_spans=[(0.5, 2.5)])
    assert len(fit["vocal_spans"]) == 1
    assert fit["vocal_spans"][0]["from"] == pytest.approx(0.5)


def test_a_render_stretched_10_percent_reads_rate_1_10():
    sent = sung(6.0, VOCAL_SPANS)
    clip = sung(6.6, VOCAL_SPANS, scale=1.10)
    fit = fit_by_sound(sent, RATE, clip, RATE)
    for phrase in fit["vocal_spans"]:
        assert phrase["rate"] == pytest.approx(1.10, abs=0.03)
        assert phrase["cost"] < 0.2


@pytest.mark.parametrize("unrelated", ["band", "noise"])
def test_unrelated_audio_costs_over_0_45_and_gives_no_points(sent, unrelated):
    other = band(6.0) if unrelated == "band" else np.random.default_rng(1).normal(0, 0.05, 6 * RATE)
    fit = fit_by_sound(sent, RATE, other, RATE)
    assert all(p["cost"] > 0.45 for p in fit["vocal_spans"])
    assert all(p["ties"] == [] for p in fit["vocal_spans"])
    assert fit["map"] == []


def test_another_singer_costs_far_more_than_the_same_sound(sent):
    """A second synthetic singer of the same timbre is not always over 0.45 (it measured 0.39 to 0.63), but it is
    never near the same sound's cost."""
    other = sung(6.0, [(0.3, 2.0), (2.6, 5.6)], voice=1)
    fit = fit_by_sound(sent, RATE, other, RATE)
    assert all(p["cost"] > 0.3 for p in fit["vocal_spans"])


def test_two_phrases_with_different_offsets_are_placed_along_a_path_not_one_offset(sent):
    split = int(2.8 * RATE)
    first = delayed(sent[:split], 0.1)
    second = sent[split:]
    clip = np.concatenate([first, np.zeros(int(0.2 * RATE)), second])
    fit = fit_by_sound(sent, RATE, clip, RATE)
    assert render_time_at(fit, 1.5) == pytest.approx(1.6, abs=0.03)
    assert render_time_at(fit, 4.0) == pytest.approx(4.3, abs=0.03)


def test_a_pause_the_render_inserts_is_reported(sent):
    cut = int(1.5 * RATE)
    clip = np.concatenate([sent[:cut], np.zeros(int(0.3 * RATE)), sent[cut:]])
    fit = fit_by_sound(sent, RATE, clip, RATE)
    rests = fit["added_rests"]
    assert len(rests) == 1
    assert rests[0]["at"] == pytest.approx(1.5, abs=0.06)
    assert rests[0]["seconds"] == pytest.approx(0.3, abs=0.06)


def test_silence_in_the_render_places_nothing(sent):
    fit = fit_by_sound(sent, RATE, np.zeros(6 * RATE), RATE)
    assert fit["map"] == []
