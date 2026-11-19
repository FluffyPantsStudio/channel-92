"""The runner writes the film's ledger (docs/job-log.md) that the comparison with the first film reads."""

from __future__ import annotations

import pytest

from atomic_flix.compare.ledger import read_job_log
from atomic_flix.runner.sched import LoadGate
from atomic_flix.runner.shoot import Request, Runner, plan_batch
from fake_comfyui import ERROR

FAST = 0.02


def _runner(film_dir, hosts, tmp_path) -> Runner:
    return Runner(film_dir, [h.host for h in hosts], machine_log_path=tmp_path / "log" / "jobs.jsonl", poll_s=FAST,
                  timeout_s=10.0, gate=LoadGate(lambda: 100.0), say=lambda _: None)


def _sung(key, graph) -> Request:
    return Request(key=key, graph=str(graph), wording=f"Frankie sings {key}", seconds=9, vocal=True,
                   inputs={"opening_still": f"stills/{key}.png", "audio": f"plan/{key}.voice-soft.wav"})


def test_every_finished_render_gets_one_ledger_entry_in_the_documented_shape(film_dir, sung_graph, silent_graph,
                                                                            fake_hosts, tmp_path):
    (fake,) = fake_hosts(1, gpu_ms=80_000)
    plate = Request(key="S03", graph=str(silent_graph), wording="the tub walks", seconds=5, vocal=False,
                    kind="cutaway", inputs={"opening_still": "stills/S03.png"})
    plan_batch(film_dir, [_sung("S02", sung_graph), plate])
    _runner(film_dir, [fake], tmp_path).run()

    job_log = read_job_log(film_dir / "job-log.jsonl")          # strict: a bad line raises
    logged = {entry.job_id: entry for entry in job_log.logged}
    assert set(logged) == {"S02-r001", "S03-r001"}
    sung, cut = logged["S02-r001"], logged["S03-r001"]
    assert (sung.kind, sung.shot, sung.state) == ("vocal", "S02", "done")
    assert (cut.kind, cut.shot, cut.state) == ("cutaway", "S03", "done")
    assert sung.gpu_seconds == pytest.approx(80.0)
    assert sung.host == fake.host and isinstance(sung.seed, int)
    assert sung.video_seconds == pytest.approx(217 / 24, abs=1e-3)
    assert sung.started and sung.finished and sung.wall_seconds == pytest.approx(80.0, abs=1.0)


def test_a_failed_render_is_in_the_ledger_as_failed(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1, mode=ERROR)
    plan_batch(film_dir, [_sung("S02", sung_graph)])
    _runner(film_dir, [fake], tmp_path).run()
    (entry,) = read_job_log(film_dir / "job-log.jsonl").logged
    assert entry.state == "errored" and entry.finished is not None


def test_the_kind_defaults_from_the_vocal_flag(film_dir, sung_graph):
    (job,) = plan_batch(film_dir, [_sung("S02", sung_graph)])
    assert job["kind"] == "vocal"
