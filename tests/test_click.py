import json

import numpy as np
import pytest

from atomic_flix.wav import read_wav, save_wav

RATE = 44100


@pytest.fixture
def click(tool):
    return tool("click")


def _beats_file(tmp_path, beats, key="beats"):
    path = tmp_path / "beats.json"
    path.write_text(json.dumps({key: beats}), encoding="utf-8")
    return path


def _peak(sig, t, span=0.04):
    a = int(t * RATE)
    return float(np.max(np.abs(sig[a:a + int(span * RATE)])))


def _pitch(sig, t, span=0.04):
    a = int(t * RATE)
    seg = sig[a:a + int(span * RATE)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), n=1 << 16))
    return float(np.fft.rfftfreq(1 << 16, 1 / RATE)[np.argmax(spec)])


def test_ones_are_loud_and_high(click):
    beats = [0.5 + 0.5 * i for i in range(16)]
    sig = click.render_clicks(beats, phase=2, rate=RATE)
    ones = beats[2::4]
    rivals = [t for i, t in enumerate(beats) if i % 4 != 2]
    assert min(_peak(sig, t) for t in ones) > 2.0 * max(_peak(sig, t) for t in rivals)
    for t in ones:
        assert _pitch(sig, t) == pytest.approx(click.COUNT_HZ[0], rel=0.01)
    for i, t in enumerate(beats):
        count = (i - 2) % 4
        assert _pitch(sig, t) == pytest.approx(click.COUNT_HZ[count], rel=0.01)


def test_counts_have_distinct_pitches(click):
    assert len(set(click.COUNT_HZ)) == 4


def test_silent_between_and_before_clicks(click):
    beats = [1.0, 1.5, 2.0, 2.5]
    sig = click.render_clicks(beats, phase=0, rate=RATE)
    assert np.max(np.abs(sig[: int(0.99 * RATE)])) == 0.0
    assert np.max(np.abs(sig[int(1.3 * RATE):int(1.49 * RATE)])) < 1e-3
    assert len(sig) == int(round((2.5 + click.TAIL_S) * RATE))


def test_click_lands_on_the_beat(click):
    sig = click.render_clicks([1.234], phase=0, rate=RATE)
    first = int(np.argmax(np.abs(sig) > 0.01))
    assert abs(first / RATE - 1.234) < 0.001


def test_cli_writes_mono_44100(click, tmp_path):
    beats = _beats_file(tmp_path, [0.2, 0.7, 1.2, 1.7, 2.2])
    out = tmp_path / "out" / "click.wav"
    assert click.main([str(beats), "--phase", "1", "--out", str(out)]) == 0
    data, rate = read_wav(out)
    assert rate == RATE and data.shape[1] == 1
    assert _peak(data[:, 0], 0.7) > 2.0 * _peak(data[:, 0], 0.2)


def test_mix_over_music_at_gain(click, tmp_path):
    music_rate = 22050
    n = music_rate * 3
    tone = 0.5 * np.sin(2 * np.pi * 200 * np.arange(n) / music_rate)
    music = tmp_path / "song.wav"
    save_wav(music, np.stack([tone, tone], axis=1), music_rate)
    beats = _beats_file(tmp_path, [0.5, 1.0])
    out = tmp_path / "mix.wav"
    assert click.main([str(beats), "--phase", "0", "--out", str(out), "--over", str(music), "--gain", "-6"]) == 0
    data, rate = read_wav(out)
    assert rate == RATE
    assert abs(len(data) - 3 * RATE) <= 2
    quiet_part = data[int(1.6 * RATE):int(2.6 * RATE), 0]
    assert np.max(np.abs(quiet_part)) == pytest.approx(0.5 * 10 ** (-6 / 20), rel=0.03)


def test_mix_never_clips(click):
    music = np.ones(RATE * 2)
    sig = click.render_clicks([0.5, 1.0], phase=0, rate=RATE)
    mixed = click.mix_over(sig, music, music_gain_db=0.0)
    assert np.max(np.abs(mixed)) <= click.PEAK_LIMIT + 1e-9


def test_bad_inputs_exit_2(click, tmp_path, capsys):
    good = _beats_file(tmp_path, [0.5, 1.0])
    assert click.main([str(good), "--phase", "4", "--out", str(tmp_path / "a.wav")]) == 2
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"ticks": [0.5]}), encoding="utf-8")
    assert click.main([str(other), "--phase", "0", "--out", str(tmp_path / "b.wav")]) == 2
    assert "beats" in capsys.readouterr().err
    unsorted = _beats_file(tmp_path, [1.0, 0.5])
    assert click.main([str(unsorted), "--phase", "0", "--out", str(tmp_path / "c.wav")]) == 2


def test_key_option_reads_another_list(click, tmp_path):
    path = _beats_file(tmp_path, [0.5, 1.0], key="grid")
    out = tmp_path / "k.wav"
    assert click.main([str(path), "--key", "grid", "--phase", "0", "--out", str(out)]) == 0
