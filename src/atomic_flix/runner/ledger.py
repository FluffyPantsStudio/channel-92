"""The job ledgers.

`log/jobs.jsonl` (the machine's log), one JSON line per finished or errored render: the time, film, shot key, host,
GPU, graph and its hash, size, frames, video seconds, seed, the seconds the graph waited in ComfyUI's queue and ran
on the GPU (from ComfyUI's own timestamps), wall seconds, and ok or the first 300 characters of the error.

`<film>/job-log.jsonl` (the film's ledger, docs/job-log.md), read by the comparison with the first film: one line
when a job is submitted and one when it ends, the last line per job id winning.

Writing either never stops a render: a errored write is reported and the render goes on. Each line goes out in one
write on an append-mode handle, one writer at a time in this process, so threads never interleave lines. Two runner
processes on one ledger are not serialised against each other (Windows has no atomic append through this call).
"""

from __future__ import annotations

import json
import os
import statistics
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ..formats import tag

FILM_JOB_LOG = "job-log.jsonl"


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="milliseconds")


def video_seconds(job: dict) -> float | None:
    """The length of the video a job makes; None for a still (a picture has no video seconds, and counting its
    frames would put picture time into the GPU seconds per video second)."""
    if job.get("extension") == ".png" or not job.get("frames") or not job.get("fps"):
        return None
    return round(job["frames"] / job["fps"], 3)


def job_log_row(job: dict, *, host: str | None, state: str, started: float | None = None,
                    finished: float | None = None) -> dict:
    """One line of the film's ledger for a job record (times as epoch seconds)."""
    ended = state in ("done", "errored")
    video = video_seconds(job) if ended else None
    return {"format": tag("job-log-row"), "job_id": f"{job['key']}-r{job['n']:03d}", "kind": job.get("kind") or
            ("vocal" if job.get("vocal") else "cutaway"), "shot": job["key"], "host": host, "seed": job.get("seed"),
            "gpu_seconds": job.get("busy_s") if ended else None, "started": _iso(started),
            "finished": _iso(finished) if ended else None, "state": state, "video_seconds": video}


_APPEND_LOCK = threading.Lock()
_APPEND_FLAGS = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)


def _append_line(path: str | Path, line: str) -> bool:
    """Append LINE and a newline with one write on an append-mode handle, one writer in this process at a time, so
    lines from several threads never interleave. False (never an exception) if it could not be written whole."""
    data = (line + "\n").encode("utf-8")
    try:
        aim = Path(path)
        aim.parent.mkdir(parents=True, exist_ok=True)
        with _APPEND_LOCK:
            handle = os.open(aim, _APPEND_FLAGS, 0o644)
            try:
                return os.write(handle, data) == len(data)
            finally:
                os.close(handle)
    except OSError:
        return False


def append_film_row(path: str | Path, row: dict) -> bool:
    """Append one film-ledger line; False (never an exception) if it could not be written."""
    return _append_line(path, json.dumps(row, ensure_ascii=False))


def append_row(path: str | Path, row: dict) -> bool:
    """Append one row with the current time; False (never an exception) if it could not be written."""
    line = json.dumps({"format": tag("machine-log-row"), "time": time.strftime("%Y-%m-%dT%H:%M:%S"), **row}, ensure_ascii=False)
    return _append_line(path, line)


def read_rows(path: str | Path) -> list[dict]:
    """Every readable row; a damaged line is skipped."""
    aim = Path(path)
    if not aim.is_file():
        return []
    rows = []
    for line in aim.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _measured(rows: Iterable[dict]) -> list[dict]:
    return [r for r in rows if r.get("ok") and (r.get("busy_s") or 0) > 0 and (r.get("video_s") or 0) > 0]


def summarize(rows: Iterable[dict]) -> dict:
    """Renders, failures, GPU hours and GPU seconds per video second over these rows. GPU hours count every finished
    job with a measured time (stills too); the rate per video second counts only jobs that made video."""
    rows = list(rows)
    measured = _measured(rows)
    busy_s = sum(r["busy_s"] for r in measured)
    video_s = sum(r["video_s"] for r in measured)
    all_gpu_s = sum(r["busy_s"] for r in rows if r.get("ok") and (r.get("busy_s") or 0) > 0)
    return {
        "made": sum(1 for r in rows if r.get("ok")),
        "errored": sum(1 for r in rows if not r.get("ok")),
        "gpu_hours": all_gpu_s / 3600,
        "gpu_s_per_video_s": busy_s / video_s if video_s else None,
        "median_gpu_s": statistics.median(r["busy_s"] for r in measured) if measured else None,
    }
