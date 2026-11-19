"""Free cuts between cutaways snap to bar lines only where every shot keeps at least MIN_SHOT seconds."""

from __future__ import annotations

import pytest

from atomic_flix.plan import PlanError, Pulse, ShotSpec, plan_cuts
from atomic_flix.plan.cuts import MIN_SHOT


def sparse_pulse(stop=20.0):
    """A beat every second, so bar lines (ones and threes) fall every two seconds: 0, 2, 4, ..."""
    return Pulse(beats=tuple(float(k) for k in range(int(stop) + 1)), downbeat_slot=0)


def cutaways(count):
    return [ShotSpec(key=f"N{n:02d}", kind="cutaway") for n in range(1, count + 1)]


def _lengths(cuts, ends_at):
    times = [c.at for c in cuts] + [ends_at]
    return [b - a for a, b in zip(times, times[1:])]


def test_snapping_never_leaves_a_free_shot_under_the_minimum():
    ends_at = 5.2
    cuts = plan_cuts(cutaways(3), {}, sparse_pulse(), ends_at=ends_at)
    assert min(_lengths(cuts, ends_at)) >= MIN_SHOT - 1e-6, [(c.key, c.at, c.grid) for c in cuts]


def test_a_free_cut_keeps_its_bar_line_when_the_minimum_allows():
    ends_at = 5.2
    cuts = plan_cuts(cutaways(3), {}, sparse_pulse(), ends_at=ends_at)
    assert cuts[1].at == pytest.approx(2.0) and cuts[1].grid in ("one", "three")


def test_cutaways_that_cannot_all_have_the_minimum_are_refused():
    with pytest.raises(PlanError, match="1.6"):
        plan_cuts(cutaways(3), {}, sparse_pulse(), ends_at=4.7)
