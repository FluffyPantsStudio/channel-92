"""The job ledger and the hours estimate shown before a batch (gate 5)."""

from __future__ import annotations

import pytest

from atomic_flix.runner.budget import estimate, gate_text
from atomic_flix.runner.ledger import append_row, read_rows, summarize


def _row(graph="sung-pinned.json", width=1280, height=704, video_s=9.0, busy_s=180.0, ok=True):
    return {"graph": graph, "width": width, "height": height, "video_s": video_s, "busy_s": busy_s, "ok": ok}


def _job(graph="graphs/sung-pinned.json", width=1280, height=704, frames=217, fps=24):
    return {"graph": graph, "width": width, "height": height, "frames": frames, "fps": fps, "state": "planned"}


def test_rows_append_as_json_lines_and_read_back(tmp_path):
    path = tmp_path / "log" / "jobs.jsonl"
    assert append_row(path, {"key": "S02", "seed": 5, "lyric": "Fröhlich"})
    assert append_row(path, {"key": "S03", "seed": 6})
    assert [r["key"] for r in read_rows(path)] == ["S02", "S03"]
    assert read_rows(path)[0]["lyric"] == "Fröhlich"
    assert "time" in read_rows(path)[0]


def test_a_broken_line_is_skipped_and_a_missing_file_is_empty(tmp_path):
    path = tmp_path / "jobs.jsonl"
    path.write_text('{"key": "S02"}\nnot json\n{"key": "S03"}\n', encoding="utf-8")
    assert [r["key"] for r in read_rows(path)] == ["S02", "S03"]
    assert read_rows(tmp_path / "none.jsonl") == []


def test_append_reports_failure_instead_of_raising(tmp_path):
    assert append_row(tmp_path, {"key": "S02"}) is False


def test_summary_counts_renders_and_gpu_hours():
    rows = [_row(busy_s=180.0), _row(busy_s=90.0, video_s=4.5), _row(ok=False, busy_s=None)]
    summary = summarize(rows)
    assert summary["made"] == 2 and summary["errored"] == 1
    assert summary["gpu_hours"] == pytest.approx(270 / 3600)
    assert summary["gpu_s_per_video_s"] == pytest.approx(20.0)


def test_estimate_uses_past_rows_of_the_same_graph_and_size():
    rows = [_row(busy_s=180.0), _row(busy_s=200.0), _row(busy_s=160.0), _row(graph="plate.json", busy_s=999.0)]
    est = estimate([_job() for _ in range(10)], rows, hosts=2, parallel=True)
    video_s = 217 / 24
    assert est.takes == 10
    assert est.gpu_s_per_video_s == pytest.approx(20.0)
    assert est.gpu_hours == pytest.approx(10 * video_s * 20 / 3600)
    assert est.wall_hours == pytest.approx(est.gpu_hours / 2)
    assert est.rows_used == 3 and "same graph and size" in est.basis


def test_a_slow_tail_shows_in_the_mean_figure_not_the_median():
    rows = [_row(busy_s=180.0), _row(busy_s=180.0), _row(busy_s=1800.0)]
    est = estimate([_job()], rows, hosts=1)
    assert est.gpu_s_per_video_s == pytest.approx(20.0)
    assert est.gpu_hours_mean == pytest.approx(est.gpu_hours * 80 / 20)
    assert "at the mean rate" in gate_text(est)


def test_rows_that_name_a_workflow_count_as_the_graph():
    rows = [{"workflow": "sung-pinned.json", "width": 1280, "height": 704, "video_s": 9.0, "busy_s": 180.0,
             "ok": True}]
    assert estimate([_job()], rows).gpu_s_per_video_s == pytest.approx(20.0)


def test_one_load_at_a_time_holds_both_gpus_for_the_whole_sum():
    est = estimate([_job() for _ in range(10)], [_row()], hosts=2, parallel=False)
    assert est.wall_hours == pytest.approx(est.gpu_hours)


def test_another_size_scales_by_pixels():
    rows = [_row(width=1280, height=704, busy_s=180.0)]
    est = estimate([_job(width=640, height=352)], rows, hosts=1, parallel=True)
    assert est.gpu_s_per_video_s == pytest.approx(5.0)
    assert "scaled by pixels" in est.basis


def test_no_history_gives_no_hours_and_says_so():
    est = estimate([_job()], [], hosts=2, parallel=True)
    assert est.gpu_hours is None and est.wall_hours is None
    assert "no measured" in gate_text(est)


def test_gate_text_names_takes_size_and_hours():
    rows = [_row(busy_s=180.0)]
    text = gate_text(estimate([_job() for _ in range(12)], rows, hosts=2, parallel=True))
    assert "12 takes" in text and "1280x704" in text
    assert "GPU hours" in text and "both GPUs" in text
