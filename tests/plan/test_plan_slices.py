"""Render slices, steps, phrases and the gate, derived from the cuts (core spec, stage 3)."""

import pytest

from atomic_flix.plan import Line, Pulse, ShotSpec, plan_film
from atomic_flix.plan.slices import gate_span, phrases_in_slice, whole_second_steps


def grid_pulse(step=0.5, stop=60.0):
    return Pulse(beats=tuple(round(k * step, 3) for k in range(int(stop / step) + 1)), downbeat_slot=0)


def line(key, start, end, text="la la la", gaps=()):
    return Line(key=key, part="lead", text=text, start=start, end=end, gaps=tuple(gaps))


def test_steps_boundaries_fall_in_the_gap():
    # spec: items 0.7-3.4 and 4.1-7.9 in 9 s: boundaries 0, 4, 9
    items = [(0.7, 3.4, "v01"), (4.1, 7.9, "v02")]
    steps = whole_second_steps(items, seconds=9, shown=(0.25, 8.3))
    assert [step.start for step in steps] + [steps[-1].end] == [0, 4, 9]
    assert steps[0].folded_head and steps[-1].folded_tail


def test_a_long_rest_keeps_its_own_step():
    items = [(2.2, 5.0, "v01")]
    steps = whole_second_steps(items, seconds=9, shown=(0.25, 7.5))
    assert [(step.start, step.end, step.lines) for step in steps] == [(0, 2, ()), (2, 5, ("v01",)), (5, 9, ())]


def test_steps_never_say_silent_over_singing():
    # a line starting at 0.55 would round to 1, leaving 0.45 s of singing in the rest: the boundary moves to 0
    items = [(1.55, 4.0, "v01")]
    steps = whole_second_steps(items, seconds=6, shown=(0.0, 5.0))
    rest = steps[0]
    assert rest.lines == ()
    assert rest.end - 1.55 <= 0.4


def test_lines_closer_than_a_second_share_a_step():
    items = [(1.0, 2.3, "v01"), (2.4, 2.9, "v02"), (3.0, 5.0, "v03")]
    steps = whole_second_steps(items, seconds=7, shown=(0.25, 6.0))
    for step in steps:
        assert step.end > step.start
    sung = [step.lines for step in steps if step.lines]
    assert sum(len(group) for group in sung) == 3


def test_phrases_join_across_short_gaps():
    lines = [line("v01", 10.0, 12.0, "one"), line("v02", 12.3, 14.0, "two"), line("v03", 15.0, 16.0, "three")]
    vocal_spans = phrases_in_slice(lines, slice_start=9.3)
    assert vocal_spans == [[0.7, 4.7, "one two"], [5.7, 6.7, "three"]]


def test_gate_stops_short_of_the_neighbouring_line():
    # spec: lines 2.0-4.0 and 4.1-6.0, shot sings the first: gate shut before 4.08
    lines = {"v01": line("v01", 2.0, 4.0), "v02": line("v02", 4.1, 6.0)}
    start, end = gate_span(["v01"], lines)
    assert end < 4.08
    assert end > 4.0
    assert 1.93 <= start <= 1.97


def test_gate_widens_after_her_last_sound_when_there_is_room():
    lines = {"v01": line("v01", 2.0, 4.0), "v02": line("v02", 8.0, 9.0)}
    start, end = gate_span(["v01"], lines)
    assert end == pytest.approx(4.25)
    assert start == pytest.approx(1.93)


def test_vocal_task_has_the_spec_fields():
    lines = [line("v01", 10.4, 12.6, "Hush now, the tub is warm")]
    shots = [ShotSpec(key="N01", kind="cutaway"), ShotSpec(key="S01", kind="vocal", sings=("v01",), still="stills/S01.png")]
    plan = plan_film(shots, lines, grid_pulse(), ends_at=20.0)
    task = plan.tasks["S01"]
    for key in ("key", "type", "slice_start", "seconds", "shown_at", "vocal_spans", "steps", "gate", "audio", "still",
                "closing_still"):
        assert key in task
    assert isinstance(task["seconds"], int)
    assert 4 <= task["seconds"] <= 15
    assert task["audio"] == "plan/S01.voice-soft.wav"
    assert task["closing_still"] == "stills/S01.png"      # pinned: the first frame again as the last
    assert task["steps"][0][0] == 0 and task["steps"][-1][1] == task["seconds"]
    run_up = 10.4 - task["slice_start"]
    assert 0.5 <= run_up <= 1.0


def test_slice_covers_the_shot_and_a_tail():
    lines = [line("v01", 10.4, 12.6)]
    shots = [ShotSpec(key="N01", kind="cutaway"), ShotSpec(key="S01", kind="vocal", sings=("v01",)),
             ShotSpec(key="N02", kind="cutaway")]
    plan = plan_film(shots, lines, grid_pulse(), ends_at=30.0)
    task = plan.tasks["S01"]
    on_from, on_to = task["shown_at"]
    assert task["slice_start"] <= on_from - 0.25 + 1e-9
    assert task["slice_start"] + task["seconds"] >= on_to + 0.3 - 1e-9


def test_cutaway_events_are_spread_over_what_the_cut_shows():
    shots = [ShotSpec(key="N01", kind="cutaway", beats=("the tub walks", "the tub stops", "the sky turns"))]
    plan = plan_film(shots, [], grid_pulse(), ends_at=6.0)
    task = plan.tasks["N01"]
    starts = [step[0] for step in task["steps"]]
    assert starts[0] == 0
    shown_end = task["shown_at"][1] - task["slice_start"]
    assert all(start < shown_end for start in starts)
    assert task["steps"][-1][1] == task["seconds"]


def test_a_long_shot_beyond_fifteen_seconds_is_reported():
    shots = [ShotSpec(key="N01", kind="cutaway")]
    plan = plan_film(shots, [], grid_pulse(stop=40.0), ends_at=40.0)
    assert plan.tasks["N01"]["seconds"] == 15
    assert any("15" in note for note in plan.tasks["N01"]["notes"])


def test_wordless_line_gets_a_soft_round_mouth():
    lines = [line("v01", 10.4, 14.6, "aa-h-aaaaa-aha-aaaaaah")]
    shots = [ShotSpec(key="N01", kind="cutaway"), ShotSpec(key="S01", kind="vocal", sings=("v01",))]
    plan = plan_film(shots, lines, grid_pulse(), ends_at=20.0)
    sung = [step for step in plan.tasks["S01"]["steps"] if step[2] != "rest"]
    assert "soft round oo" in sung[0][4]


def test_neighbouring_vocal_shots_on_one_setup_need_different_sizes():
    lines = [line("v01", 4.4, 6.0), line("v02", 7.4, 9.0), line("v03", 10.4, 12.0)]
    shots = [ShotSpec(key="S01", kind="vocal", sings=("v01",), setup="moon", crop=0.85),
             ShotSpec(key="S02", kind="vocal", sings=("v02",), setup="moon", crop=0.8),
             ShotSpec(key="S03", kind="vocal", sings=("v03",), setup="moon", crop=0.6)]
    plan = plan_film(shots, lines, grid_pulse(), ends_at=20.0)
    assert any("S01" in note and "S02" in note for note in plan.notes)
    assert not any("S02" in note and "S03" in note and "size" in note for note in plan.notes)


def test_mute_and_plate_kinds():
    shots = [ShotSpec(key="N01", kind="cutaway", figures=False), ShotSpec(key="M01", kind="mute", figures=True)]
    plan = plan_film(shots, [], grid_pulse(), ends_at=12.0)
    assert plan.tasks["N01"]["role"] == "plate"
    assert plan.tasks["M01"]["role"] == "silent"
