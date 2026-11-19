"""`shoot`: plan render jobs, then run them on the ComfyUI hosts, one worker per host on a shared queue.

Planning checks every request (graph, sizes, inputs on disk and inside the film, the refusals in `template`) and only
then writes job files, so a bad batch leaves nothing behind and makes no network call. Running picks up every job
that is not done: `planned` jobs go on the shared queue; a `running` job is first looked up on its own host,
collected if it finished, followed if ComfyUI still has it queued, and submitted again only if the host has no
record of it. An `unknown` job (sent, but the host's answer was lost) is looked up on its host by client id first and
is never handed to another host. A finished job is never rendered again. A job that outlives the timeout stays
queued in ComfyUI and `running` here, to be collected by the next run. Stopping (Ctrl-C) leaves submitted jobs to
finish in ComfyUI; the next run collects them.

The headroom floor is read before a heavy job waits at the load gate and again once the gate lets it start, less
what loads let start on other hosts have still to take. Under the floor the job goes back on the queue and that
host takes no more work in this run; jobs other hosts are following are never cut short by it.
"""

from __future__ import annotations

import hashlib
import queue
import random
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .comfy import ComfyClient, ComfyError, Outcome, check_upload_name, read_outcome
from .commit import headroom_gb
from .jobs import DONE, ERRORED, RUNNING, UNKNOWN, WAITING, JobStore
from .ledger import FILM_JOB_LOG, append_film_row, append_row, job_log_row, summarize, video_seconds
from .names import load_names
from .places import graph_file, input_file
from .sched import LoadGate
from .template import (TemplateError, check_request, check_size, fill, frames_for, is_file_slot, load_graph,
                       load_meta)

POLL_S = 3.0
TIMEOUT_S = 3600.0
MAX_BACKOFF_S = 30.0
ERROR_LIMIT = 300
EXTENSIONS = {"video": ".mp4", "still": ".png"}


@dataclass(frozen=True)
class Request:
    """One render to plan. `inputs` maps a file slot (opening_still, audio, image1...) to a project-relative path;
    `extra` holds other scalar placeholders (punch...). `kind` is what the film's ledger calls the job (vocal,
    mute, cutaway, still, edit, test); without it a vocal request is "vocal" and any other "cutaway". `graph` is a
    path inside the film folder (a relative one is read from there) or the kit's `workflows/` folder."""

    key: str
    graph: str
    wording: str
    inputs: Mapping[str, str]
    seconds: float
    vocal: bool = False
    fps: int = 24
    width: int = 1280
    height: int = 704
    extra: Mapping[str, Any] = field(default_factory=dict)
    kind: str | None = None
    seed: int | None = None


def _sha(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def _values(job: Mapping[str, Any], files: Mapping[str, str]) -> dict[str, Any]:
    return {**job.get("extra", {}), "wording": job["wording"], "seconds": job["seconds"], "frames": job["frames"],
            "fps": job["fps"], "width": job["width"], "height": job["height"], "seed": job["seed"],
            "save_as": job["save_as"], **files}


SEED_RANGE = 2 ** 32


def _seed(req: Request, rng: random.Random) -> int:
    """The request's own seed when it has one (a whole number the noise nodes take), else a fresh draw."""
    if req.seed is None:
        return rng.randrange(SEED_RANGE)
    if isinstance(req.seed, bool) or not isinstance(req.seed, int) or not 0 <= req.seed < SEED_RANGE:
        raise TemplateError(f"{req.key}: seed {req.seed!r} is not a whole number from 0 to {SEED_RANGE - 1}")
    return req.seed


def _save_as(film: str, key: str) -> str:
    save_as = f"{film}-{key}-{secrets.token_hex(3)}"
    try:
        check_upload_name(f"{save_as}-opening_still.png")
    except ValueError:
        raise TemplateError(f"{key}: the film name {film!r} cannot be part of an upload name (no quotes, line "
                            "breaks or folder parts)") from None
    return save_as


def _prepare(film_dir: Path, film: str, req: Request, rng: random.Random, silent_ok: bool) -> dict:
    graph_path = graph_file(film_dir, req.graph, f"{req.key}: graph")
    graph = load_graph(graph_path)
    meta = load_meta(graph_path)
    check_size(req.width, req.height, meta.size_step)
    for slot, rel in req.inputs.items():
        if not is_file_slot(slot):
            raise TemplateError(f"{req.key}: {slot} is not a file slot")
        if not input_file(film_dir, rel, f"{req.key}: input {slot}").is_file():
            raise TemplateError(f"{req.key}: input {slot} is missing: {rel}")
    record = {
        "film": film, "graph": str(graph_path), "graph_digest": _sha(graph_path), "host": None, "queue_ticket": None,
        "seed": _seed(req, rng), "save_as": _save_as(film, req.key),
        "frames": frames_for(req.seconds, req.fps, meta.frame_multiple), "fps": req.fps, "seconds": req.seconds,
        "width": req.width, "height": req.height, "wording": req.wording, "extra": dict(req.extra),
        "inputs": dict(req.inputs), "vocal": req.vocal, "kind": req.kind or ("vocal" if req.vocal else "cutaway"),
        "silent_ok": silent_ok, "commit_gb": meta.commit_gb,
        "extension": EXTENSIONS.get(meta.kind, ".mp4"), "submitted_at": None, "waited_s": None, "busy_s": None,
        "result_file": None, "error": None,
    }
    names = load_names(graph_path)
    record["names_from"] = names.found_at
    check_request(graph, meta, _values(record, req.inputs), vocal=req.vocal, silent_ok=silent_ok, names=names)
    return record


def plan_batch(film_dir: str | Path, requests: Iterable[Request], *, film: str | None = None,
               silent_ok: bool = False, rng: random.Random | None = None,
               extra_fields: Mapping[str, Any] | None = None) -> list[dict]:
    """Check every request, then write one `planned` job file per request. No network call. `extra_fields` are
    written into every job file (the gate-5 approval the batch was planned under)."""
    root = Path(film_dir)
    name = film or root.name
    chooser = rng or random.SystemRandom()
    prepared = []
    for req in requests:
        try:
            key = req.key if isinstance(req.key, str) else ""
            JobStore(root).folder(key)
        except ValueError as problem:
            raise TemplateError(str(problem)) from None
        prepared.append((req.key, {**_prepare(root, name, req, chooser, silent_ok), **(extra_fields or {})}))
    store = JobStore(root)
    return [store.create(key, record) for key, record in prepared]


class _HostDown(Exception):
    pass


class _HostRefused(Exception):
    """This host takes no more work in this run: commit headroom is under the floor."""


class Runner:
    def __init__(self, film_dir: str | Path, hosts: list[str], *, machine_log_path: str | Path, poll_s: float = POLL_S,
                 timeout_s: float = TIMEOUT_S, gate: LoadGate | None = None, say: Callable[[str], None] = print,
                 client_factory: Callable[[str], ComfyClient] | None = None,
                 job_log_path: str | Path | None = None, min_headroom_gb: float | None = None,
                 read_headroom: Callable[[], float | None] | None = None, allow_remote: bool = False) -> None:
        """`min_headroom_gb`: a heavy job (its graph's `commit_gb` over 0) is not started while commit headroom,
        less what loads let start on other hosts have still to take, is under this many GB, or unknown; the job
        stays planned and that host takes no more work in this run. The load gate holds a second load; this floor
        guards the first one too, against loads it cannot see (another ComfyUI's resident model, another program).
        `allow_remote`: hosts off this machine are accepted (`ComfyClient`)."""
        if not hosts:
            raise ValueError("no ComfyUI hosts given")
        self.film_dir = Path(film_dir)
        self.hosts = list(dict.fromkeys(hosts))
        self.machine_log_path = Path(machine_log_path)
        self.job_log_path = Path(job_log_path) if job_log_path else self.film_dir / FILM_JOB_LOG
        self.poll_s = poll_s
        self.timeout_s = timeout_s
        self.gate = gate or LoadGate()
        self.store = JobStore(self.film_dir)
        self._say = say
        factory = client_factory or (lambda host: ComfyClient(host, allow_remote=allow_remote))
        self._clients = {host: factory(host) for host in self.hosts}
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._ledger_lock = threading.Lock()
        self._rows: list[dict] = []
        self._gpu_names: dict[str, str] = {}
        self._in_flight: queue.Queue[dict] = queue.Queue()
        self.min_headroom_gb = min_headroom_gb
        self._read_headroom = read_headroom or (lambda: headroom_gb())
        self._refused_hosts: set[str] = set()

    # public ----------------------------------------------------------------------------------------------------
    def stop(self) -> None:
        self._stop.set()

    def run(self, keys: Iterable[str] | None = None) -> dict:
        wanted = set(keys) if keys is not None else None
        jobs = [j for j in self.store.load_all() if wanted is None or j["key"] in wanted]
        resume: dict[str, list[dict]] = {host: [] for host in self.hosts}
        for job in jobs:
            if job["state"] == WAITING:
                self._in_flight.put(job)
            elif job["state"] in (RUNNING, UNKNOWN) and job.get("host") in resume:
                resume[job["host"]].append(job)
            elif job["state"] in (RUNNING, UNKNOWN):
                self.say(f"{self._name(job)}: {job['state']} on {job.get('host')}, which is not in this run's hosts; "
                         "left")
        threads = [threading.Thread(target=self._worker, args=(host, resume[host]), daemon=True)
                   for host in self.hosts]
        for thread in threads:
            thread.start()
        try:
            while any(t.is_alive() for t in threads):
                for thread in threads:
                    thread.join(0.2)
        except KeyboardInterrupt:
            self.stop()
            self.say("stopping: jobs already submitted finish in ComfyUI and are collected by the next run")
            for thread in threads:
                thread.join(5)
        return self._summary(wanted)

    # workers ---------------------------------------------------------------------------------------------------
    def say(self, text: str) -> None:
        with self._lock:
            self._say(text)

    @staticmethod
    def _name(job: dict) -> str:
        return f"{job['key']} r{job['n']:03d}"

    def _worker(self, host: str, resume: list[dict]) -> None:
        try:
            for job in resume:
                if self._stop.is_set():
                    return
                self._resume(host, job)
            while not self._stop.is_set():
                try:
                    job = self._in_flight.get_nowait()
                except queue.Empty:
                    return
                self._fresh(host, job)
        except _HostDown as err:
            self.say(f"{host}: {err}; this host takes no more jobs in this run")
        except _HostRefused as err:
            self.say(f"{host}: {err}")
        except Exception as err:  # a worker must never die unseen; its job keeps its state for the next run
            self.say(f"{host}: worker stopped by an unexpected error: {err!r}")
            raise

    def _claim(self, host: str, job: dict) -> dict:
        """A job sent without a confirmed ticket: its ticket from the host by client id, or the job unchanged."""
        ticket = self._clients[host].find_client(job["client_id"])
        if ticket is None:
            return job
        self.say(f"{self._name(job)}: found on {host} by its client id")
        running = self.store.update(job, state=RUNNING, queue_ticket=ticket, error=None)
        self._film_row(running, host, "running", started=running.get("submitted_at"))
        return running

    def _resume(self, host: str, job: dict) -> None:
        client = self._clients[host]
        try:
            if not job.get("queue_ticket") and job.get("client_id"):
                job = self._claim(host, job)
            outcome = read_outcome(client.history(job["queue_ticket"]), job["extension"]) if job.get("queue_ticket") \
                else Outcome("awaiting")
            if outcome.state != "awaiting":
                self._finish(host, job, outcome)
                return
            if job.get("queue_ticket") and job["queue_ticket"] in client.queued_ids():
                self.say(f"{self._name(job)}: still queued on {host}; waiting for it")
                self.gate.note(host, job["commit_gb"])
                try:
                    self._track_job(host, job)
                finally:
                    self.gate.release(host)
                return
        except ComfyError as err:
            raise _HostDown(f"cannot look up {self._name(job)} ({err}); it stays {job['state']}") from err
        self.say(f"{self._name(job)}: {host} has no record of it; submitting it again")
        self._fresh(host, job)

    def _room_for(self, host: str, job: dict) -> bool:
        """Whether a heavy job may start on HOST by the headroom floor, less loads other hosts have still to take."""
        if self.min_headroom_gb is None or job.get("commit_gb", 0) <= 0:
            return True
        room = self._read_headroom()
        if room is not None:
            room -= self.gate.pending_gb(other_than=host)
        if room is not None and room >= self.min_headroom_gb:
            return True
        shown = "unknown" if room is None else f"{room:.1f} GB"
        with self._lock:
            self._refused_hosts.add(host)
        self._in_flight.put(job)
        raise _HostRefused(f"{self._name(job)} not started: commit headroom {shown} is under the floor of "
                           f"{self.min_headroom_gb:g} GB; it stays {job['state']} and this host takes no more work "
                           "in this run")

    def _fresh(self, host: str, job: dict) -> None:
        self._room_for(host, job)
        if not self.gate.acquire(host, job["commit_gb"], self._stop):
            return
        try:
            self._room_for(host, job)          # headroom may have fallen while the job waited at the gate
            submitted = self._enqueue(host, job)
            if submitted is not None:
                self._track_job(host, submitted)
        finally:
            self.gate.release(host)

    def _send_inputs(self, host: str, job: dict) -> tuple[dict, str]:
        """Check the job file's graph and inputs again (it may have been edited), upload the inputs, fill the
        graph. Returns the filled graph and its client id."""
        client = self._clients[host]
        graph_path = graph_file(self.film_dir, job["graph"], f"{job['key']}: graph")
        graph = load_graph(graph_path)
        meta = load_meta(graph_path)
        names = load_names(graph_path)
        sources = {slot: input_file(self.film_dir, rel, f"{job['key']}: input {slot}")
                   for slot, rel in job["inputs"].items()}
        files = {slot: client.send_file(source, f"{job['save_as']}-{slot}{source.suffix}")
                 for slot, source in sources.items()}
        values = _values(job, files)
        check_request(graph, meta, values, vocal=job["vocal"], silent_ok=job.get("silent_ok", False), names=names)
        return fill(graph, values, names), f"atomic-flix-{job['save_as']}"

    def _enqueue(self, host: str, job: dict) -> dict | None:
        try:
            filled, client_id = self._send_inputs(host, job)
        except TemplateError as err:
            self._fail(host, job, str(err))
            return None
        except (OSError, ValueError) as err:
            self._fail(host, job, f"an input could not be sent: {err}")
            return None
        except ComfyError as err:     # nothing is queued yet: the job may go to another host
            if err.status is None or err.status >= 500:
                self._in_flight.put(job)
                raise _HostDown(str(err)) from err
            self._fail(host, job, str(err))
            return None
        started = time.time()
        try:
            queue_ticket = self._clients[host].enqueue(filled, client_id=client_id)
        except ComfyError as err:
            if err.status is None:    # the graph may have been queued and the answer lost: never send it elsewhere
                self.store.update(job, state=UNKNOWN, host=host, queue_ticket=None, client_id=client_id,
                                  submitted_at=started, error=str(err)[:ERROR_LIMIT])
                raise _HostDown(f"{self._name(job)}: no answer to the enqueue ({err}); it may be queued, so it is "
                                f"left unknown and looked up on {host} by client id before it is sent again") from err
            if err.status >= 500:
                self._in_flight.put(job)
                raise _HostDown(str(err)) from err
            self._fail(host, job, str(err))
            return None
        self.say(f"{self._name(job)}: queued on {host}")
        running = self.store.update(job, state=RUNNING, host=host, queue_ticket=queue_ticket, client_id=client_id,
                                    submitted_at=started, graph_digest=_sha(job["graph"]), error=None)
        self._film_row(running, host, "running", started=started)
        return running

    def _track_job(self, host: str, job: dict) -> None:
        client = self._clients[host]
        deadline = time.monotonic() + self.timeout_s
        delay = self.poll_s
        while not self._stop.is_set():
            try:
                outcome = read_outcome(client.history(job["queue_ticket"]), job["extension"])
                delay = self.poll_s
            except ComfyError as err:
                outcome = Outcome("awaiting")
                delay = min(max(delay, self.poll_s) * 2, MAX_BACKOFF_S)
                self.say(f"{self._name(job)}: {host} did not answer ({err}); trying again in {delay:.0f} s")
            if outcome.state != "awaiting":
                self._finish(host, job, outcome)
                return
            if time.monotonic() >= deadline:
                self.say(f"{self._name(job)}: not finished after {self.timeout_s:.0f} s; left queued on {host}, "
                         "collected by the next run")
                return
            self._stop.wait(delay)

    # endings ---------------------------------------------------------------------------------------------------
    def _timing(self, job: dict, outcome: Outcome) -> tuple[float | None, float | None]:
        if outcome.start_ms is None:
            return None, None
        waited_s = None
        if job.get("submitted_at"):
            waited_s = round(max(0.0, outcome.start_ms / 1000 - job["submitted_at"]), 1)
        busy_s = round((outcome.end_ms - outcome.start_ms) / 1000, 1) if outcome.end_ms is not None else None
        return waited_s, busy_s

    @staticmethod
    def _span(job: dict, outcome: Outcome | None) -> tuple[float | None, float]:
        """(started, finished) as epoch seconds: ComfyUI's own timestamps when it gave them, else ours."""
        started = outcome.start_ms / 1000 if outcome and outcome.start_ms is not None else job.get("submitted_at")
        finished = outcome.end_ms / 1000 if outcome and outcome.end_ms is not None else time.time()
        if started is not None:
            finished = max(finished, started)
        return started, finished

    def _film_row(self, job: dict, host: str, state: str, *, started: float | None = None,
                  finished: float | None = None) -> None:
        row = job_log_row(job, host=host, state=state, started=started, finished=finished)
        with self._ledger_lock:
            written = append_film_row(self.job_log_path, row)
        if not written:
            self.say(f"film ledger: could not write {self.job_log_path}; the render is kept")

    def _finish(self, host: str, job: dict, outcome: Outcome) -> None:
        if outcome.state == "errored":
            waited_s, busy_s = self._timing(job, outcome)
            self._fail(host, job, outcome.error or "errored", waited_s=waited_s, busy_s=busy_s, outcome=outcome)
            return
        try:
            aim = self.store.result_path(job, job["extension"])
        except ValueError as err:
            self._fail(host, job, str(err), outcome=outcome)
            return
        try:
            data = self._clients[host].download(outcome.file)
        except ComfyError as err:
            raise _HostDown(f"could not fetch {self._name(job)}'s output ({err}); it stays running") from err
        temp = aim.with_name(aim.name + ".part")
        temp.write_bytes(data)
        temp.replace(aim)
        waited_s, busy_s = self._timing(job, outcome)
        done = self.store.update(job, state=DONE, waited_s=waited_s, busy_s=busy_s,
                                 result_file=aim.relative_to(self.film_dir).as_posix(), error=None)
        self._log(host, done, ok=True)
        started, finished = self._span(done, outcome)
        self._film_row(done, host, "done", started=started, finished=finished)
        self.say(f"{self._name(job)}: done on {host} -> {done['result_file']}"
                 + (f" ({busy_s:.0f} GPU s)" if busy_s is not None else ""))

    def _fail(self, host: str, job: dict, error: str, waited_s: float | None = None,
              busy_s: float | None = None, outcome: Outcome | None = None) -> None:
        errored = self.store.update(job, state=ERRORED, host=host, error=error, waited_s=waited_s, busy_s=busy_s)
        self._log(host, errored, ok=False)
        started, finished = self._span(errored, outcome)
        self._film_row(errored, host, "errored", started=started, finished=finished)
        self.say(f"{self._name(job)}: ERRORED on {host}: {error}")

    def _gpu_name(self, host: str) -> str:
        if host not in self._gpu_names:
            try:
                self._gpu_names[host] = self._clients[host].gpu(timeout_s=10)[0]
            except ComfyError:
                self._gpu_names[host] = "?"
        return self._gpu_names[host]

    def _log(self, host: str, job: dict, ok: bool) -> None:
        row = {
            "film": job.get("film"), "key": job["key"], "n": job["n"], "host": host, "gpu": self._gpu_name(host),
            "graph": Path(job["graph"]).name, "graph_digest": job.get("graph_digest"), "width": job["width"],
            "height": job["height"], "frames": job["frames"], "fps": job["fps"],
            "video_s": video_seconds(job), "seed": job["seed"], "waited_s": job.get("waited_s"),
            "busy_s": job.get("busy_s"),
            "wall_s": round(time.time() - job["submitted_at"], 1) if job.get("submitted_at") else None,
            "ok": ok, "error": None if ok else (job.get("error") or "")[:ERROR_LIMIT],
        }
        with self._lock:
            self._rows.append(row)
        with self._ledger_lock:
            written = append_row(self.machine_log_path, row)
        if not written:
            self.say(f"ledger: could not write {self.machine_log_path}; the render is kept")

    def _summary(self, wanted: set[str] | None) -> dict:
        jobs = [j for j in self.store.load_all() if wanted is None or j["key"] in wanted]
        summary = summarize(self._rows)
        return {**summary, "still_running": sum(1 for j in jobs if j["state"] == RUNNING),
                "not_started": sum(1 for j in jobs if j["state"] == WAITING),
                "unknown": sum(1 for j in jobs if j["state"] == UNKNOWN), "refused": bool(self._refused_hosts)}
