"""The global line-to-phrase assignment: one error must not shift the rest of the song.

Every stem here is synthetic. Lines are made of one-syllable words, so the
expected length of a line is its word count times the song's pace, and the
bursts are cut to that pace (0.3 s a syllable).
"""

import pytest

from atomic_flix.timing import time_lines, timing_report
from atomic_flix.timing.lyric import parse_lyric

from voice_synth import RATE, voice

WORDS = ("red blue green gold pink gray black white "
         "sun moon star sky rain snow wind fire "
         "cat dog fox owl bat hen cow pig "
         "oak elm ash fir yew bay box pine "
         "salt rope ship sail mast deck hull keel "
         "bread milk cheese jam tea rice corn bean "
         "hat coat scarf shoe sock belt ring pin "
         "road path lane street bridge gate wall door").split()
PACE = 0.3


def _lyric(count: int, words_per_line: int = 8) -> list:
    rows = [" ".join(WORDS[i * words_per_line:(i + 1) * words_per_line]) for i in range(count)]
    return parse_lyric("\n".join(rows) + "\n")


def _by_id(result):
    return {ln.id: ln for ln in result.lines}


def _cascade_case():
    """Eight lines of 8 syllables (2.4 s); lines 1 and 2 run together with no dip at all."""
    bursts = [(1.0, 5.8, -14.0)]
    start = 6.8
    for _ in range(6):
        bursts.append((start, start + 2.4, -14.0))
        start += 3.4
    return _lyric(8), voice(start + 1.0, bursts)


def test_a_missed_legato_join_does_not_shift_the_lines_after_it():
    lyric, audio = _cascade_case()
    lines = _by_id(time_lines(lyric, audio, RATE))
    assert lines["v01"].start == pytest.approx(1.0, abs=0.03)
    for k, expected in enumerate([6.8, 10.2, 13.6, 17.0, 20.4, 23.8], start=3):
        assert lines[f"v{k:02d}"].start == pytest.approx(expected, abs=0.03)


def test_the_line_split_out_of_a_join_is_placed_near_its_share_and_flagged():
    lyric, audio = _cascade_case()
    lines = _by_id(time_lines(lyric, audio, RATE))
    split = lines["v02"]
    assert split.start == pytest.approx(3.4, abs=0.5)
    assert split.confidence < lines["v03"].confidence
    assert any("uncertain" in f for f in split.flags)


def test_lines_after_clear_pauses_are_confident_and_not_flagged():
    lyric = _lyric(3, 6)
    audio = voice(9.0, [(1.0, 2.8, -14.0), (3.8, 5.6, -14.0), (6.6, 8.4, -14.0)])
    result = time_lines(lyric, audio, RATE)
    for line in result.lines:
        assert line.confidence >= 0.8
        assert not any("uncertain" in f for f in line.flags)


def test_an_echo_not_in_the_lyric_is_skipped_without_shifting_later_lines():
    lyric = _lyric(4, 6)
    audio = voice(15.0, [(1.0, 2.8, -14.0), (4.0, 5.8, -14.0), (6.3, 7.1, -14.0),
                         (8.2, 10.0, -14.0), (11.2, 13.0, -14.0)])
    lines = _by_id(time_lines(lyric, audio, RATE))
    assert lines["v03"].start == pytest.approx(8.2, abs=0.03)
    assert lines["v04"].start == pytest.approx(11.2, abs=0.03)
    assert not any(6.2 < ln.start < 7.2 for ln in lines.values())


def test_a_doubled_line_sung_legato_is_split_between_its_two_copies():
    lyric = parse_lyric("ride the big tub\nride the big tub\nmade of salt and tears and dreams\n")
    audio = voice(9.0, [(1.0, 3.4, -14.0), (4.4, 6.5, -14.0)])
    lines = _by_id(time_lines(lyric, audio, RATE))
    assert lines["v01"].start == pytest.approx(1.0, abs=0.03)
    assert lines["v02"].start == pytest.approx(2.2, abs=0.35)
    assert lines["v03"].start == pytest.approx(4.4, abs=0.03)


def test_a_long_held_note_stays_one_line():
    lyric = _lyric(4, 6)
    audio = voice(16.0, [(1.0, 6.5, -14.0), (7.5, 9.3, -14.0), (10.3, 12.1, -14.0), (13.1, 14.9, -14.0)])
    lines = _by_id(time_lines(lyric, audio, RATE))
    for key, expected in (("v01", 1.0), ("v02", 7.5), ("v03", 10.3), ("v04", 13.1)):
        assert lines[key].start == pytest.approx(expected, abs=0.03)
    assert lines["v01"].end == pytest.approx(6.5, abs=0.05)


def test_report_lists_every_line_with_start_end_confidence_and_why():
    lyric, audio = _cascade_case()
    result = time_lines(lyric, audio, RATE)
    text = timing_report(result)
    rows = [row for row in text.splitlines() if row.startswith("v")]
    assert len(rows) == len(result.lines)
    first = _by_id(result)["v01"]
    assert f"{first.start:.2f}" in rows[0] and f"{first.end:.2f}" in rows[0]
    assert f"{first.confidence:.2f}" in rows[0]
    assert "uncertain" in rows[1]
    assert all(ln.why for ln in result.lines)


def test_confidence_and_why_are_in_the_json():
    lyric = _lyric(2, 6)
    result = time_lines(lyric, voice(7.0, [(1.0, 2.8, -14.0), (3.8, 5.6, -14.0)]), RATE)
    row = result.to_dict()["lines"][0]
    assert 0.0 <= row["confidence"] <= 1.0
    assert isinstance(row["why"], str) and row["why"]
