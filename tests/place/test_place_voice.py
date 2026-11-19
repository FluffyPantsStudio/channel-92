"""The gated vocal a render hears, and its quieter compressed copy."""

from __future__ import annotations

import numpy as np
import pytest

from atomic_flix.place.voice import gated_voice, soft_copy, write_voice_pair
from atomic_flix.wav import read_wav

RATE = 48_000


def _steady(seconds: float, rate: int = RATE, env_db: float = -12.0) -> np.ndarray:
    """A voice stem that sounds the whole time (so a gate's edges show)."""
    t = np.arange(int(seconds * rate)) / rate
    tone = np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 660 * t)
    return tone / np.sqrt(np.mean(tone ** 2)) * 10 ** (env_db / 20)


def _lines(seconds: float, spans, rate: int = RATE, env_db: float = -12.0) -> np.ndarray:
    voice = _steady(seconds, rate, env_db)
    t = np.arange(len(voice)) / rate
    mask = np.zeros_like(t)
    for start, end in spans:
        mask[(t >= start) & (t < end)] = 1.0
    return voice * mask


def _rms_db(x: np.ndarray) -> float:
    return 10 * np.log10(np.mean(np.asarray(x, dtype=float) ** 2) + 1e-20)


def test_the_gate_shuts_before_the_next_line_and_the_wav_is_exact(tmp_path):
    voice = _steady(8.0)
    gated = gated_voice(voice, RATE, slice_from=0.0, seconds=8, own=[(2.0, 4.0)], rivals=[(4.1, 6.0)])
    assert gated.samples.shape == (8 * RATE, 2)
    assert gated.rate == 48_000
    assert np.max(np.abs(gated.samples[int(4.08 * RATE):])) == 0.0
    assert np.max(np.abs(gated.samples[int(2.1 * RATE):int(3.9 * RATE)])) > 0.1
    assert np.max(np.abs(gated.samples[:int(1.93 * RATE)])) == 0.0, "opens at most 70 ms early"
    gated_path, soft_path = write_voice_pair(gated, tmp_path / "S02")
    for path in (gated_path, soft_path):
        samples, rate = read_wav(path)
        assert rate == 48_000 and samples.shape == (8 * RATE, 2)
    assert gated_path.name == "S02.voice.wav" and soft_path.name == "S02.voice-soft.wav"


def test_the_gate_spans_first_start_to_last_end_with_short_fades():
    voice = _steady(9.0)
    gated = gated_voice(voice, RATE, slice_from=1.0, seconds=8, own=[(2.0, 3.0), (3.5, 5.0)])
    left = gated.samples[:, 0]
    assert np.max(np.abs(left[int(2.0 * RATE):int(4.0 * RATE)])) > 0.1, "open across the gap between own lines"
    fade = left[int((gated.open_from - 1.0) * RATE):int((gated.open_from - 1.0 + 0.02) * RATE)]
    assert np.abs(fade[0]) < np.max(np.abs(left)) * 0.05 < np.max(np.abs(fade))
    assert gated.open_from == pytest.approx(1.93, abs=0.045)
    assert 5.03 <= gated.open_to <= 5.25


def test_the_tail_follows_the_sound_into_its_release():
    voice = _lines(6.0, [(1.0, 3.12)])
    gated = gated_voice(voice, RATE, slice_from=0.0, seconds=6, own=[(1.0, 3.0)])
    assert gated.open_to == pytest.approx(3.12 + 0.02, abs=0.03)


def test_a_gate_edge_inside_sound_warns_when_no_neighbour_touches():
    voice = _steady(8.0)
    gated = gated_voice(voice, RATE, slice_from=0.0, seconds=8, own=[(2.0, 4.0)])
    assert any("inside sound" in w for w in gated.warnings)
    clean = gated_voice(_lines(8.0, [(2.0, 4.0)]), RATE, slice_from=0.0, seconds=8, own=[(2.0, 4.0)])
    assert clean.warnings == ()


def test_a_slice_with_no_voice_warns():
    gated = gated_voice(np.zeros(8 * RATE), RATE, slice_from=0.0, seconds=8, own=[(2.0, 4.0)])
    assert any("no voice" in w for w in gated.warnings)


def test_another_rate_comes_out_at_48k_and_exact_length():
    voice = _lines(8.0, [(2.0, 4.0)], rate=44_100)
    gated = gated_voice(voice, 44_100, slice_from=0.5, seconds=5, own=[(2.0, 4.0)])
    assert gated.samples.shape == (5 * RATE, 2)


def test_a_slice_past_the_stem_end_is_padded_with_silence():
    voice = _lines(5.0, [(2.0, 4.0)])
    gated = gated_voice(voice, RATE, slice_from=1.0, seconds=6, own=[(2.0, 4.0)])
    assert gated.samples.shape == (6 * RATE, 2)


@pytest.mark.parametrize("env_db", [-8.0, -14.0, -24.0, -36.0])
def test_the_soft_copy_sits_8_db_under_the_gated_copy(env_db):
    gated = gated_voice(_lines(8.0, [(1.0, 3.0), (3.4, 6.0)], env_db=env_db), RATE, slice_from=0.0,
                        seconds=8, own=[(1.0, 3.0), (3.4, 6.0)])
    soft = soft_copy(gated.samples, RATE)
    assert soft.shape == gated.samples.shape
    vocal_on = slice(int(1.1 * RATE), int(5.9 * RATE))
    assert _rms_db(gated.samples[vocal_on]) - _rms_db(soft[vocal_on]) == pytest.approx(8.0, abs=2.0)


def test_the_soft_copy_narrows_the_gap_between_loud_and_quiet():
    rate = RATE
    loud = _steady(2.0, env_db=-6.0)
    quiet = _steady(2.0, env_db=-26.0)
    voice = np.concatenate([loud, quiet])[:, None].repeat(2, axis=1)
    soft = soft_copy(voice, rate)
    before = _rms_db(voice[:2 * rate]) - _rms_db(voice[2 * rate + 4800:])
    after = _rms_db(soft[:2 * rate]) - _rms_db(soft[2 * rate + 4800:])
    assert before == pytest.approx(20.0, abs=0.1)
    assert after < 8.0
