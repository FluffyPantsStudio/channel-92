"""The load gate: one heavy model load at a time unless commit headroom says a second one fits.

Each job carries its graph's `commit_gb` (from the sidecar). A job may start when no other host holds a load, or when
commit headroom is at least its `commit_gb` plus a margin (about 45 GB for a 40 GB LTX-class load, as measured on our
machine). Unknown headroom counts as none. A graph with `commit_gb` 0 is never held.

A load let start does not take its memory at once: the model is read for a while after the job is queued. Until
headroom has fallen by the load's own size since it was let start (it is then resident), or until it is released,
its `commit_gb` is taken off the headroom read for every other host. Without this, two 40 GB loads on 60 GB of
headroom would both start, each reading 60 GB free.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from .commit import headroom_gb

MARGIN_GB = 5.0
WAIT_S = 3.0


def headroom_floor(jobs: Iterable[Mapping], override: float | None = None) -> float | None:
    """The commit-headroom floor for a run (`Runner(min_headroom_gb=...)`): OVERRIDE when given (0 or less turns the
    floor off), else the heaviest job's `commit_gb` plus MARGIN_GB; None when no job is heavy."""
    if override is not None:
        return float(override) if override > 0 else None
    heaviest = max((float(job.get("commit_gb") or 0) for job in jobs), default=0.0)
    return heaviest + MARGIN_GB if heaviest > 0 else None


@dataclass
class _Load:
    commit_gb: float
    room_before: float | None    # headroom when it was let start, less what other loads still had to take
    resident: bool = False


class LoadGate:
    def __init__(self, read_headroom_gb: Callable[[], float | None] = headroom_gb, margin_gb: float = MARGIN_GB,
                 wait_s: float = WAIT_S) -> None:
        self._read = read_headroom_gb
        self.margin_gb = margin_gb
        self.wait_s = wait_s
        self._lock = threading.Lock()
        self._held: dict[str, _Load] = {}

    def _settle(self, room: float | None) -> None:
        """Mark loads resident whose memory the headroom now shows as taken. Called with the lock held."""
        if room is None:
            return
        for load in self._held.values():
            if not load.resident and load.room_before is not None and load.room_before - room >= load.commit_gb:
                load.resident = True

    def _to_come(self, other_than: str | None) -> float:
        return sum(load.commit_gb for host, load in self._held.items() if host != other_than and not load.resident)

    def pending_gb(self, other_than: str | None = None) -> float:
        """GB that loads let start on other hosts have still to take."""
        with self._lock:
            self._settle(self._read())
            return self._to_come(other_than)

    def fits_alongside(self, commit_gb: float) -> bool:
        """Whether a load of this size fits while another one is held, by the headroom right now."""
        with self._lock:
            room = self._read()
            self._settle(room)
            return room is not None and room - self._to_come(None) >= commit_gb + self.margin_gb

    def try_acquire(self, host: str, commit_gb: float) -> bool:
        if commit_gb <= 0:
            return True
        with self._lock:
            room = self._read()
            self._settle(room)
            rivals = [h for h in self._held if h != host]
            still_to_come = self._to_come(host)
            if rivals and (room is None or room - still_to_come < commit_gb + self.margin_gb):
                return False
            self._held[host] = _Load(commit_gb, None if room is None else room - still_to_come)
            return True

    def acquire(self, host: str, commit_gb: float, stop: threading.Event) -> bool:
        """Wait until the load may start; False if `stop` is set first."""
        while not stop.is_set():
            if self.try_acquire(host, commit_gb):
                return True
            stop.wait(self.wait_s)
        return False

    def note(self, host: str, commit_gb: float) -> None:
        """Record a load that may already be on a host (a job found running after a restart). Whether it has taken
        its memory is not known, so it counts as still to come until headroom shows it or it is released."""
        if commit_gb > 0:
            with self._lock:
                room = self._read()
                self._settle(room)
                self._held[host] = _Load(commit_gb, None if room is None else room - self._to_come(host))

    def release(self, host: str) -> None:
        with self._lock:
            self._held.pop(host, None)
