import numpy as np
import pytest

from atomic_flix.barmap.swells import find_swells

RATE = 22050


def _sections(levels, seconds_each):
    """Noise sections at given linear amplitudes, back to back."""
    rng = np.random.default_rng(3)
    parts = [amp * rng.standard_normal(int(seconds_each * RATE)) for amp in levels]
    return np.concatenate(parts)


def test_a_jump_in_level_is_an_accent_snapped_to_the_nearest_beat():
    audio = _sections([0.02, 0.3], 6.0)
    beats = np.arange(0.03, 12.0, 0.5)
    result = find_swells(audio, RATE, beats)
    assert len(result.swells) == 1
    accent = result.swells[0]
    assert accent["t"] == pytest.approx(6.03, abs=0.001)
    assert 0.22 < accent["punch"] <= 1.0


def test_small_changes_are_not_accents():
    audio = _sections([0.2, 0.22, 0.2], 5.0)
    assert find_swells(audio, RATE, np.arange(0.0, 15.0, 0.5)).swells == ()


def test_accents_keep_two_seconds_apart():
    audio = _sections([0.01, 0.15, 0.4], 1.2)
    result = find_swells(audio, RATE, np.arange(0.0, 3.6, 0.25))
    times = [a["t"] for a in result.swells]
    assert all(b - a >= 2.0 for a, b in zip(times, times[1:]))


def test_parts_between_accents_carry_their_voiced_share():
    audio = _sections([0.02, 0.3], 6.0)
    vocal = np.zeros_like(audio)
    vocal[int(7 * RATE):int(10 * RATE)] = 0.2 * np.sin(2 * np.pi * 220 * np.arange(3 * RATE) / RATE)
    result = find_swells(audio, RATE, np.arange(0.0, 12.0, 0.5), vocal=vocal, vocal_rate=RATE)
    assert [(p["from"], p["to"]) for p in result.parts] == [(0.0, 6.0), (6.0, 12.0)]
    assert result.parts[0]["vocal_on"] == pytest.approx(0.0, abs=0.01)
    assert result.parts[1]["vocal_on"] == pytest.approx(0.5, abs=0.05)


def test_without_a_vocal_the_voiced_share_is_unknown():
    audio = _sections([0.02, 0.3], 6.0)
    result = find_swells(audio, RATE, np.arange(0.0, 12.0, 0.5))
    assert all(p["vocal_on"] is None for p in result.parts)
