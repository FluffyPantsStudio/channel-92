"""Runner fixes from the 2026-11-19 review: the headroom floor, ledger writes from many threads, an unconfirmed
enqueue, job keys and paths, and the HTTP client's limits."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from atomic_flix.runner import ledger as ledger_mod
from atomic_flix.runner.comfy import ComfyClient, ComfyError
from atomic_flix.runner.jobs import JobStore
from atomic_flix.runner.names import KIT_MAPS
from atomic_flix.runner.sched import LoadGate
from atomic_flix.runner.shoot import Request, Runner, plan_batch
from atomic_flix.runner.template import TemplateError, load_meta
from runner_samples import SUNG_GRAPH, write_graph

FAST = 0.02


def _request(key: str, graph, **extra) -> Request:
    inputs = {"opening_still": f"stills/{key}.png", "audio": f"plan/{key}.voice-soft.wav"}
    inputs.update(extra.pop("inputs", {}))
    return Request(key=key, graph=str(graph), wording=f"Nova sings {key}", inputs=inputs, seconds=9, vocal=True,
                   **extra)


def _runner(film_dir, hosts, tmp_path, **kwargs) -> Runner:
    options = {"poll_s": FAST, "timeout_s": 10.0, "gate": LoadGate(lambda: 100.0), "say": lambda _: None}
    options.update(kwargs)
    return Runner(film_dir, [h.host for h in hosts], machine_log_path=tmp_path / "log" / "jobs.jsonl", **options)


# A2: the floor is read again once the gate lets the job start ---------------------------------------------------

class _WaitingGate:
    """A gate that makes the job wait, during which headroom falls."""

    def __init__(self, on_wait) -> None:
        self.on_wait = on_wait

    def acquire(self, host, commit_gb, stop) -> bool:
        self.on_wait()
        return True

    def release(self, host) -> None:
        return None

    def note(self, host, commit_gb) -> None:
        return None

    def pending_gb(self, other_than=None) -> float:
        return 0.0


def test_the_floor_is_checked_again_after_waiting_for_the_gate(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1)
    plan_batch(film_dir, [_request("S01", sung_graph)])
    room = {"gb": 80.0}
    runner = _runner(film_dir, [fake], tmp_path, gate=_WaitingGate(lambda: room.update(gb=20.0)),
                     min_headroom_gb=45, read_headroom=lambda: room["gb"])
    summary = runner.run()
    assert fake.submitted == [], "headroom fell under the floor while the job waited"
    assert summary["refused"] is True
    assert JobStore(film_dir).load_all()[0]["state"] == "planned"


# A10: one host's refusal never stops another host following its running job ---------------------------------------

def test_a_floor_refusal_on_one_host_leaves_the_other_hosts_job_running_to_done(film_dir, sung_graph, fake_hosts,
                                                                                tmp_path):
    fakes = fake_hosts(2, polls_to_finish=10)
    plan_batch(film_dir, [_request("S01", sung_graph), _request("S02", sung_graph)])
    owner: list[int] = []
    lock = threading.Lock()

    def room() -> float:
        with lock:
            if not owner:
                owner.append(threading.get_ident())
            return 100.0 if owner[0] == threading.get_ident() else 0.0

    summary = _runner(film_dir, fakes, tmp_path, min_headroom_gb=45, read_headroom=room).run()
    states = {job["key"]: job["state"] for job in JobStore(film_dir).load_all()}
    assert summary["refused"] is True
    assert "running" not in states.values(), states
    assert sorted(states.values()).count("done") >= 1


# A11: ledger lines are whole however many threads write them -----------------------------------------------------

def test_many_threads_appending_to_a_ledger_leave_every_line_whole(tmp_path):
    path = tmp_path / "log" / "jobs.jsonl"
    film = tmp_path / "job-log.jsonl"
    payload = "x" * 40_000

    def write(n: int) -> None:
        for i in range(15):
            ledger_mod.append_row(path, {"key": f"S{n:02d}", "i": i, "error": payload})
            ledger_mod.append_film_row(film, {"job_id": f"S{n:02d}-{i}", "note": payload})

    threads = [threading.Thread(target=write, args=(n,)) for n in range(24)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for aim in (path, film):
        lines = aim.read_bytes().split(b"\n")
        assert lines[-1] == b""
        rows = [json.loads(line) for line in lines[:-1]]
        assert len(rows) == 24 * 15


def test_the_runner_never_writes_two_ledger_lines_at_once(film_dir, sung_graph, fake_hosts, tmp_path, monkeypatch):
    fakes = fake_hosts(2)
    plan_batch(film_dir, [_request(key, sung_graph) for key in ("S01", "S02", "S03", "S04")])
    now = {"in": 0, "peak": 0}
    lock = threading.Lock()

    def slow_write(*_args) -> bool:
        with lock:
            now["in"] += 1
            now["peak"] = max(now["peak"], now["in"])
        time.sleep(0.03)
        with lock:
            now["in"] -= 1
        return True

    monkeypatch.setattr("atomic_flix.runner.shoot.append_row", slow_write)
    monkeypatch.setattr("atomic_flix.runner.shoot.append_film_row", slow_write)
    _runner(film_dir, fakes, tmp_path).run()
    assert now["peak"] == 1


# A12: an enqueue that may have been accepted is never sent again before the host is asked ---------------------------

class _LostAnswer(ComfyClient):
    """Queues the graph, then loses ComfyUI's answer, as a timed-out read does."""

    def enqueue(self, graph: dict, client_id: str) -> str:
        super().enqueue(graph, client_id)
        raise ComfyError(f"{self.host}/prompt: timed out")


def test_an_unconfirmed_enqueue_is_left_unknown_then_found_by_its_client_id(film_dir, sung_graph, fake_hosts,
                                                                            tmp_path):
    fakes = fake_hosts(2, polls_to_finish=3)
    plan_batch(film_dir, [_request("S01", sung_graph)])
    _runner(film_dir, fakes, tmp_path, client_factory=_LostAnswer).run()
    (job,) = JobStore(film_dir).load_all()
    assert job["state"] == "unknown" and job["host"] in {f.host for f in fakes}
    assert sum(len(f.submitted) for f in fakes) == 1, "never handed to the other host"

    summary = _runner(film_dir, fakes, tmp_path).run()
    (job,) = JobStore(film_dir).load_all()
    assert job["state"] == "done" and summary["made"] == 1
    assert sum(len(f.submitted) for f in fakes) == 1, "found on its host by client id, not sent again"


def test_an_unknown_job_the_host_never_got_is_sent_again(film_dir, sung_graph, fake_hosts, tmp_path):
    (fake,) = fake_hosts(1)
    plan_batch(film_dir, [_request("S01", sung_graph)])
    _runner(film_dir, [fake], tmp_path, client_factory=_LostAnswer).run()
    fake.forget()
    _runner(film_dir, [fake], tmp_path).run()
    (job,) = JobStore(film_dir).load_all()
    assert job["state"] == "done" and len(fake.submitted) == 2


# B3: job keys, result names and every path stay inside the film -------------------------------------------------

@pytest.mark.parametrize("key", ["../up", "a/b", "a\\b", "..", "S 01", "S01\n", "", "-S01", "S01.mp4"])
def test_unsafe_job_keys_are_refused(film_dir, key):
    with pytest.raises(ValueError):
        JobStore(film_dir).create(key, {})


def test_a_result_must_have_a_known_extension(film_dir):
    store = JobStore(film_dir)
    job = store.create("S01", {})
    assert store.result_path(job, ".mp4").parent == film_dir / "renders" / "S01"
    for suffix in (".exe", ".bat", ".mp4/../../x", ""):
        with pytest.raises(ValueError):
            store.result_path(job, suffix)


def test_a_job_file_whose_key_was_changed_is_refused(film_dir):
    store = JobStore(film_dir)
    job = store.create("S01", {})
    path = film_dir / "renders" / "S01" / "r001.job.json"
    path.write_text(json.dumps({**job, "key": "../../evil"}), encoding="utf-8")
    with pytest.raises(ValueError, match="r001.job.json"):
        store.load_all()


def test_an_input_outside_the_film_is_refused_with_its_path(film_dir, sung_graph, tmp_path):
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"not for upload")
    for given in ("../secret.png", str(outside)):
        with pytest.raises(TemplateError, match="secret.png"):
            plan_batch(film_dir, [_request("S01", sung_graph, inputs={"opening_still": given})])
    assert not (film_dir / "renders").exists()


def test_a_graph_outside_the_film_and_the_kit_is_refused(film_dir, tmp_path):
    stray = write_graph(tmp_path / "elsewhere", "sung.json", SUNG_GRAPH,
                        {"needs": ["wording", "opening_still", "audio"], "commit_gb": 40})
    with pytest.raises(TemplateError, match="elsewhere"):
        plan_batch(film_dir, [_request("S01", stray)])


def test_the_kit_graph_folder_is_allowed(film_dir):
    assert KIT_MAPS.is_dir()
    with pytest.raises(TemplateError) as caught:
        plan_batch(film_dir, [_request("S01", KIT_MAPS / "no-such-graph.json")])
    assert "outside" not in str(caught.value)


def test_a_job_file_pointing_outside_after_planning_fails_without_an_upload(film_dir, sung_graph, fake_hosts,
                                                                           tmp_path):
    (fake,) = fake_hosts(1)
    (job,) = plan_batch(film_dir, [_request("S01", sung_graph)])
    outside = tmp_path / "secret.wav"
    outside.write_bytes(b"private")
    path = film_dir / "renders" / "S01" / "r001.job.json"
    path.write_text(json.dumps({**job, "inputs": {**job["inputs"], "audio": str(outside)}}), encoding="utf-8")
    _runner(film_dir, [fake], tmp_path).run()
    (done,) = JobStore(film_dir).load_all()
    assert done["state"] == "errored" and "secret.wav" in done["error"]
    assert fake.uploads == {}


def test_a_film_name_that_cannot_be_an_upload_name_is_refused(film_dir, sung_graph):
    with pytest.raises(TemplateError, match="name"):
        plan_batch(film_dir, [_request("S01", sung_graph)], film='bad"name')


# B4: the HTTP client takes host:port only, local unless allowed, and caps what it reads ---------------------------

@pytest.mark.parametrize("host", ["127.0.0.1:8188", "localhost:8189", "[::1]:8188"])
def test_local_hosts_are_taken(host):
    assert ComfyClient(host).host == host


@pytest.mark.parametrize("host", ["127.0.0.1", "http://127.0.0.1:8188", "127.0.0.1:8188/x", "127.0.0.1:99999",
                                  "user@127.0.0.1:8188", "127.0.0.1:81 88", ""])
def test_anything_but_host_and_port_is_refused(host):
    with pytest.raises(ValueError):
        ComfyClient(host)


def test_a_remote_host_needs_allow_remote():
    with pytest.raises(ValueError, match="allow-remote"):
        ComfyClient("gpu-box.lan:8188")
    assert ComfyClient("gpu-box.lan:8188", allow_remote=True).host == "gpu-box.lan:8188"


def test_answers_over_the_cap_are_refused(fake_hosts):
    (fake,) = fake_hosts(1)
    with pytest.raises(ComfyError, match="limit"):
        ComfyClient(fake.host, json_limit=64).system_stats()
    with pytest.raises(ComfyError, match="limit"):
        ComfyClient(fake.host, download_limit=8).download({"filename": "a_long_file_name.mp4", "type": "output"})
    assert ComfyClient(fake.host).system_stats()["devices"]


@pytest.mark.parametrize("name", ['a"b.png', "a\rb.png", "a\nb.png", "a'b.png"])
def test_upload_names_with_quotes_or_line_breaks_are_refused(fake_hosts, tmp_path, name):
    (fake,) = fake_hosts(1)
    source = tmp_path / "x.png"
    source.write_bytes(b"png")
    with pytest.raises(ValueError):
        ComfyClient(fake.host).send_file(source, name)
    assert fake.uploads == {}


# A6: a graph that does not say what it loads is not taken as free --------------------------------------------------

def test_a_graph_without_a_sidecar_counts_as_a_heavy_load(tmp_path):
    graph = write_graph(tmp_path, "bare.json", SUNG_GRAPH)
    assert load_meta(graph).commit_gb == 30.0


def test_a_sidecar_without_commit_gb_counts_as_heavy_unless_marked_light(tmp_path):
    heavy = write_graph(tmp_path, "heavy.json", SUNG_GRAPH, {"frame_multiple": 8})
    light = write_graph(tmp_path, "light.json", SUNG_GRAPH, {"frame_multiple": 8, "light": True})
    assert load_meta(heavy).commit_gb == 30.0
    assert load_meta(light).commit_gb == 0.0


def test_commit_gb_zero_without_light_is_refused(tmp_path):
    graph = write_graph(tmp_path, "zero.json", SUNG_GRAPH, {"commit_gb": 0})
    with pytest.raises(TemplateError, match="light"):
        load_meta(graph)


# A14: one size rule, shared with the control clips ------------------------------------------------------------------

def test_a_graph_that_takes_a_control_video_defaults_to_the_control_video_step(tmp_path):
    graph = dict(SUNG_GRAPH, **{"60": {"class_type": "LoadVideo", "inputs": {"video": "$video"}}})
    with_video = write_graph(tmp_path, "union.json", graph, {"commit_gb": 40})
    without = write_graph(tmp_path, "plain.json", SUNG_GRAPH, {"commit_gb": 40})
    assert load_meta(with_video).size_step == 128
    assert load_meta(without).size_step == 32


def test_the_runner_and_the_control_clips_use_one_size_check():
    from atomic_flix import sizes
    from atomic_flix.runner import template
    from atomic_flix.scenes import guides
    assert template.check_size.__module__ == "atomic_flix.runner.template"
    for module in (template, guides):
        assert module.check_multiple is sizes.check_multiple
    assert guides.SIZE_RULES["ltx"] == sizes.CONTROL_VIDEO_STEP == 128
