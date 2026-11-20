"""The runner against fake ComfyUI hosts: submit, poll, collect, resume, log."""

from __future__ import annotations

import json
import threading
import time

import pytest

from atomic_flix.runner.jobs import JobStore
from atomic_flix.runner.ledger import read_rows
from atomic_flix.runner.sched import LoadGate
from atomic_flix.runner.shoot import Request, Runner, plan_batch
from atomic_flix.runner.template import TemplateError
from fake_comfyui import EMPTY, ERROR, HANG, Concurrency

FAST = 0.02


def _request(key: str, graph, vocal: bool = True, **extra) -> Request:
    inputs = {"opening_still": f"stills/{key}.png"}
    if vocal:
        inputs["audio"] = f"plan/{key}.voice-soft.wav"
    return Request(key=key, graph=str(graph), wording=f"Nova sings {key}", inputs=inputs, seconds=9,
                   vocal=vocal, **extra)


def _runner(film_dir, hosts, tmp_path, **kwargs) -> Runner:
    options = {"poll_s": FAST, "timeout_s": 10.0, "gate": LoadGate(lambda: 100.0), "say": lambda _: None}
    options.update(kwargs)
    return Runner(film_dir, [h.host for h in hosts], machine_log_path=tmp_path / "log" / "jobs.jsonl", **options)


def test_a_vocal_task_on_a_graph_without_audio_is_refused_before_any_http(film_dir, silent_graph, fake_hosts):
    (fake,) = fake_hosts(1)
    with pytest.raises(TemplateError, match="audio"):
        plan_batch(film_dir, [_request("S02", silent_graph, vocal=True)])
    assert fake.requests == []
    assert not (film_dir / "renders").exists()


def test_a_missing_input_file_is_refused_before_any_job_is_written(film_dir, sung_graph):
    (film_dir / "stills" / "S03.png").unlink()
    with pytest.raises(TemplateError, match="S03.png"):
        plan_batch(film_dir, [_request("S02", sung_graph), _request("S03", sung_graph)])
    assert not (film_dir / "renders").exists()


def test_planning_writes_job_files_with_seed_prefix_and_frames(film_dir, sung_graph):
    (job,) = plan_batch(film_dir, [_request("S02", sung_graph)])
    saved = json.loads((film_dir / "renders" / "S02" / "r001.job.json").read_text(encoding="utf-8"))
    assert saved == job
    assert job["state"] == "planned" and job["frames"] == 217
    assert isinstance(job["seed"], int) and 0 <= job["seed"] < 2 ** 32
    assert job["save_as"].startswith("girl-in-the-tub-S02-")
    assert job["inputs"] == {"opening_still": "stills/S02.png", "audio": "plan/S02.voice-soft.wav"}
    assert job["graph_digest"] and job["commit_gb"] == 40


def test_one_job_runs_to_done_with_its_output_and_one_log_line(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1, polls_to_finish=2)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    summary = _runner(film_dir, [fake], tmp_path).run()
    job = JobStore(film_dir).load_all()[0]
    assert job["state"] == "done"
    assert job["host"] == fake.host and job["queue_ticket"] == fake.submitted[0]
    assert job["busy_s"] == pytest.approx(80.0)
    assert job["waited_s"] is not None
    out = film_dir / "renders" / "S02" / "r001.mp4"
    assert out.read_bytes().startswith(b"VIDEO:output:")
    assert job["result_file"] == "renders/S02/r001.mp4"
    graph = fake.prompts[fake.submitted[0]]["graph"]
    assert graph["37"]["inputs"]["noise_seed"] == job["seed"]
    assert graph["31"]["inputs"]["length"] == 217
    assert graph["10"]["inputs"]["image"] in fake.uploads
    assert graph["20"]["inputs"]["audio"] in fake.uploads
    rows = read_rows(tmp_path / "log" / "jobs.jsonl")
    assert len(rows) == 1
    row = rows[0]
    assert row["ok"] is True and row["seed"] == job["seed"] and row["busy_s"] == pytest.approx(80.0)
    assert row["gpu"] == "Fake GPU 0" and row["film"] == "girl-in-the-tub" and row["key"] == "S02"
    assert row["video_s"] == pytest.approx(217 / 24, abs=0.01) and row["width"] == 1280
    assert summary["made"] == 1 and summary["errored"] == 0


def test_completed_with_no_outputs_fails_with_the_cached_graph_message(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1, mode=EMPTY)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    summary = _runner(film_dir, [fake], tmp_path).run()
    job = JobStore(film_dir).load_all()[0]
    assert job["state"] == "errored"
    assert "cached" in job["error"] and "$seed" in job["error"]
    rows = read_rows(tmp_path / "log" / "jobs.jsonl")
    assert rows[0]["ok"] is False and "cached" in rows[0]["error"]
    assert summary["errored"] == 1


def test_a_graph_error_fails_the_job_with_the_message(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1, mode=ERROR)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    _runner(film_dir, [fake], tmp_path).run()
    job = JobStore(film_dir).load_all()[0]
    assert job["state"] == "errored" and "CUDA out of memory" in job["error"]
    assert len(read_rows(tmp_path / "log" / "jobs.jsonl")[0]["error"]) <= 300


def _run_until_submitted(runner: Runner, fake, count: int = 1) -> threading.Thread:
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while len(fake.submitted) < count and time.time() < deadline:
        time.sleep(0.01)
    assert len(fake.submitted) == count
    return thread


def test_killed_after_submit_then_restarted_collects_once_and_never_resubmits(film_dir, sung_graph, fake_hosts,
                                                                              tmp_path):
    (fake,) = fake_hosts(1, mode=HANG)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    first = _runner(film_dir, [fake], tmp_path)
    thread = _run_until_submitted(first, fake)
    first.stop()
    thread.join(5)
    assert not thread.is_alive()
    job = JobStore(film_dir).load_all()[0]
    assert job["state"] == "running" and job["queue_ticket"] == fake.submitted[0]
    assert read_rows(tmp_path / "log" / "jobs.jsonl") == []

    fake.finish_all()
    _runner(film_dir, [fake], tmp_path).run()
    assert len(fake.submitted) == 1, "a job ComfyUI still knows is never submitted again"
    job = JobStore(film_dir).load_all()[0]
    assert job["state"] == "done"
    names = sorted(p.name for p in (film_dir / "renders" / "S02").iterdir() if p.name.startswith("r"))
    assert names == ["r001.job.json", "r001.mp4"]
    assert len(read_rows(tmp_path / "log" / "jobs.jsonl")) == 1


def test_restart_waits_for_a_job_still_queued_on_its_host(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1, mode=HANG)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    first = _runner(film_dir, [fake], tmp_path)
    thread = _run_until_submitted(first, fake)
    first.stop()
    thread.join(5)
    with fake.lock:
        entry = fake.prompts[fake.submitted[0]]
        entry["mode"] = "finish"
        entry["polls_left"] = 3
    _runner(film_dir, [fake], tmp_path).run()
    assert len(fake.submitted) == 1
    assert JobStore(film_dir).load_all()[0]["state"] == "done"


def test_restart_resubmits_only_when_the_host_has_no_record(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1, mode=HANG)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    first = _runner(film_dir, [fake], tmp_path)
    thread = _run_until_submitted(first, fake)
    first.stop()
    thread.join(5)
    fake.forget()
    fake.finish_all()
    _runner(film_dir, [fake], tmp_path).run()
    assert len(fake.submitted) == 2
    job = JobStore(film_dir).load_all()[0]
    assert job["state"] == "done" and job["n"] == 1 and job["queue_ticket"] == fake.submitted[1]
    assert len(read_rows(tmp_path / "log" / "jobs.jsonl")) == 1


def test_a_finished_job_is_never_rendered_again(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    _runner(film_dir, [fake], tmp_path).run()
    _runner(film_dir, [fake], tmp_path).run()
    assert len(fake.submitted) == 1
    assert len(read_rows(tmp_path / "log" / "jobs.jsonl")) == 1


def test_timeout_leaves_the_job_queued_and_running_without_a_log_line(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1, mode=HANG)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    summary = _runner(film_dir, [fake], tmp_path, timeout_s=0.2).run()
    assert JobStore(film_dir).load_all()[0]["state"] == "running"
    assert read_rows(tmp_path / "log" / "jobs.jsonl") == []
    assert summary["still_running"] == 1


def test_two_hosts_five_jobs_both_work_and_numbers_are_unique(film_dir, sung_graph, fake_hosts, tmp_path):
    fakes = fake_hosts(2, polls_to_finish=3)
    keys = ["S01", "S02", "S02", "S02", "S03"]
    plan_batch(film_dir, [_request(key, sung_graph) for key in keys])
    summary = _runner(film_dir, fakes, tmp_path).run()
    jobs = JobStore(film_dir).load_all()
    assert all(job["state"] == "done" for job in jobs)
    assert sorted((job["key"], job["n"]) for job in jobs) == [("S01", 1), ("S02", 1), ("S02", 2), ("S02", 3),
                                                              ("S03", 1)]
    assert all(len(f.submitted) >= 1 for f in fakes), "both hosts took work"
    assert sum(len(f.submitted) for f in fakes) == 5
    assert len(read_rows(tmp_path / "log" / "jobs.jsonl")) == 5
    assert summary["made"] == 5
    assert summary["gpu_hours"] == pytest.approx(5 * 80 / 3600, rel=0.01)


def test_polling_waits_between_looks(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1, mode=HANG)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    _runner(film_dir, [fake], tmp_path, poll_s=0.1, timeout_s=0.55).run()
    assert 3 <= fake.history_polls() <= 8


def test_one_heavy_load_at_a_time_without_commit_headroom(film_dir, sung_graph, fake_hosts, tmp_path):
    tracker = Concurrency()
    fakes = fake_hosts(2, polls_to_finish=4, tracker=tracker)
    plan_batch(film_dir, [_request(key, sung_graph) for key in ("S01", "S02", "S03", "S04")])
    _runner(film_dir, fakes, tmp_path, gate=LoadGate(lambda: 30.0, wait_s=FAST)).run()
    assert tracker.peak == 1
    assert all(job["state"] == "done" for job in JobStore(film_dir).load_all())


def test_two_heavy_loads_when_commit_headroom_allows(film_dir, sung_graph, fake_hosts, tmp_path):
    tracker = Concurrency()
    fakes = fake_hosts(2, polls_to_finish=6, tracker=tracker)
    plan_batch(film_dir, [_request(key, sung_graph) for key in ("S01", "S02", "S03", "S04")])
    _runner(film_dir, fakes, tmp_path, gate=LoadGate(lambda: 100.0, wait_s=FAST)).run()
    assert tracker.peak == 2


def test_only_named_keys_run(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1)
    plan_batch(film_dir, [_request("S01", sung_graph), _request("S02", sung_graph)])
    _runner(film_dir, [fake], tmp_path).run(keys=["S02"])
    states = {job["key"]: job["state"] for job in JobStore(film_dir).load_all()}
    assert states == {"S01": "planned", "S02": "done"}


def test_an_input_deleted_after_planning_fails_that_job_only(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1)
    plan_batch(film_dir, [_request("S01", sung_graph), _request("S02", sung_graph)])
    (film_dir / "stills" / "S01.png").unlink()
    _runner(film_dir, [fake], tmp_path).run()
    states = {job["key"]: (job["state"], job["error"]) for job in JobStore(film_dir).load_all()}
    assert states["S01"][0] == "errored" and "S01.png" in states["S01"][1]
    assert states["S02"] == ("done", None)


def test_a_host_that_goes_down_hands_its_work_to_the_other(film_dir, sung_graph, fake_hosts, tmp_path):
    live, dead = fake_hosts(2)
    dead.down = True
    plan_batch(film_dir, [_request(key, sung_graph) for key in ("S01", "S02", "S03")])
    summary = _runner(film_dir, [dead, live], tmp_path).run()
    assert summary["made"] == 3
    assert len(live.submitted) == 3 and dead.submitted == []


def test_a_logging_failure_never_stops_a_render(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1)
    plan_batch(film_dir, [_request("S02", sung_graph)])
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    runner = Runner(film_dir, [fake.host], machine_log_path=blocked, poll_s=FAST, timeout_s=5.0,
                    gate=LoadGate(lambda: 100.0), say=lambda _: None)
    runner.run()
    assert JobStore(film_dir).load_all()[0]["state"] == "done"
