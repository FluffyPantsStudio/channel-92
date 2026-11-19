"""Job files: one JSON file per render, `renders/<key>/r007.job.json`, written before it is submitted.

A job moves through `planned`, `running`, `done` or `errored`; the file is rewritten whole on every change (write to a
temporary file, then replace), so a crash never leaves half a record. Render numbers are per shot key and never
reused: a small counter file remembers the highest number handed out, and a number is claimed by creating its job
file exclusively, so two runners on one project cannot take the same one.

A job is `unknown` when it was sent to a host that never confirmed it queued the graph (the answer was lost): it is
looked up on that host by its client id before it may be sent anywhere again.

A shot key is letters, digits, `-` and `_` (SAFE_KEY), a result's extension one of RESULT_SUFFIXES, and every path
built from a job file stays inside the film's `renders/` folder; a job file that breaks this is refused when read.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from ..formats import tag

WAITING = "planned"
RUNNING = "running"
DONE = "done"
ERRORED = "errored"
UNKNOWN = "unknown"
STATES = (WAITING, RUNNING, DONE, ERRORED, UNKNOWN)

JOB_NAME = re.compile(r"r([0-9]+)\.job\.json")
SAFE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
RESULT_SUFFIXES = (".mp4", ".webm", ".png", ".jpg", ".wav", ".json")
COUNTER = "last-number.txt"
_COUNTER_LOCK = threading.Lock()
REPLACE_TRIES = 20
REPLACE_WAIT_S = 0.05


def _dump(record: dict) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False) + "\n"


def check_key(key: object) -> str:
    """KEY if it is a usable shot key (letters, digits, - and _, starting with a letter or digit); else ValueError."""
    if not isinstance(key, str) or not SAFE_KEY.fullmatch(key):
        raise ValueError(f"not a usable shot key: {key!r} (letters, digits, - and _ only)")
    return key


class JobStore:
    """Reads and writes the job files of one film project."""

    def __init__(self, film_dir: str | Path) -> None:
        self.film_dir = Path(film_dir)
        self.takes_dir = self.film_dir / "renders"

    def folder(self, key: str) -> Path:
        return self.takes_dir / check_key(key)

    @staticmethod
    def _number(job: dict) -> int:
        n = job.get("n")
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise ValueError(f"not a render number: {n!r}")
        return n

    def job_path(self, job: dict) -> Path:
        return self.folder(job["key"]) / f"r{self._number(job):03d}.job.json"

    def result_path(self, job: dict, suffix: str) -> Path:
        """Where a job's result is written; refuses an extension outside RESULT_SUFFIXES."""
        if suffix not in RESULT_SUFFIXES:
            raise ValueError(f"not a result extension: {suffix!r} (one of {', '.join(RESULT_SUFFIXES)})")
        aim = self.folder(job["key"]) / f"r{self._number(job):03d}{suffix}"
        if self.takes_dir.resolve() not in aim.resolve().parents:
            raise ValueError(f"{aim} is outside {self.takes_dir}")
        return aim

    @staticmethod
    def _counter_value(counter: Path) -> int:
        """The counter's number; 0 when it is missing or unreadable (it only guards numbers of deleted files)."""
        try:
            text = counter.read_text(encoding="utf-8").strip() if counter.exists() else ""
        except OSError:
            return 0
        return int(text) if text.isdigit() else 0

    def _highest(self, folder: Path) -> int:
        seen = [int(m.group(1)) for p in folder.glob("r*") if (m := re.match(r"r([0-9]+)\.", p.name))]
        with _COUNTER_LOCK:
            seen.append(self._counter_value(folder / COUNTER))
        return max(seen, default=0)

    def create(self, key: str, fields: dict[str, Any]) -> dict:
        """Claim the next number for `key` and write its job file in state `planned`."""
        folder = self.folder(key)
        folder.mkdir(parents=True, exist_ok=True)
        n = self._highest(folder) + 1
        while True:
            record = {"format": tag("job"), **fields, "key": key, "n": n, "state": WAITING}
            path = folder / f"r{n:03d}.job.json"
            try:
                handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                n += 1
                continue
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                out.write(_dump(record))
            self._raise_counter(folder, n)
            return record

    def _raise_counter(self, folder: Path, n: int) -> None:
        """Remember `n` as handed out. The job file already holds the number; this only covers deleted files."""
        counter = folder / COUNTER
        with _COUNTER_LOCK:
            if n > self._counter_value(counter):
                self._replace(counter, f"{n}\n")

    @staticmethod
    def _replace(path: Path, text: str) -> None:
        """Write `text` to a temporary file, then put it in place. Windows refuses a replace while another process
        (a reader, a virus scanner) has the file open, so a refused replace is tried again for a moment."""
        temp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        temp.write_text(text, encoding="utf-8")
        for try_no in range(REPLACE_TRIES):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if try_no == REPLACE_TRIES - 1:
                    raise
                time.sleep(REPLACE_WAIT_S)

    def save(self, job: dict) -> dict:
        self._replace(self.job_path(job), _dump(job))
        return job

    def update(self, job: dict, **changes: Any) -> dict:
        """A new record with `changes` applied, written to the job's file."""
        if "state" in changes and changes["state"] not in STATES:
            raise ValueError(f"unknown job state {changes['state']!r}")
        return self.save({**job, **changes})

    @staticmethod
    def load(path: str | Path) -> dict:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def _checked(path: Path, job: object) -> dict:
        """A job read from PATH, refused unless its key, number, extension and state fit where it lies."""
        named = JOB_NAME.fullmatch(path.name)
        problem = None
        if not isinstance(job, dict):
            problem = "not a JSON object"
        elif job.get("key") != path.parent.name or not SAFE_KEY.fullmatch(str(job.get("key"))):
            problem = f"its key {job.get('key')!r} is not its folder's name {path.parent.name!r}"
        elif named is None or job.get("n") != int(named.group(1)):
            problem = f"its number {job.get('n')!r} is not the file's"
        elif job.get("extension") is not None and job.get("extension") not in RESULT_SUFFIXES:
            problem = f"its extension {job.get('extension')!r} is not one of {', '.join(RESULT_SUFFIXES)}"
        elif job.get("state") not in STATES:
            problem = f"its state {job.get('state')!r} is not one of {', '.join(STATES)}"
        if problem:
            raise ValueError(f"{path}: refused: {problem}")
        return job

    def load_all(self) -> list[dict]:
        if not self.takes_dir.exists():
            return []
        jobs = [self._checked(p, self.load(p)) for p in self.takes_dir.glob("*/r*.job.json")
                if JOB_NAME.fullmatch(p.name)]
        return sorted(jobs, key=lambda job: (job["key"], job["n"]))
