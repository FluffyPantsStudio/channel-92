"""A damaged ledger line is reported with its number, whatever is wrong with it (review 2026-11-19, A11)."""

from __future__ import annotations

import json

import pytest

from atomic_flix.compare.ledger import JobLogError, read_job_log

GOOD = {"job_id": "S01-r001", "kind": "vocal", "shot": "S01", "host": "127.0.0.1:8188", "seed": 1,
        "gpu_seconds": 80.0, "started": "2026-11-19T10:00:00+00:00", "finished": "2026-11-19T10:02:00+00:00",
        "state": "done"}


def _write(path, middle: bytes) -> None:
    good = json.dumps(GOOD).encode("utf-8")
    path.write_bytes(good + b"\n" + middle + b"\n" + good.replace(b"S01-r001", b"S02-r001") + b"\n")


def test_a_line_torn_inside_a_character_names_its_line(tmp_path):
    path = tmp_path / "job-log.jsonl"
    _write(path, '{"job_id": "S03-r001", "kind": "vocal é'.encode("utf-8")[:-1])
    with pytest.raises(JobLogError, match="line 2"):
        read_job_log(path)


def test_a_torn_line_is_listed_by_number_when_not_strict(tmp_path):
    path = tmp_path / "job-log.jsonl"
    _write(path, b"\xff\xfe not text")
    log = read_job_log(path, strict=False)
    assert [entry.job_id for entry in log.logged] == ["S01-r001", "S02-r001"]
    assert len(log.problems) == 1 and log.problems[0].startswith("line 2:")


def test_strict_is_still_the_default(tmp_path):
    path = tmp_path / "job-log.jsonl"
    _write(path, b"{not json")
    with pytest.raises(JobLogError, match="line 2"):
        read_job_log(path)
