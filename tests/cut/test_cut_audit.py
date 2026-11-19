import numpy as np
import pytest

from atomic_flix.cut.audit import TakeInfo, audit_edit
from atomic_flix.cut.edit import Cut, Edit, Placed
from atomic_flix.wav import save_wav

INFO = {"A": TakeInfo(fps=24.0, frames=96, width=192, height=108),
        "B": TakeInfo(fps=24.0, frames=96, width=192, height=108),
        "C": TakeInfo(fps=24.0, frames=96, width=192, height=108)}
PULSE = {"beats": [0.5 * i for i in range(40)], "downbeat_slot": 0}


def _edit(cuts, takes, **extra):
    base = dict(fps=24, size=(192, 108), song=None, start=0.0, end=4.0, pulse=PULSE)
    base.update(extra)
    return Edit(cuts=tuple(cuts), takes=takes, **base)


def _row(account, key):
    return next(row for row in account.rows if row["key"] == key)


def test_clean_edit_reports_counts_and_lengths():
    takes = {"A": Placed("A", "a", ((0.0, 0.5),)), "B": Placed("B", "b", ((2.0, 0.5),))}
    account = audit_edit(_edit([Cut("A", 0.0), Cut("B", 2.0)], takes), take_info=INFO)
    assert account.errors == []
    b = _row(account, "B")
    assert b["count"] == 1
    assert b["take_seconds"] == pytest.approx(4.0)
    assert b["shown_seconds"] == pytest.approx(2.0)
    assert b["used"] == [pytest.approx(0.5), pytest.approx(2.5, abs=0.05)]
    assert b["slowest_rate"] == pytest.approx(1.0)
    assert b["slower"] is False


def test_cut_off_the_one_and_three_is_named():
    takes = {"A": Placed("A", "a", ((0.0, 0.5),)), "B": Placed("B", "b", ((2.5, 0.5),))}
    account = audit_edit(_edit([Cut("A", 0.0), Cut("B", 2.5)], takes), take_info=INFO)
    assert _row(account, "B")["count"] == 2
    assert any("B" in w and "count 2" in w for w in account.warnings)


def test_a_take_played_slower_is_an_error():
    takes = {"A": Placed("A", "a", ((0.0, 0.5), (4.0, 3.7)))}
    account = audit_edit(_edit([Cut("A", 0.0)], takes), take_info=INFO)
    row = _row(account, "A")
    assert row["slower"] is True and row["slowest_rate"] == pytest.approx(0.8)
    assert any("slower" in e for e in account.errors)


def test_faster_is_allowed():
    takes = {"A": Placed("A", "a", ((0.0, 0.5), (2.0, 3.0)))}
    account = audit_edit(_edit([Cut("A", 0.0)], takes, end=2.0), take_info=INFO)
    assert account.errors == []
    assert _row(account, "A")["fastest_rate"] == pytest.approx(1.25)


def test_showing_a_takes_first_two_frames_is_an_error():
    takes = {"A": Placed("A", "a", ((0.0, 0.04),))}
    account = audit_edit(_edit([Cut("A", 0.0)], takes), take_info=INFO)
    assert any("first two frames" in e for e in account.errors)


def test_jump_cut_between_two_takes_of_one_setup():
    takes = {"A": Placed("A", "a", ((0.0, 0.5),), setup="moon", crop_keep=1.0),
             "B": Placed("B", "b", ((1.5, 0.5),), setup="moon", crop_keep=1.0),
             "C": Placed("C", "c", ((3.0, 0.5),), setup="desert", crop_keep=1.0)}
    account = audit_edit(_edit([Cut("A", 0.0), Cut("B", 1.5), Cut("C", 3.0)], takes), take_info=INFO)
    assert any("jump cut" in e and "A" in e and "B" in e for e in account.errors)
    assert _row(account, "B")["jump_from_previous"] is True
    assert _row(account, "C")["jump_from_previous"] is False


def test_tail_past_the_take_end_is_reported_as_a_hold():
    short = dict(INFO, A=TakeInfo(fps=24.0, frames=48, width=192, height=108))
    takes = {"A": Placed("A", "a", ((0.0, 0.5),))}
    account = audit_edit(_edit([Cut("A", 0.0)], takes, end=3.0), take_info=short)
    assert _row(account, "A")["held_at_end"] == pytest.approx(1.5, abs=0.05)
    assert any("holds its last frame" in e for e in account.errors)


def test_cut_inside_a_held_note_from_the_voice_stem(tmp_path):
    rate = 48000
    voice = np.zeros(rate * 5)
    t = np.arange(rate * 5) / rate
    held = (t >= 1.2) & (t < 2.6)
    voice[held] = 0.3 * np.sin(2 * np.pi * 220 * t[held])
    voice_path = save_wav(tmp_path / "voice.wav", voice, rate)
    takes = {"A": Placed("A", "a", ((0.0, 0.5),)), "B": Placed("B", "b", ((2.0, 0.5),)),
             "C": Placed("C", "c", ((3.0, 0.5),))}
    account = audit_edit(_edit([Cut("A", 0.0), Cut("B", 2.0), Cut("C", 3.0)], takes, voice=voice_path),
                        take_info=INFO)
    assert _row(account, "B")["held_note"] is True
    assert _row(account, "C")["held_note"] is False
    assert any("held note" in w and "B" in w for w in account.warnings)


def test_cut_inside_a_sung_line_without_a_stem():
    takes = {"A": Placed("A", "a", ((0.0, 0.5),)), "B": Placed("B", "b", ((2.0, 0.5),))}
    account = audit_edit(_edit([Cut("A", 0.0), Cut("B", 2.0)], takes, sung=((1.0, 3.0),)), take_info=INFO)
    assert _row(account, "B")["mid_line"] is True
    assert _row(account, "B")["held_note"] is None


def test_short_shot_is_warned():
    takes = {"A": Placed("A", "a", ((0.0, 0.5),)), "B": Placed("B", "b", ((1.0, 0.5),))}
    account = audit_edit(_edit([Cut("A", 0.0), Cut("B", 1.0)], takes), take_info=INFO)
    assert any("A" in w and "1.6" in w for w in account.warnings)


def test_audit_text_lists_every_cut():
    takes = {"A": Placed("A", "a", ((0.0, 0.5),)), "B": Placed("B", "b", ((2.0, 0.5),))}
    text = audit_edit(_edit([Cut("A", 0.0), Cut("B", 2.0)], takes), take_info=INFO).text()
    assert "A" in text and "B" in text and "count" in text


# ---- playback rate judged against the placement's own uncertainty -------------------------------------------------


def _jittered_map(seconds=4.0, slope=1.0, wobble=0.01, step=0.1, offset=0.5, seed=7):
    """Points every `step` s, as placing by sound writes them: a straight line plus one-hop timing noise."""
    rng = np.random.default_rng(seed)
    times = np.arange(0.0, seconds + 1e-9, step)
    takes = offset + slope * times + rng.choice([-wobble, 0.0, wobble], size=len(times))
    takes = np.maximum.accumulate(takes)
    return tuple((float(t), float(r)) for t, r in zip(times, takes))


def test_placement_jitter_near_1x_is_not_a_slowed_take():
    # the first film's maps: points 0.1 s apart, each off by up to a 10 ms hop, so neighbour slopes read 0.88 to
    # 1.12 while the take runs at 1x; the audit must not refuse that
    placed = Placed("A", "a", _jittered_map())
    assert min(placed.rates_between(0.0, 4.0)) < 0.9            # the old point-to-point reading
    account = audit_edit(_edit([Cut("A", 0.0)], {"A": placed}), take_info=INFO)
    row = _row(account, "A")
    assert row["slower"] is False, account.errors
    assert row["slowest_rate"] > 0.97
    assert row["slowest_point_rate"] < 0.9                        # still shown, so nothing is hidden


def test_a_take_a_little_slower_over_the_whole_shot_is_refused():
    placed = Placed("A", "a", _jittered_map(slope=0.97, wobble=0.0))
    account = audit_edit(_edit([Cut("A", 0.0)], {"A": placed}), take_info=INFO)
    assert _row(account, "A")["slower"] is True
    assert any("slower than 1x" in e for e in account.errors)


def test_a_short_slowed_stretch_inside_a_shot_is_refused():
    ties = ((0.0, 0.5), (1.5, 2.0), (2.5, 2.8), (4.0, 4.3))   # 0.8x for one second in the middle
    account = audit_edit(_edit([Cut("A", 0.0)], {"A": Placed("A", "a", ties)}), take_info=INFO)
    row = _row(account, "A")
    assert row["slower"] is True and row["slowest_rate"] == pytest.approx(0.8, abs=0.02)


def test_slow_tolerance_comes_from_the_placement_uncertainty():
    from atomic_flix.cut.rate import PLACEMENT_UNCERTAINTY_S, slow_tolerance
    assert slow_tolerance(2.0) == pytest.approx(PLACEMENT_UNCERTAINTY_S)
    assert slow_tolerance(4.0) == pytest.approx(slow_tolerance(2.0) / 2)
    assert slow_tolerance(1.0) == pytest.approx(0.03)          # capped: never more than 3 % under 1x


# ---- the jump-cut decision is the one lint rule C1 makes ------------------------------------------------------------


def _two_on_one_setup(size_a, size_b):
    return {"A": Placed("A", "a", ((0.0, 0.5),), setup="moon", crop_keep=size_a),
            "B": Placed("B", "b", ((2.0, 0.5),), setup="moon", crop_keep=size_b)}


def test_one_setup_at_clearly_different_sizes_is_not_a_jump():
    account = audit_edit(_edit([Cut("A", 0.0), Cut("B", 2.0)], _two_on_one_setup(1.0, 0.62)), take_info=INFO)
    assert _row(account, "B")["jump_from_previous"] is False
    assert not any("jump" in e for e in account.errors)


def test_one_setup_at_nearly_one_size_is_a_jump():
    account = audit_edit(_edit([Cut("A", 0.0), Cut("B", 2.0)], _two_on_one_setup(1.0, 0.9)), take_info=INFO)
    assert _row(account, "B")["jump_from_previous"] is True
    assert any("jump cut" in e for e in account.errors)


def test_one_setup_with_a_size_not_recorded_is_a_warning_not_an_error():
    account = audit_edit(_edit([Cut("A", 0.0), Cut("B", 2.0)], _two_on_one_setup(1.0, None)), take_info=INFO)
    assert not any("jump" in e for e in account.errors)
    assert any("size" in w and "A" in w and "B" in w for w in account.warnings)


@pytest.mark.parametrize("sizes", [(1.0, 0.62), (1.0, 0.9), (0.7, 0.75), (0.5, 0.75), (1.0, None)])
def test_audit_and_lint_c1_agree_on_every_pair(sizes):
    from atomic_flix.lint import book_from_case, check_rule
    a, b = sizes
    account = audit_edit(_edit([Cut("A", 0.0), Cut("B", 2.0)], _two_on_one_setup(a, b)), take_info=INFO)
    shots = [{"key": "A", "kind": "vocal", "sings": ["v01"], "setup": "moon", "crop": a},
             {"key": "B", "kind": "vocal", "sings": ["v01"], "setup": "moon", "crop": b}]
    lint_says_jump = bool(check_rule("C1", book_from_case({"shots": shots})))
    assert _row(account, "B")["jump_from_previous"] is lint_says_jump
