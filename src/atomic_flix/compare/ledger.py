"""Read the runner's ledger: one JSON object per line, nine fixed fields (docs/job-log.md).

A job may be written more than once (when it starts and when it ends); the last line for a job id wins.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..gates import parse_time

FIELDS: tuple[str, ...] = ("job_id", "kind", "shot", "host", "seed", "gpu_seconds", "started", "finished", "state")
STATES: tuple[str, ...] = ("planned", "running", "done", "errored")
ENDED = ("done", "errored")


class JobLogError(ValueError):
    """A ledger line that does not follow docs/job-log.md."""


@dataclass(frozen=True)
class JobLogRow:
    job_id: str
    kind: str
    shot: str | None
    host: str | None
    seed: int | None
    gpu_seconds: float | None
    started: str | None
    finished: str | None
    state: str
    video_seconds: float | None = None

    @property
    def wall_seconds(self) -> float | None:
        """Finished minus started, when both are known."""
        if not self.started or not self.finished:
            return None
        return (parse_time(self.finished) - parse_time(self.started)).total_seconds()


@dataclass(frozen=True)
class JobLog:
    logged: tuple[JobLogRow, ...]
    problems: tuple[str, ...] = ()


def _text_or_none(data: dict[str, Any], name: str, *, empty_ok: bool = False) -> str | None:
    value = data[name]
    if value is None:
        return None
    if not isinstance(value, str) or (not empty_ok and not value.strip()):
        raise JobLogError(f"{name} must be text or null, got {value!r}")
    return value


def _seconds(data: dict[str, Any], name: str) -> float | None:
    value = data.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise JobLogError(f"{name} must be a number of seconds, 0 or more, or null, got {value!r}")
    return float(value)


def _time(data: dict[str, Any], name: str) -> str | None:
    value = _text_or_none(data, name)
    if value is not None:
        try:
            parse_time(value)
        except ValueError:
            raise JobLogError(f"{name} must be an ISO 8601 time, got {value!r}") from None
    return value


def _entry(data: dict[str, Any]) -> JobLogRow:
    missing = [name for name in FIELDS if name not in data]
    if missing:
        raise JobLogError(f"missing field {', '.join(missing)}")
    job_id, kind = data["job_id"], data["kind"]
    for name, value in (("job_id", job_id), ("kind", kind)):
        if not isinstance(value, str) or not value.strip():
            raise JobLogError(f"{name} must be non-empty text, got {value!r}")
    seed = data["seed"]
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise JobLogError(f"seed must be a whole number or null, got {seed!r}")
    state = data["state"]
    if state not in STATES:
        raise JobLogError(f"state must be one of {', '.join(STATES)}, got {state!r}")
    started, finished = _time(data, "started"), _time(data, "finished")
    if state in ENDED and finished is None:
        raise JobLogError(f"finished must be set on a {state} job")
    if state == "running" and started is None:
        raise JobLogError("started must be set on a running job")
    if started and finished and parse_time(finished) < parse_time(started):
        raise JobLogError(f"finished {finished} is before started {started}")
    return JobLogRow(job_id=job_id, kind=kind, shot=_text_or_none(data, "shot"),
                       host=_text_or_none(data, "host", empty_ok=True), seed=seed,
                       gpu_seconds=_seconds(data, "gpu_seconds"), started=started, finished=finished,
                       state=state, video_seconds=_seconds(data, "video_seconds"))


def parse_line(text: str) -> JobLogRow:
    """One ledger line as an entry; JobLogError says what is wrong with it."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as problem:
        raise JobLogError(f"not JSON ({problem.msg})") from None
    if not isinstance(data, dict):
        raise JobLogError("not a JSON object")
    return _entry(data)


def read_job_log(path: Path, *, strict: bool = True) -> JobLog:
    """Every job in the ledger at PATH, in the order each first appeared, holding its last line.

    A missing file is an empty ledger. A bad line raises JobLogError naming its line number; with strict=False
    the good lines are kept and each bad one is listed in `problems`.
    """
    path = Path(path)
    if not path.is_file():
        return JobLog(logged=())
    jobs: dict[str, JobLogRow] = {}
    problems: list[str] = []
    with path.open("rb") as lines:
        for number, raw in enumerate(lines, start=1):
            if not raw.strip():
                continue
            try:
                try:
                    line = raw.decode("utf-8")
                except UnicodeDecodeError as torn:
                    raise JobLogError(f"not UTF-8 text (byte {torn.start}); a torn or mixed write") from None
                entry = parse_line(line)
            except JobLogError as problem:
                message = f"line {number}: {problem}"
                if strict:
                    raise JobLogError(f"{path}: {message}") from None
                problems.append(message)
                continue
            jobs[entry.job_id] = entry
    return JobLog(logged=tuple(jobs.values()), problems=tuple(problems))
