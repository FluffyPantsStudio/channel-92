"""A film measured against the first film's baseline, and the markdown report."""

import json
import os
from pathlib import Path

import pytest

from atomic_flix.compare import (
    METRICS,
    compare_film,
    load_baseline,
    measure_film,
    render_report,
)
from atomic_flix.compare.__main__ import main
from atomic_flix.gates import GATES, Answer
from atomic_flix.project import answer_gate, ask_gate, create_project, review_cut, set_record

CREATED = "2026-11-20T09:00:00+00:00"
ACCEPTED = "2026-11-22T18:00:00+00:00"

BASELINE = {
    "film": "First Film (films/first)",
    "calendar": {"start_to_acceptance": {"value": "about 4 calendar days (13 to 17); exact hours unknown",
                                          "provenance": "notes"}},
    "model_calls": {"cost_usd_list_price": {"value": 578, "provenance": "usage"},
                    "calls": {"value": 3090, "provenance": "usage"},
                    "driver_median_tokens_per_call": {"value": 416000, "provenance": "usage"}},
    "gpu": {"by_kind_of_job_seconds": {
        "provenance": "jobs",
        "sung_takes": {"jobs": 30, "seconds": 36000},
        "plate_takes": {"jobs": 20, "seconds": 18000},
        "some_stills_edit": {"jobs": 10, "seconds": 3600},
        "video_model_test_x": {"jobs": 2, "seconds": 360},
        "total": {"seconds": 57960, "hours": 16.1}}},
    "takes": {"rendered_total": {"value": 300, "provenance": "files"},
              "sung": {"value": 200, "shots": 10, "per_shot_mean": 20.0},
              "plate": {"value": 100, "shots": 10, "per_shot_mean": 10.0}},
    "sung_reshoots": {"full_passes_of_all_25_sung_shots": {"value": 8, "list": []}},
    "rendered_to_finished": {"finished_film_seconds": {"value": 100.0, "provenance": "ffprobe"},
                             "ratio": {"value": 26.7, "provenance": "jobs"}},
    "builds_and_reviews": {"numbered_builds": {"value": 25, "provenance": "files"}},
}


def entry(job, kind, shot, gpu, state="done", video=None, start="2026-11-21T10:00:00+00:00",
          end="2026-11-21T11:00:00+00:00"):
    row = {"job_id": job, "kind": kind, "shot": shot, "host": "127.0.0.1:8188", "seed": 7, "gpu_seconds": gpu,
           "started": start, "finished": end, "state": state}
    if video is not None:
        row["video_seconds"] = video
    return json.dumps(row)


@pytest.fixture
def baseline_path(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(BASELINE), encoding="utf-8")
    return path


@pytest.fixture
def film(tmp_path):
    film = create_project(tmp_path, "second", "Second Film", created=CREATED)
    (film.root / "audio" / "mix.wav").write_bytes(b"mix")
    for spec in GATES[:-1]:
        ask_gate(film, spec.id, ["shown"], at=CREATED)
        answer_gate(film, spec.id, Answer(words="yes", by="Test Person", provenance="person", at=CREATED))
    review_cut(film, "cuts/v02.mp4", "cold-1", [], at=ACCEPTED)
    ask_gate(film, "v1", ["cuts/v02.mp4"], at=ACCEPTED)
    answer_gate(film, "v1", Answer(words="video is ready, all good", by="Test Person", provenance="person", at=ACCEPTED))
    lines = [
        entry("S01-r001", "vocal", "S01", 1800, video=8),
        entry("S01-r002", "vocal", "S01", 1800, video=8),
        entry("S01-r003", "vocal", "S01", 1800, video=8),
        entry("S02-r001", "vocal", "S02", 1800, video=8),
        entry("S02-r002", "vocal", "S02", None, video=8),           # unmeasured: wall time 3600 s
        entry("S02-r003", "vocal", "S02", 900, state="errored"),
        entry("N01-r001", "cutaway", "N01", 3600, video=10),
        entry("N02-r001", "mute", "N02", 1800, video=6),
        entry("still-1", "still", None, 360),
        entry("test-1", "test", None, 360),
        entry("set-1", "blender", None, 720),
    ]
    film.job_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for name in ("v01.mp4", "v02.mp4", "v01-toned.mp4"):
        (film.root / "cuts" / name).write_bytes(b"cut")
    set_record(film, finished_seconds=100.0, calls=3090, cost_usd=300.0, reshoot_passes=9)
    return film


def test_baseline_numbers_are_read_with_their_sources(baseline_path):
    base = load_baseline(baseline_path)
    assert base["gpu_hours_total"].value == pytest.approx(16.1)
    assert base["gpu_hours_vocal"].value == pytest.approx(10.0)
    assert base["gpu_hours_cutaway"].value == pytest.approx(5.0)
    assert base["gpu_hours_still"].value == pytest.approx(1.0)
    assert base["gpu_hours_test"].value == pytest.approx(0.1)
    assert base["renders_per_finished_second"].value == pytest.approx(3.0)
    assert base["days_to_acceptance"].value == 4
    assert base["driver_calls"].value == 3090
    assert base["cost_usd"].provenance == "usage"
    assert base["reshoot_passes"].value == 8


def test_baseline_without_a_number_is_unknown(tmp_path):
    path = tmp_path / "b.json"
    path.write_text(json.dumps({"model_calls": {"calls": {"value": "unknown"}}}), encoding="utf-8")
    base = load_baseline(path)
    assert base["driver_calls"].value is None
    assert base["cost_usd"].value is None


def test_measures_the_film(film):
    got = measure_film(film)
    assert got["gpu_hours_vocal"].value == pytest.approx((1800 * 4 + 3600 + 900) / 3600)
    assert "wall" in got["gpu_hours_vocal"].note
    assert got["gpu_hours_cutaway"].value == pytest.approx(1.5)
    assert got["gpu_hours_still"].value == pytest.approx(0.1)
    assert got["gpu_hours_total"].value == pytest.approx((1800 * 4 + 3600 + 900 + 3600 + 1800 + 360 * 2 + 720) / 3600)
    assert got["renders_per_finished_second"].value == pytest.approx(7 / 100)
    assert got["vocal_renders_per_shot"].value == pytest.approx(2.5)
    assert got["cutaway_renders_per_shot"].value == pytest.approx(1.0)
    assert got["rendered_to_finished"].value == pytest.approx(56 / 100)
    assert got["builds"].value == 2
    assert got["days_to_acceptance"].value == 2
    assert got["driver_calls"].value == 3090
    assert got["driver_median_tokens"].value is None
    assert got["reshoot_passes"].value == 9


def test_a_planned_job_counts_no_gpu_time(tmp_path):
    film = create_project(tmp_path, "planned", "Planned", created=CREATED)
    film.job_log.write_text(entry("S01-r001", "vocal", "S01", 1800, video=8) + "\n"
                           + entry("S01-r002", "vocal", "S01", 3600, state="planned", end=None) + "\n",
                           encoding="utf-8")
    got = measure_film(film)
    assert got["gpu_hours_total"].value == pytest.approx(0.5)
    assert got["gpu_hours_vocal"].value == pytest.approx(0.5)


def test_the_total_hours_target_is_35_hours_at_most(tmp_path, baseline_path):
    def total_row(hours: float):
        film = create_project(tmp_path, f"h{int(hours)}", "Hours", created=CREATED)
        film.job_log.write_text(entry("S01-r001", "vocal", "S01", hours * 3600, video=8) + "\n", encoding="utf-8")
        rows = {row.key: row for row in compare_film(load_baseline(baseline_path), measure_film(film))}
        return rows["gpu_hours_total"]

    assert total_row(35.0).target_met == "yes"
    assert total_row(36.0).target_met == "no"


def test_verdicts_and_targets(film, baseline_path):
    rows = {row.key: row for row in compare_film(load_baseline(baseline_path), measure_film(film))}
    assert set(rows) == {metric.key for metric in METRICS}
    assert rows["gpu_hours_total"].verdict == "better" and rows["gpu_hours_total"].target_met == "yes"
    assert rows["driver_calls"].verdict == "same" and rows["driver_calls"].target_met == "no"
    assert rows["reshoot_passes"].verdict == "worse"
    assert rows["driver_median_tokens"].verdict == "unknown" and rows["driver_median_tokens"].target_met == "unknown"
    assert rows["cost_usd"].verdict == "better" and rows["cost_usd"].target_met == "no"
    assert rows["days_to_acceptance"].verdict == "better"


def test_an_unrecorded_film_is_unknown_everywhere_it_must_be(tmp_path, baseline_path):
    film = create_project(tmp_path, "empty", "Empty", created=CREATED)
    rows = {row.key: row for row in compare_film(load_baseline(baseline_path), measure_film(film))}
    for key in ("renders_per_finished_second", "days_to_acceptance", "cost_usd", "rendered_to_finished", "builds",
                "gpu_hours_total"):
        assert rows[key].verdict == "unknown", key
    text = render_report(tuple(rows.values()), film_name="Empty", baseline_name="First Film")
    assert "counts so far" in text


def test_the_report_is_plain_markdown(film, baseline_path):
    rows = compare_film(load_baseline(baseline_path), measure_film(film))
    text = render_report(rows, film_name="Second Film", baseline_name="First Film")
    assert text.startswith("# Second Film against First Film")
    assert "| Metric | First film | This film | Verdict | Aim | Aim met |" in text
    for word in ("better", "worse", "same", "unknown"):
        assert f"| {word} |" in text
    for metric in METRICS:
        assert metric.label in text
    assert "blender" in text
    assert "\u2014" not in text and "\u2013" not in text


def test_command_line_writes_the_report(film, baseline_path, tmp_path, capsys):
    out = tmp_path / "report.md"
    assert main([str(film.root), "--baseline", str(baseline_path), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# Second Film against First Film")
    assert main([str(film.root), "--baseline", str(baseline_path)]) == 0
    assert "| Metric |" in capsys.readouterr().out


def test_command_line_refuses_a_missing_baseline(film, tmp_path, capsys):
    assert main([str(film.root), "--baseline", str(tmp_path / "none.json")]) == 2
    assert "baseline" in capsys.readouterr().err


@pytest.mark.skipif(not os.environ.get("ATOMIC_FLIX_BASELINE"), reason="set ATOMIC_FLIX_BASELINE to the real file")
def test_the_real_baseline_loads():
    base = load_baseline(Path(os.environ["ATOMIC_FLIX_BASELINE"]))
    assert all(base[metric.key].value is not None for metric in METRICS)
