"""The load gate counts loads it has let start but that have not yet taken their memory (review 2026-11-19, A1)."""

from __future__ import annotations

import threading
import time

from atomic_flix.runner.sched import LoadGate


class LateReader:
    """Headroom that only drops some time after a load is let start, as a real model load does."""

    def __init__(self, start_gb: float) -> None:
        self.value = start_gb
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self.value

    def take_later(self, gb: float, after_s: float) -> threading.Thread:
        def drop() -> None:
            time.sleep(after_s)
            with self._lock:
                self.value -= gb
        thread = threading.Thread(target=drop, daemon=True)
        thread.start()
        return thread


def test_two_40_gb_loads_on_60_gb_headroom_do_not_both_start():
    reader = LateReader(60.0)
    gate = LoadGate(reader)
    assert gate.try_acquire("gpu0", 40)
    reader.take_later(40.0, 0.2)
    assert not gate.try_acquire("gpu1", 40), "gpu0's load has not taken its memory yet but will"
    time.sleep(0.4)
    assert not gate.try_acquire("gpu1", 40), "and once it has, 20 GB is left"


def test_a_resident_load_is_not_counted_twice():
    reader = LateReader(90.0)
    gate = LoadGate(reader)
    assert gate.try_acquire("gpu0", 40)
    reader.take_later(40.0, 0.0).join()
    assert gate.pending_gb(other_than="gpu1") == 0, "headroom fell by gpu0's 40 GB: it is resident"
    assert gate.try_acquire("gpu1", 40), "50 GB left is over 40 plus the margin, with nothing still to come"


def test_a_released_load_no_longer_counts():
    reader = LateReader(60.0)
    gate = LoadGate(reader)
    assert gate.try_acquire("gpu0", 40)
    assert not gate.try_acquire("gpu1", 40)
    gate.release("gpu0")
    assert gate.try_acquire("gpu1", 40)


def test_enough_room_for_both_loads_still_lets_both_start():
    gate = LoadGate(lambda: 100.0)
    assert gate.try_acquire("gpu0", 40)
    assert gate.try_acquire("gpu1", 40), "100 GB less 40 to come leaves 60, over 40 plus the margin"


def test_pending_gb_names_what_other_hosts_have_still_to_load():
    reader = LateReader(100.0)
    gate = LoadGate(reader)
    gate.try_acquire("gpu0", 40)
    assert gate.pending_gb(other_than="gpu1") == 40
    assert gate.pending_gb(other_than="gpu0") == 0
    reader.take_later(40.0, 0.0).join()
    assert gate.pending_gb(other_than="gpu1") == 0
