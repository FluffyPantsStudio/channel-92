"""Job files: numbered once, written before submit, updated in place."""

from __future__ import annotations

import json
import threading

from atomic_flix.runner.jobs import JobStore


def test_numbers_count_up_per_key_and_files_are_named_by_number(film_dir):
    store = JobStore(film_dir)
    first = store.create("S02", {"seed": 1})
    second = store.create("S02", {"seed": 2})
    other = store.create("S03", {"seed": 3})
    assert (first["n"], second["n"], other["n"]) == (1, 2, 1)
    assert store.job_path(first) == film_dir / "renders" / "S02" / "r001.job.json"
    saved = json.loads(store.job_path(second).read_text(encoding="utf-8"))
    assert saved["state"] == "planned" and saved["key"] == "S02" and saved["seed"] == 2


def test_numbers_are_never_reused_even_after_a_job_file_is_deleted(film_dir):
    store = JobStore(film_dir)
    store.create("S02", {})
    second = store.create("S02", {})
    store.job_path(second).unlink()
    assert store.create("S02", {})["n"] == 3


def test_numbers_stay_unique_across_threads(film_dir):
    store = JobStore(film_dir)
    numbers: list[int] = []
    lock = threading.Lock()

    def make() -> None:
        job = JobStore(film_dir).create("S05", {})
        with lock:
            numbers.append(job["n"])

    threads = [threading.Thread(target=make) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(numbers) == list(range(1, 13))
    assert len(store.load_all()) == 12


def test_update_returns_a_new_record_and_rewrites_the_file(film_dir):
    store = JobStore(film_dir)
    job = store.create("S02", {"seed": 9})
    running = store.update(job, state="running", host="127.0.0.1:8189", queue_ticket="b1c")
    assert job["state"] == "planned", "the earlier record is not changed"
    assert running["state"] == "running"
    again = store.load(store.job_path(job))
    assert again == running
    assert not list((film_dir / "renders" / "S02").glob("*.tmp"))


def test_load_all_sorts_by_key_and_number(film_dir):
    store = JobStore(film_dir)
    for key in ("S03", "S01", "S03"):
        store.create(key, {})
    assert [(j["key"], j["n"]) for j in store.load_all()] == [("S01", 1), ("S03", 1), ("S03", 2)]
