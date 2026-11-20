"""Gaps found driving the real ComfyUI hosts (docs/real-run.md): a fixed seed for a re-render, and refusing to start
a heavy load while commit headroom is under a floor the person sets."""

from __future__ import annotations

import json

import pytest

from atomic_flix.runner.__main__ import main
from atomic_flix.runner.jobs import JobStore
from atomic_flix.runner.ledger import read_rows
from atomic_flix.runner.sched import LoadGate
from atomic_flix.runner.shoot import Request, Runner, plan_batch
from atomic_flix.runner.template import TemplateError

FAST = 0.02
OLD_SEED = 2673691454


def _request(key: str, graph, **extra) -> Request:
    inputs = {"opening_still": f"stills/{key}.png", "audio": f"plan/{key}.voice-soft.wav"}
    return Request(key=key, graph=str(graph), wording=f"Nova sings {key}", inputs=inputs, seconds=10, vocal=True,
                   **extra)


def _runner(film_dir, hosts, tmp_path, **kwargs) -> Runner:
    options = {"poll_s": FAST, "timeout_s": 10.0, "gate": LoadGate(lambda: 100.0), "say": lambda _: None}
    options.update(kwargs)
    return Runner(film_dir, [h.host for h in hosts], machine_log_path=tmp_path / "log" / "jobs.jsonl", **options)


# a fixed seed ------------------------------------------------------------------------------------------------------

def test_a_request_with_a_seed_keeps_it_through_planning_and_into_the_graph(film_dir, sung_graph, fake_hosts,
                                                                             tmp_path):
    (fake,) = fake_hosts(1)
    (job,) = plan_batch(film_dir, [_request("S02", sung_graph, seed=OLD_SEED)])
    assert job["seed"] == OLD_SEED
    _runner(film_dir, [fake], tmp_path).run()
    graph = fake.prompts[fake.submitted[0]]["graph"]
    assert graph["37"]["inputs"]["noise_seed"] == OLD_SEED
    assert read_rows(tmp_path / "log" / "jobs.jsonl")[0]["seed"] == OLD_SEED


def test_two_requests_without_a_seed_still_get_their_own(film_dir, sung_graph):
    first, second = plan_batch(film_dir, [_request("S02", sung_graph), _request("S02", sung_graph)])
    assert first["seed"] != second["seed"]


@pytest.mark.parametrize("seed", [-1, 2 ** 32, 1.5, "7", True])
def test_a_seed_outside_the_noise_range_is_refused_before_any_job_is_written(film_dir, sung_graph, seed):
    with pytest.raises(TemplateError, match="seed"):
        plan_batch(film_dir, [_request("S02", sung_graph, seed=seed)])
    assert not (film_dir / "renders").exists()


def test_the_batch_file_carries_a_seed(film_dir, sung_graph, tmp_path, capsys):
    batch = {"requests": [{"key": "S02", "graph": str(sung_graph), "wording": "Nova sings", "seconds": 10,
                           "vocal": True, "seed": OLD_SEED,
                           "inputs": {"opening_still": "stills/S02.png", "audio": "plan/S02.voice-soft.wav"}}]}
    path = tmp_path / "batch.json"
    path.write_text(json.dumps(batch), encoding="utf-8")
    assert main(["plan", str(film_dir), str(path)]) == 0
    assert f"seed {OLD_SEED}" in capsys.readouterr().out
    assert JobStore(film_dir).load_all()[0]["seed"] == OLD_SEED


# a floor on commit headroom -----------------------------------------------------------------------------------------

def test_a_heavy_job_is_not_started_while_headroom_is_under_the_floor(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    said: list[str] = []
    summary = _runner(film_dir, [fake], tmp_path, min_headroom_gb=35.0, read_headroom=lambda: 30.0,
                      say=said.append).run()
    assert fake.submitted == [] and fake.uploads == {}
    assert JobStore(film_dir).load_all()[0]["state"] == "planned"
    assert read_rows(tmp_path / "log" / "jobs.jsonl") == []
    assert summary["refused"] and summary["not_started"] == 1
    assert any("30" in line and "35" in line for line in said)


def test_a_heavy_job_starts_when_headroom_clears_the_floor(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    summary = _runner(film_dir, [fake], tmp_path, min_headroom_gb=25.0, read_headroom=lambda: 30.0).run()
    assert JobStore(film_dir).load_all()[0]["state"] == "done"
    assert not summary["refused"]


def test_unknown_headroom_counts_as_under_the_floor(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    summary = _runner(film_dir, [fake], tmp_path, min_headroom_gb=1.0, read_headroom=lambda: None).run()
    assert fake.submitted == [] and summary["refused"]


def test_a_light_graph_ignores_the_floor(film_dir, tmp_path, fake_hosts):
    from runner_samples import SILENT_GRAPH, write_graph
    light = write_graph(film_dir / "graphs", "light.json", SILENT_GRAPH, {"light": True})
    (fake,) = fake_hosts(1)
    plan_batch(film_dir, [Request(key="S02", graph=str(light), wording="a plate", seconds=4,
                                 inputs={"opening_still": "stills/S02.png"})])
    summary = _runner(film_dir, [fake], tmp_path, min_headroom_gb=50.0, read_headroom=lambda: 1.0).run()
    assert JobStore(film_dir).load_all()[0]["state"] == "done" and not summary["refused"]


def test_headroom_that_drops_mid_batch_stops_before_the_next_heavy_job(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1)
    plan_batch(film_dir, [_request("S01", sung_graph), _request("S02", sung_graph)])
    readings = iter([40.0, 40.0, 10.0])          # the floor is read before the load gate and again after it
    summary = _runner(film_dir, [fake], tmp_path, min_headroom_gb=20.0,
                      read_headroom=lambda: next(readings, 10.0)).run()
    states = sorted(job["state"] for job in JobStore(film_dir).load_all())
    assert states == ["done", "planned"] and len(fake.submitted) == 1 and summary["refused"]


def test_the_command_line_takes_the_floor_and_exits_1_when_refused(film_dir, sung_graph, fake_hosts, tmp_path,
                                                                    capsys, monkeypatch, cleared):
    (fake,) = fake_hosts(1)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    monkeypatch.setattr("atomic_flix.runner.shoot.headroom_gb", lambda: 30.0)
    monkeypatch.setattr("atomic_flix.runner.__main__.LoadGate", lambda: LoadGate(lambda: 30.0))
    log = tmp_path / "log" / "jobs.jsonl"
    code = main(["shoot", str(film_dir), "--hosts", fake.host, "--log", str(log), "--min-headroom", "35"])
    captured = capsys.readouterr()
    assert code == 1
    assert "refused" in captured.out + captured.err
    assert fake.submitted == []
    assert JobStore(film_dir).load_all()[0]["state"] == "planned"


# a still has no video length ----------------------------------------------------------------------------------------

def _still_graph(film_dir):
    from runner_samples import SILENT_GRAPH, write_graph
    graph = {key: node for key, node in SILENT_GRAPH.items() if key not in ("10", "11")}
    graph["4"] = {"class_type": "LoadImage", "inputs": {"image": "$image1"}}
    return write_graph(film_dir / "graphs", "still.json", graph, {"kind": "still", "commit_gb": 20})


def test_a_still_logs_its_gpu_time_but_no_video_seconds(film_dir, fake_hosts, tmp_path):
    from atomic_flix.compare.ledger import read_job_log
    (fake,) = fake_hosts(1, gpu_ms=79_000)
    plan_batch(film_dir, [Request(key="T01", graph=str(_still_graph(film_dir)), wording="the still, smaller",
                                 seconds=0.04, width=640, height=352, kind="still",
                                 inputs={"image1": "stills/S02.png"})])
    summary = _runner(film_dir, [fake], tmp_path).run()
    (row,) = read_rows(tmp_path / "log" / "jobs.jsonl")
    assert row["video_s"] is None and row["busy_s"] == pytest.approx(79.0)
    (entry,) = read_job_log(film_dir / "job-log.jsonl").logged
    assert entry.video_seconds is None and entry.gpu_seconds == pytest.approx(79.0)
    assert summary["gpu_hours"] == pytest.approx(79.0 / 3600)
    assert summary["gpu_s_per_video_s"] is None


def test_summary_counts_still_time_in_gpu_hours_but_not_in_the_video_rate():
    from atomic_flix.runner.ledger import summarize
    rows = [{"ok": True, "busy_s": 100.0, "video_s": 10.0}, {"ok": True, "busy_s": 80.0, "video_s": None}]
    summary = summarize(rows)
    assert summary["gpu_hours"] == pytest.approx(180.0 / 3600)
    assert summary["gpu_s_per_video_s"] == pytest.approx(10.0)
    assert summary["made"] == 2


def test_a_run_with_nothing_waiting_says_so_instead_of_an_empty_estimate(film_dir, fake_hosts, tmp_path, capsys,
                                                                       cleared):
    (fake,) = fake_hosts(1)
    log = tmp_path / "log" / "jobs.jsonl"
    assert main(["shoot", str(film_dir), "--hosts", fake.host, "--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "nothing waiting" in out and "0 takes at no size" not in out
    assert fake.submitted == []
