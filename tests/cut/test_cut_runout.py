"""A take that runs out is slowed to 0x, and no window may pass a take played slower than 0.97x."""

from __future__ import annotations

import pytest

from atomic_flix.cut.audit import TakeInfo, audit_edit
from atomic_flix.cut.edit import Cut, Edit, Placed
from atomic_flix.cut.rate import RATE_WINDOWS_S, slow_tolerance

TAKES = {"A": TakeInfo(fps=24.0, frames=96, width=192, height=108)}
PULSE = {"beats": [0.5 * i for i in range(40)], "downbeat_slot": 0}


def _audit(ties, end, frames=96):
    edit = Edit(cuts=(Cut("A", 0.0),), takes={"A": Placed("A", "a", ties)}, fps=24, size=(192, 108), song=None,
                start=0.0, end=end, pulse=PULSE)
    return audit_edit(edit, take_info={"A": TakeInfo(fps=24.0, frames=frames, width=192, height=108)})


def test_a_take_that_runs_out_and_holds_its_last_frame_is_an_error():
    account = _audit(((0.0, 0.5),), end=3.0, frames=48)
    assert account.rows[0]["held_at_end"] > 0
    assert any("holds its last frame" in e and "0x" in e for e in account.errors), account.errors
    assert not any("holds its last frame" in w for w in account.warnings)


@pytest.mark.parametrize("window", [0.1, 0.25, 0.5, 0.8, 1.0, 1.33] + list(RATE_WINDOWS_S))
def test_no_window_tolerates_more_than_three_percent(window):
    assert slow_tolerance(window) <= 0.03 + 1e-12


def test_a_short_shot_at_096x_is_refused():
    account = _audit(((0.0, 0.5), (0.8, 0.5 + 0.8 * 0.96)), end=0.8)
    assert account.rows[0]["slower"] is True, account.rows[0]
    assert any("slower than 1x" in e for e in account.errors)


def test_one_second_at_0965x_inside_a_longer_shot_is_refused():
    ties = ((0.0, 0.5), (1.0, 1.5), (2.0, 2.5 - 0.035), (4.0, 4.5 - 0.035))
    account = _audit(ties, end=4.0)
    row = account.rows[0]
    assert row["slowest_rate"] == pytest.approx(0.965, abs=0.002)
    assert row["slower"] is True
