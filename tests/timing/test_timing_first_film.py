"""Regression on the first film (The Girl In The Magic Tub): run with `pytest -m first_film`.

The reference is the film's final line table (56 lines, 15 of them set by
hand). Its unfixed rows came from the earlier tools and were never checked by
ear, so agreement is a floor to hold, not a target to chase. Some hand-set
starts sit where the stem's level gives no sign (v26 at 125.00, heard; v30,
v50 and v56 set to the label start), so no level-based method reaches them.

Hold-out: the costs were set looking only at the first two thirds of the
song (v01 to v37). The last third (v38 to v56) was looked at once, after.

The roadmap gates (40 of 56 within 0.10 s with labels; 30 of 56 within
0.25 s from the stem alone) are not met yet; they are kept here as strict
expected failures so that meeting them shows up.
"""

import os

import numpy as np
import pytest

from atomic_flix.timing import parse_lyric, time_lines, timing_report
from atomic_flix.wav import read_wav

import first_film_data as film
from first_film_data import FIRST_FILM

pytestmark = pytest.mark.first_film

CLOSE_S = 0.10
NEAR_S = 0.25
HOLD_OUT = slice(37, 56)


@pytest.fixture(scope="module", autouse=True)
def _only_when_asked(request):
    """Skip unless asked for (`-m first_film` or AF_FIRST_FILM=1) and the fixture pack is here."""
    asked = "first_film" in (request.config.getoption("markexpr") or "") or os.environ.get("AF_FIRST_FILM") == "1"
    if not asked:
        pytest.skip("slow; run with -m first_film")
    if not (FIRST_FILM / "audio" / "lead.wav").exists():
        pytest.skip("fixtures/first-film is not on this machine")


@pytest.fixture(scope="module")
def stems():
    lead, rate = read_wav(film.FIRST_FILM / "audio" / "lead.wav")
    group, group_rate = read_wav(film.FIRST_FILM / "audio" / "group.wav")
    return lead, rate, group, group_rate


@pytest.fixture(scope="module")
def marked(stems):
    lead, rate, group, group_rate = stems
    lyric = parse_lyric(film.lyric_text())
    return time_lines(lyric, lead, rate, labels=film.labels(), choir=group, choir_rate=group_rate)


@pytest.fixture(scope="module")
def stem_alone(stems):
    lead, rate, group, group_rate = stems
    return time_lines(parse_lyric(film.lyric_text()), lead, rate, choir=group, choir_rate=group_rate)


def _start_errors(result):
    return np.array([abs(ln.start - t0) if ln.start is not None else np.inf
                     for ln, (t0, _) in zip(result.lines, film.truth())])


def _count(result, limit, part=slice(None)):
    return int((_start_errors(result)[part] <= limit).sum())


def test_every_line_is_timed(marked):
    assert len(marked.lines) == 56
    assert marked.unplaced == ()


def test_starts_agree_with_the_final_table(marked):
    assert _count(marked, CLOSE_S) >= 34, f"{_count(marked, CLOSE_S)} of 56 starts within {CLOSE_S} s"
    assert _count(marked, NEAR_S) >= 43, f"{_count(marked, NEAR_S)} of 56 starts within {NEAR_S} s"


def test_the_held_out_last_third_agrees_as_well(marked):
    assert _count(marked, CLOSE_S, HOLD_OUT) >= 11
    assert _count(marked, NEAR_S, HOLD_OUT) >= 13


def test_every_line_more_than_a_quarter_second_off_is_flagged(marked):
    errors = _start_errors(marked)
    silent = [ln.id for ln, err in zip(marked.lines, errors) if err > NEAR_S and not ln.flags]
    assert silent == []


@pytest.mark.xfail(strict=True, reason="roadmap gate not met: 34 of 56 within 0.10 s")
def test_roadmap_gate_forty_within_a_tenth(marked):
    assert _count(marked, CLOSE_S) >= 40


def test_stem_alone_does_not_carry_an_early_error_to_the_end(stem_alone):
    assert _count(stem_alone, NEAR_S) >= 23
    assert _count(stem_alone, NEAR_S, HOLD_OUT) >= 12


def test_stem_alone_flags_nearly_every_line_it_has_wrong(stem_alone):
    errors = _start_errors(stem_alone)
    silent = [ln.id for ln, err, by_hand in zip(stem_alone.lines, errors, film.hand_fixed())
              if err > NEAR_S and not ln.flags and not by_hand]
    assert len(silent) <= 1, silent


@pytest.mark.xfail(strict=True, reason="roadmap gate not met: 23 of 56 within 0.25 s from the stem alone")
def test_roadmap_gate_thirty_near_from_the_stem_alone(stem_alone):
    assert _count(stem_alone, NEAR_S) >= 30


def test_report_has_a_row_per_line(marked):
    rows = [row for row in timing_report(marked).splitlines() if row.startswith("v")]
    assert len(rows) == 56


def test_quiet_line_sits_eighteen_db_under_the_working_level(marked):
    assert marked.floor_db == pytest.approx(marked.sung_db - 18.0)
