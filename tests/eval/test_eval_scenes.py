"""The optional `scene` field on shots, and the verdict rules of a row (unit tests, no film folder)."""

from __future__ import annotations

import numpy as np
import pytest

from atomic_flix.eval.rows import BLOCKED, CLEAN, WARN, Row, verdict_at
from atomic_flix.eval.scenes import png_size
from atomic_flix.plan import parse_shot_list
from atomic_flix.plan.model import Line, Pulse
from atomic_flix.plan.planner import plan_film
from atomic_flix.scenes.imageio import write_png


def test_a_shot_may_name_its_scene_and_old_lists_still_read():
    shots = parse_shot_list("N01 cutaway\n  scene: dunes\n  beat: sand drifts\n\nN02 cutaway\n  beat: sand drifts\n")
    assert [shot.scene for shot in shots] == ["dunes", None]


def test_the_plan_carries_the_scene_only_when_a_shot_has_one():
    shots = parse_shot_list("N01 cutaway\n  scene: dunes\n  beat: sand drifts\n\nN02 cutaway\n  beat: sand drifts\n")
    pulse = Pulse(beats=tuple(round(k * 0.5, 3) for k in range(40)))
    plan = plan_film(shots, [Line("v01", "lead", "la", 4.0, 6.0)], pulse, ends_at=16.0)
    assert plan.tasks["N01"]["scene"] == "dunes" and "scene" not in plan.tasks["N02"]


def test_png_size_reads_the_header_and_refuses_anything_else(tmp_path):
    path = write_png(tmp_path / "a.png", np.zeros((9, 16, 3), dtype=np.uint8))
    assert png_size(path) == (16, 9)
    (tmp_path / "b.png").write_bytes(b"png placeholder")
    assert png_size(tmp_path / "b.png") is None and png_size(tmp_path / "missing.png") is None


def _row(verdict, level="block", method="auto", due="spend"):
    return Row(rule="X1", unit="film", method=method, verdict=verdict, level=level, evidence="", due=due)


def test_unchecked_by_the_kit_blocks_but_unchecked_by_design_does_not():
    assert verdict_at([_row("unchecked")], "spend") == BLOCKED
    assert verdict_at([_row("unchecked", method="judge"), _row("unchecked", method=None)], "spend") == CLEAN


def test_a_failed_warn_rule_warns_and_a_note_never_lowers_the_verdict():
    assert verdict_at([_row("fail", level="warn"), _row("pass")], "spend") == WARN
    assert verdict_at([_row("fail", level="note")], "spend") == CLEAN


def test_rows_due_at_a_later_gate_do_not_count_yet():
    rows = [_row("fail", due="v1")]
    assert verdict_at(rows, "spend") == CLEAN and verdict_at(rows, "v1") == BLOCKED


def test_a_row_refuses_an_unknown_verdict_or_gate():
    with pytest.raises(ValueError):
        _row("maybe")
    with pytest.raises(ValueError):
        _row("pass", due="board")
