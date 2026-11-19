"""The load gate and the commit-charge reader."""

from __future__ import annotations

import os
import sys
import threading

import pytest

from atomic_flix.runner.commit import CommitInfo, headroom_gb, read_commit
from atomic_flix.runner.sched import LoadGate


def test_a_second_heavy_load_is_refused_at_30_gb_and_accepted_at_50_gb():
    tight = LoadGate(lambda: 30.0)
    assert tight.try_acquire("gpu0", 40)
    assert not tight.try_acquire("gpu1", 40)
    readings = iter([90.0, 50.0, 50.0])        # gpu0's load takes its 40 GB before gpu1 asks
    roomy = LoadGate(lambda: next(readings))
    assert roomy.try_acquire("gpu0", 40)
    assert roomy.try_acquire("gpu1", 40)


def test_the_first_load_never_waits_for_headroom():
    gate = LoadGate(lambda: 0.0)
    assert gate.try_acquire("gpu0", 40)


def test_unknown_headroom_means_one_load_at_a_time():
    gate = LoadGate(lambda: None)
    assert gate.try_acquire("gpu0", 40)
    assert not gate.try_acquire("gpu1", 40)
    gate.release("gpu0")
    assert gate.try_acquire("gpu1", 40)


def test_a_graph_with_no_load_figure_is_never_held():
    gate = LoadGate(lambda: 0.0)
    assert gate.try_acquire("gpu0", 40)
    assert gate.try_acquire("gpu1", 0)


def test_fits_alongside_answers_for_the_budget():
    assert not LoadGate(lambda: 30.0).fits_alongside(40)
    assert LoadGate(lambda: 46.0).fits_alongside(40)
    assert not LoadGate(lambda: None).fits_alongside(40)


def test_acquire_waits_until_the_other_load_is_released():
    gate = LoadGate(lambda: 10.0, wait_s=0.01)
    assert gate.try_acquire("gpu0", 40)
    got: list[bool] = []
    thread = threading.Thread(target=lambda: got.append(gate.acquire("gpu1", 40, threading.Event())))
    thread.start()
    thread.join(0.1)
    assert thread.is_alive(), "held while gpu0 has its load"
    gate.release("gpu0")
    thread.join(2)
    assert got == [True]


def test_acquire_gives_up_when_asked_to_stop():
    gate = LoadGate(lambda: 10.0, wait_s=0.01)
    gate.try_acquire("gpu0", 40)
    stop = threading.Event()
    stop.set()
    assert gate.acquire("gpu1", 40, stop) is False


def test_headroom_is_limit_minus_committed():
    info = CommitInfo(committed_gb=60.0, limit_gb=100.0, provenance="test")
    assert info.headroom_gb == pytest.approx(40.0)


def test_headroom_falls_back_to_the_environment(monkeypatch):
    monkeypatch.setenv("ATOMIC_FLIX_COMMIT_HEADROOM_GB", "52.5")
    assert headroom_gb(reader=lambda: None) == pytest.approx(52.5)
    monkeypatch.delenv("ATOMIC_FLIX_COMMIT_HEADROOM_GB")
    assert headroom_gb(reader=lambda: None) is None
    assert headroom_gb(reader=lambda: CommitInfo(10.0, 64.0, "test")) == pytest.approx(54.0)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows commit charge")
def test_windows_commit_charge_reads_on_this_machine():
    info = read_commit()
    assert info is not None and info.provenance == "windows"
    assert 0 < info.committed_gb < info.limit_gb


@pytest.mark.skipif(not os.path.exists("/proc/meminfo"), reason="Linux fallback")
def test_linux_fallback_reads_meminfo():
    info = read_commit()
    assert info is not None and info.limit_gb > 0
