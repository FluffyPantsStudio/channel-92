import json

import numpy as np
import pytest

from atomic_flix.timing import time_lines, write_timing
from atomic_flix.timing.labels import Label
from atomic_flix.timing.lyric import parse_lyric

from voice_synth import RATE, voice

THREE = parse_lyric("one two three four\none two three four five six\nseven eight nine ten\n")
BURSTS = [(1.0, 2.0, -14.0), (3.0, 4.5, -14.0), (4.6, 6.0, -14.0)]


def _by_id(result):
    return {ln.id: ln for ln in result.lines}


def _labels_for_three(second_line_start):
    words = [("one", 1.0, 1.2), ("two", 1.2, 1.5), ("three", 1.5, 1.7), ("four", 1.7, 1.95),
             ("one", second_line_start, 3.3), ("two", 3.3, 3.5), ("three", 3.5, 3.7), ("four", 3.7, 3.9),
             ("five", 3.9, 4.1), ("six", 4.1, 4.45),
             ("seven", 4.6, 4.9), ("eight", 4.9, 5.2), ("nine", 5.2, 5.5), ("ten", 5.5, 5.9)]
    return [Label(t, a, b, 0.9) for t, a, b in words]


def test_starts_are_within_thirty_ms_and_the_legato_pair_splits_near_the_join():
    result = time_lines(THREE, voice(7.0, BURSTS), RATE)
    lines = _by_id(result)
    assert lines["v01"].start == pytest.approx(1.0, abs=0.03)
    assert lines["v02"].start == pytest.approx(3.0, abs=0.03)
    assert lines["v01"].end == pytest.approx(2.0, abs=0.05)
    assert lines["v02"].end == pytest.approx(4.55, abs=0.1)
    assert lines["v03"].start == pytest.approx(4.55, abs=0.1)
    assert result.unplaced == ()
    assert all(ln.provenance == "guess" for ln in result.lines)


def test_an_early_label_does_not_move_the_start_but_is_flagged():
    result = time_lines(THREE, voice(7.0, BURSTS), RATE, labels=_labels_for_three(1.8))
    line = _by_id(result)["v02"]
    assert line.start == pytest.approx(3.0, abs=0.03)
    assert line.marked_start == pytest.approx(1.8)
    assert any("label 1.20 s early" in f for f in line.flags)
    assert line.provenance == "level"
    assert result.marked


def test_labels_say_which_words_fall_in_each_line():
    result = time_lines(THREE, voice(7.0, BURSTS), RATE, labels=_labels_for_three(3.0))
    lines = _by_id(result)
    assert [w["text"] for w in lines["v03"].words] == ["seven", "eight", "nine", "ten"]
    assert not any("label" in f for f in lines["v02"].flags)


def test_a_breath_twenty_db_down_is_no_line():
    audio = voice(7.0, BURSTS + [(2.3, 2.7, -34.0)])
    result = time_lines(THREE, audio, RATE)
    starts = [ln.start for ln in result.lines]
    assert not any(2.2 < s < 2.8 for s in starts)
    assert _by_id(result)["v02"].start == pytest.approx(3.0, abs=0.03)


def test_a_fix_wins():
    result = time_lines(THREE, voice(7.0, BURSTS), RATE, fixes={"v02": [3.1, 4.4]})
    line = _by_id(result)["v02"]
    assert (line.start, line.end) == (3.1, 4.4)
    assert line.provenance == "fixed"


def test_lines_left_without_a_phrase_are_reported_as_unplaced():
    lyric = parse_lyric("one two three four\none two three four five six\nseven eight nine ten\nlast one here\n")
    result = time_lines(lyric, voice(7.0, BURSTS), RATE)
    assert len(result.unplaced) == 1
    missing = _by_id(result)[result.unplaced[0]]
    assert missing.start is None and missing.end is None
    assert "no time" in missing.flags


def test_a_pause_inside_a_line_is_a_gap():
    lyric = parse_lyric("one two three four five six seven eight nine\n")
    result = time_lines(lyric, voice(4.0, [(1.0, 1.6, -14.0), (1.9, 2.6, -14.0)]), RATE)
    line = result.lines[0]
    assert line.start == pytest.approx(1.0, abs=0.03)
    assert line.end == pytest.approx(2.6, abs=0.05)
    assert len(line.gaps) == 1
    assert line.gaps[0][0] == pytest.approx(1.6, abs=0.05)
    assert line.gaps[0][1] == pytest.approx(1.9, abs=0.05)


def test_repeats_written_out_get_their_own_phrases():
    lyric = parse_lyric("ride the magic tub\nfloat away on hurt and learn to fly\nride the magic tub\n")
    audio = voice(10.0, [(1.0, 2.0, -14.0), (3.0, 5.4, -14.0), (6.5, 7.5, -14.0)])
    lines = _by_id(time_lines(lyric, audio, RATE))
    assert lines["v01"].start == pytest.approx(1.0, abs=0.03)
    assert lines["v03"].start == pytest.approx(6.5, abs=0.03)


def test_a_wordless_line_is_timed_like_any_other():
    lyric = parse_lyric("aa-h-aaaaa-aha-aaaaaah\nshe slipped out the back door\n")
    audio = voice(9.0, [(1.0, 4.5, -14.0), (5.5, 7.0, -14.0)])
    lines = _by_id(time_lines(lyric, audio, RATE))
    assert lines["v01"].start == pytest.approx(1.0, abs=0.03)
    assert lines["v02"].start == pytest.approx(5.5, abs=0.03)


def test_choir_lines_come_from_the_choir_stem_and_trim_the_lead():
    lyric = parse_lyric("ride the magic tub\n(magic tub)\nmade of salty tears\n")
    lead = voice(8.0, [(1.0, 2.5, -14.0), (3.0, 4.8, -14.0)])
    choir = voice(8.0, [(2.6, 3.4, -16.0)])
    lines = _by_id(time_lines(lyric, lead, RATE, choir=choir))
    assert lines["v02"].part == "choir"
    assert lines["v02"].start == pytest.approx(2.6, abs=0.03)
    assert lines["v03"].start == pytest.approx(3.4, abs=0.05)


def test_choir_lines_without_a_choir_stem_are_unplaced():
    lyric = parse_lyric("ride the magic tub\n(magic tub)\n")
    result = time_lines(lyric, voice(4.0, [(1.0, 2.5, -14.0)]), RATE)
    assert result.unplaced == ("v02",)


def test_output_file_is_utf8_json_in_the_spec_shape(tmp_path):
    lyric = parse_lyric("Señorita, ça va\n")
    result = time_lines(lyric, voice(3.0, [(1.0, 2.0, -14.0)]), RATE)
    path = write_timing(result, tmp_path / "analysis" / "voice-lines.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) >= {"sung_db", "floor_db", "marked", "lines", "unplaced"}
    line = data["lines"][0]
    assert set(line) >= {"id", "part", "text", "start", "end", "marked_start", "gaps", "provenance", "flags"}
    assert line["text"] == "Señorita, ça va"
    assert "Señorita" in path.read_text(encoding="utf-8")


def test_quiet_line_is_eighteen_db_under_the_working_level():
    result = time_lines(THREE, voice(7.0, BURSTS), RATE)
    assert result.floor_db == pytest.approx(result.sung_db - 18.0)
    assert -15.5 < result.sung_db < -12.5


def test_stereo_voice_is_accepted():
    mono = voice(7.0, BURSTS)
    result = time_lines(THREE, np.stack([mono, mono], axis=1), RATE)
    assert _by_id(result)["v02"].start == pytest.approx(3.0, abs=0.03)
