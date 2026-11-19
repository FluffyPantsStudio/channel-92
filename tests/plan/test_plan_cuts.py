"""Cut planning: cuts go on the bar first, every window is derived from them (core spec, stage 3)."""

import pytest

from atomic_flix.plan import Line, Pulse, ShotSpec, plan_cuts, plan_film


def grid_pulse(start=0.0, stop=40.0, step=0.5, one_offset=0):
    """Beats every `step` s; the one on beats whose index mod 4 is `one_offset`."""
    beats = [round(start + k * step, 3) for k in range(int((stop - start) / step) + 1)]
    return Pulse(beats=tuple(beats), downbeat_slot=one_offset)


def line(key, start, end, text="la la", gaps=()):
    return Line(key=key, part="lead", text=text, start=start, end=end, gaps=tuple(gaps))


def vocal(key, *sings, **kw):
    return ShotSpec(key=key, kind="vocal", sings=tuple(sings), **kw)


def cutaway(key, **kw):
    return ShotSpec(key=key, kind="cutaway", **kw)


def test_pulse_ones_and_threes():
    pulse = grid_pulse(0, 4, 0.5, one_offset=0)
    assert pulse.ones == (0.0, 2.0, 4.0)
    assert pulse.thirds == (1.0, 3.0)
    assert pulse.grid_of(2.0) == "one"
    assert pulse.grid_of(3.0) == "three"
    assert pulse.grid_of(2.5) == "beat"
    assert pulse.grid_of(2.7) == "off"


def test_enters_on_the_one_before_her_first_sound():
    # spec: first sound 10.4, ones at 10.0 and 12.0: enters 10.0, slice from 9.70
    lines = [line("v01", 10.4, 12.6)]
    shots = [cutaway("N01"), vocal("S01", "v01")]
    plan = plan_film(shots, lines, grid_pulse(), ends_at=20.0)
    assert plan.cut_of("S01").at == pytest.approx(10.0)
    assert plan.cut_of("S01").grid == "one"
    assert plan.tasks["S01"]["slice_start"] == pytest.approx(9.70)


def test_enters_on_the_three_just_after_her_first_sound():
    # spec: first sound 10.95, a three at 11.0: enters 11.0
    lines = [line("v01", 10.95, 13.6)]
    shots = [cutaway("N01"), vocal("S01", "v01")]
    cuts = plan_cuts(shots, {x.key: x for x in lines}, grid_pulse(), ends_at=20.0)
    assert cuts[1].at == pytest.approx(11.0)
    assert cuts[1].grid == "three"


def test_first_cut_is_the_lead():
    lines = [line("v01", 10.4, 12.6)]
    plan = plan_film([cutaway("N01"), vocal("S01", "v01")], lines, grid_pulse(), ends_at=20.0)
    assert plan.cuts[0].at == pytest.approx(0.25)
    assert plan.cuts[0].grid == "lead"


def test_vocal_to_vocal_cuts_early_in_the_silence():
    lines = [line("v01", 4.4, 8.2), line("v02", 10.3, 13.0)]
    shots = [cutaway("N01"), vocal("S01", "v01"), vocal("S02", "v02")]
    plan = plan_film(shots, lines, grid_pulse(), ends_at=20.0)
    cut = plan.cut_of("S02")
    # silence from 8.2 to 10.3: the earliest bar line from 0.3 s before her last sound dies (the one at 8.0)
    assert 7.9 <= cut.at <= 9.2
    assert cut.grid in ("one", "three")


def test_leaving_a_pinned_vocal_shot_stays_within_a_second_of_her_last_sound():
    # bar lines every 2 s here (beats every 1 s): the first one after her last sound (8.5) is the three at 10.0,
    # 1.5 s late for a pinned shot, so the plan moves the cut to the beat at 9.0 and says so
    pulse = Pulse(beats=tuple(float(k) for k in range(0, 31)), downbeat_slot=0)
    lines = [line("v01", 4.4, 8.5)]
    shots = [cutaway("N01"), vocal("S01", "v01"), cutaway("N02")]
    plan = plan_film(shots, lines, pulse, ends_at=30.0)
    cut = plan.cut_of("N02")
    assert cut.at - 8.5 <= 1.0
    assert cut.at == pytest.approx(9.0)
    assert "earlier" in cut.note
    assert plan.tasks["S01"]["pin"] == "full"


def test_unpinned_vocal_shot_may_leave_on_the_next_bar_line():
    pulse = Pulse(beats=tuple(float(k) for k in range(0, 31)), downbeat_slot=0)
    lines = [line("v01", 4.4, 8.5)]
    shots = [cutaway("N01"), vocal("S01", "v01", pin="none"), cutaway("N02")]
    plan = plan_film(shots, lines, pulse, ends_at=30.0)
    assert plan.cut_of("N02").at == pytest.approx(10.0)    # a three, within 2.2 s
    assert plan.cut_of("N02").grid == "three"


def test_a_time_set_by_the_person_snaps_to_the_nearest_one_or_three():
    lines = [line("v01", 4.4, 6.0)]
    shots = [vocal("S01", "v01", pin="none"), cutaway("N01", at="12.8")]
    plan = plan_film(shots, lines, grid_pulse(), ends_at=20.0)
    assert plan.cut_of("N01").at == pytest.approx(13.0)
    assert plan.cut_of("N01").grid == "three"
    assert "person" in plan.cut_of("N01").note


def test_a_person_time_far_from_any_bar_line_is_off_grid_and_says_so():
    pulse = Pulse(beats=tuple(float(k) for k in range(0, 31)), downbeat_slot=0)   # ones 0, 4, 8...; threes 2, 6, 10...
    shots = [cutaway("N01"), cutaway("N02", at="11.0")]
    plan = plan_film(shots, [], pulse, ends_at=30.0)
    cut = plan.cut_of("N02")
    assert cut.at == pytest.approx(11.0)
    assert cut.grid == "off"
    assert "OFF GRID" in plan.cut_table()


def test_late_in_lets_her_first_sound_play_over_the_shot_before():
    lines = [line("v01", 10.4, 14.6)]
    shots = [cutaway("N01"), vocal("S01", "v01", late_in=1.5)]
    plan = plan_film(shots, lines, grid_pulse(), ends_at=20.0)
    assert plan.cut_of("S01").at == pytest.approx(12.0)


def test_cutaways_between_anchors_share_the_gap_on_bar_lines():
    lines = [line("v01", 30.4, 33.0)]
    shots = [cutaway("N01"), cutaway("N02"), cutaway("N03"), vocal("S01", "v01")]
    plan = plan_film(shots, lines, grid_pulse(), ends_at=40.0)
    ats = [cut.at for cut in plan.cuts]
    assert ats[0] == pytest.approx(0.25)
    assert ats[1] == pytest.approx(10.0)
    assert ats[2] == pytest.approx(20.0)
    assert all(cut.grid in ("lead", "one", "three") for cut in plan.cuts)


def test_at_a_line_enters_a_cutaway_like_a_vocal_shot():
    lines = [line("v01", 10.4, 12.6)]
    shots = [cutaway("N01"), cutaway("N02", at="v01")]
    plan = plan_film(shots, lines, grid_pulse(), ends_at=20.0)
    assert plan.cut_of("N02").at == pytest.approx(10.0)


def test_two_cuts_at_one_time_are_an_error():
    from atomic_flix.plan import PlanError
    shots = [cutaway("N01"), cutaway("N02", at="10.0"), cutaway("N03", at="10.0")]
    with pytest.raises(PlanError, match="same time"):
        plan_film(shots, [], grid_pulse(), ends_at=20.0)


def test_cut_table_prints_every_cut_with_its_grid():
    lines = [line("v01", 10.4, 12.6)]
    plan = plan_film([cutaway("N01"), vocal("S01", "v01")], lines, grid_pulse(), ends_at=20.0)
    table = plan.cut_table()
    assert "N01" in table and "S01" in table
    assert "one" in table


def test_unknown_line_in_a_shot_is_an_error():
    from atomic_flix.plan import PlanError
    with pytest.raises(PlanError, match="v09"):
        plan_film([vocal("S01", "v09")], [line("v01", 1.0, 2.0)], grid_pulse(), ends_at=20.0)


def test_a_film_that_opens_at_zero_gets_a_lead_so_the_first_frames_stay_hidden():
    from atomic_flix.plan.slices import HEAD
    lines = [line("v01", 10.4, 12.6)]
    plan = plan_film([cutaway("N01"), vocal("S01", "v01")], lines, grid_pulse(), ends_at=20.0)
    first = plan.cuts[0]
    assert first.grid == "lead" and first.at == pytest.approx(HEAD)
    task = plan.tasks["N01"]
    assert task["slice_start"] == 0.0 and task["shown_at"][0] - task["slice_start"] >= HEAD - 1e-9
    assert "lead" in first.note


def test_singing_before_the_lead_is_refused_with_the_reason():
    from atomic_flix.plan import PlanError
    lines = [line("v01", 0.1, 2.6)]
    with pytest.raises(PlanError, match="before the film's first frame"):
        plan_film([vocal("S01", "v01"), cutaway("N01")], lines, grid_pulse(), ends_at=20.0)
