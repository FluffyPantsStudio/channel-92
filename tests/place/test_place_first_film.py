"""Regression on the first film: the latest take of every sung shot places on the lead vocal by its sound.

Our record for these renders: cost 0.02 to 0.09 against the exact soft copy each one heard. Here the sent audio is
rebuilt from the ungated, uncompressed lead stem (the windows' times are not in the fixture), which costs a little
more on a few takes, so the bar is: every phrase under 0.2 (a usable placement), nine in ten at 0.09 or lower.
"""

from __future__ import annotations

import numpy as np
import pytest

from atomic_flix.place.check import check_fit
from first_film_env import UNSET, flix_root
from first_film_takes import Song, available, place_take, sung_takes

pytestmark = [pytest.mark.first_film, pytest.mark.skipif(flix_root() is None, reason=UNSET),
              pytest.mark.skipif(not available(), reason="the first film's takes or ffmpeg are not here")]


@pytest.fixture(scope="module")
def placed():
    song = Song.load()
    return [place_take(song, video) for video in sung_takes(latest_only=True)]


def test_every_sung_shot_has_a_take_to_place(placed):
    assert len(placed) >= 20


def test_every_phrase_places_and_nine_in_ten_at_0_09_or_lower(placed):
    worst = np.array([row["worst"] for row in placed])
    assert np.all(worst < 0.2), [row["take"] for row in placed if row["worst"] >= 0.2]
    assert np.mean(worst <= 0.09) >= 0.9


def test_no_take_is_flagged_for_rate_or_drift(placed):
    for row in placed:
        ids = {flag["id"] for flag in check_fit(row["fit"])}
        assert not ids & {"rate", "drift", "unplaced", "cost"}, (row["take"], ids)
