"""Regression on the first film (The Girl In The Magic Tub): run with `pytest -m first_film`.

Known (fixtures/first-film/TRUTH.txt): the bar's one is on beats whose index
mod 4 is 0 in build/beats.json; counts 1 and 3 are the snare beats, the
mistake that cost the first film a reshoot. The film has no drum stem; the
band stem (rest.wav) carries the drums.
"""

import json
import os
from pathlib import Path

import numpy as np
import pytest

from atomic_flix.barmap import beat_grid, find_bar_one, pulse
from atomic_flix.barmap.spectral import spectra_of
from atomic_flix.wav import read_wav

FIRST_FILM = Path(__file__).resolve().parents[2] / "fixtures" / "first-film"

pytestmark = pytest.mark.first_film


@pytest.fixture(scope="module", autouse=True)
def _only_when_asked(request):
    """Skip unless asked for (`-m first_film` or AF_FIRST_FILM=1) and the fixture pack is here."""
    asked = "first_film" in (request.config.getoption("markexpr") or "") or os.environ.get("AF_FIRST_FILM") == "1"
    if not asked:
        pytest.skip("slow; run with -m first_film")
    if not (FIRST_FILM / "audio" / "lead.wav").exists():
        pytest.skip("fixtures/first-film is not on this machine")


@pytest.fixture(scope="module")
def film():
    rest, rate = read_wav(FIRST_FILM / "audio" / "rest.wav")
    old = np.array(json.loads((FIRST_FILM / "build" / "beats.json").read_text(encoding="utf-8"))["beats"])
    return {"rest": rest, "rate": rate, "spectra": spectra_of(rest, rate), "old": old}


def _old_phase(beats, phase, old):
    """The old grid's phase for a phase given on another grid, matched by time."""
    return int(np.argmin(np.abs(old - beats[phase]))) % 4


def test_beats_match_the_old_grid(film):
    grid = beat_grid(film["spectra"])
    miss = np.array([np.min(np.abs(grid.beats - t)) for t in film["old"]])
    assert np.mean(miss <= 0.030) >= 0.95, f"{np.mean(miss <= 0.030):.3f} within 30 ms"
    assert np.median(miss) <= 0.010
    assert abs(len(grid.beats) - len(film["old"])) <= 2


def test_snare_phases_are_rejected_by_more_than_three_z(film):
    result = find_bar_one(film["old"], film["spectra"], film["spectra"])
    assert result.pair_margin > 3.0
    if result.status == "decided":
        assert result.downbeat_slot == 0
    else:
        assert result.status == "needs_click_check"
        assert result.one_or_three == (0, 2)


def test_our_own_grid_lands_the_one_on_the_same_beats(film):
    grid = beat_grid(film["spectra"])
    result = find_bar_one(grid.beats, film["spectra"], film["spectra"])
    assert result.pair_margin > 3.0
    phases = [result.downbeat_slot] if result.downbeat_slot is not None else list(result.one_or_three)
    assert 0 in [_old_phase(grid.beats, p, film["old"]) for p in phases]


def test_cut_points_never_fall_on_snare_beats(film):
    song, rate = read_wav(FIRST_FILM / "audio" / "song.wav")
    lead, lead_rate = read_wav(FIRST_FILM / "audio" / "lead.wav")
    out = pulse(None, film["rate"], band=film["rest"], mix=song, vocal=lead, vocal_rate=lead_rate)
    cuts = np.array(out.to_dict()["cut_beats"])
    old = film["old"]
    nearest = np.array([np.argmin(np.abs(old - t)) for t in cuts])
    close = np.abs(old[nearest] - cuts) <= 0.030
    assert np.all(nearest[close] % 2 == 0)
    assert close.mean() >= 0.95
