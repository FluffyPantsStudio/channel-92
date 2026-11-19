"""The runner's ledger: JSON lines with nine fixed fields (docs/job-log.md)."""

import json

import pytest

from atomic_flix.compare import FIELDS, JobLog, JobLogRow, JobLogError, read_job_log


def row(**changes):
    base = {"job_id": "S02-r007", "kind": "vocal", "shot": "S02", "host": "127.0.0.1:8189", "seed": 1934820044,
            "gpu_seconds": 149.0, "started": "2026-11-20T10:00:00+00:00",
            "finished": "2026-11-20T10:03:00+00:00", "state": "done"}
    base.update(changes)
    return base


def write(tmp_path, *rows, raw=()):
    path = tmp_path / "job-log.jsonl"
    lines = [json.dumps(r) for r in rows] + list(raw)
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def test_the_nine_fields():
    assert FIELDS == ("job_id", "kind", "shot", "host", "seed", "gpu_seconds", "started", "finished", "state")


def test_reads_every_field(tmp_path):
    job_log = read_job_log(write(tmp_path, row()))
    assert isinstance(job_log, JobLog)
    (entry,) = job_log.logged
    assert isinstance(entry, JobLogRow)
    assert entry.job_id == "S02-r007" and entry.kind == "vocal" and entry.shot == "S02"
    assert entry.seed == 1934820044 and entry.gpu_seconds == 149.0 and entry.state == "done"
    assert entry.wall_seconds == pytest.approx(180.0)
    assert entry.video_seconds is None


def test_a_missing_ledger_is_empty(tmp_path):
    assert read_job_log(tmp_path / "nothing.jsonl").logged == ()


def test_the_last_line_of_a_job_wins(tmp_path):
    running = row(state="running", finished=None, gpu_seconds=None)
    path = write(tmp_path, running, row(job_id="N08-r001", kind="cutaway", shot="N08"), row())
    logged = read_job_log(path).logged
    assert [e.job_id for e in logged] == ["S02-r007", "N08-r001"]
    assert logged[0].state == "done"


def test_nulls_where_allowed(tmp_path):
    entry = read_job_log(write(tmp_path, row(shot=None, seed=None, gpu_seconds=None, kind="still"))).logged[0]
    assert entry.shot is None and entry.seed is None and entry.gpu_seconds is None


def test_z_times_and_blank_lines(tmp_path):
    path = write(tmp_path, row(started="2026-11-20T10:00:00Z", finished="2026-11-20T10:01:00Z"), raw=["", "   "])
    assert read_job_log(path).logged[0].wall_seconds == pytest.approx(60.0)


def test_extra_keys_are_ignored_and_video_seconds_is_read(tmp_path):
    entry = read_job_log(write(tmp_path, row(video_seconds=9, graph="sung.json"))).logged[0]
    assert entry.video_seconds == 9.0


@pytest.mark.parametrize("change, fragment", [
    ({"job_id": ""}, "job_id"),
    ({"kind": 3}, "kind"),
    ({"seed": "abc"}, "seed"),
    ({"seed": True}, "seed"),
    ({"gpu_seconds": "149"}, "gpu_seconds"),
    ({"gpu_seconds": -1}, "gpu_seconds"),
    ({"state": "queued"}, "state"),
    ({"started": "noon"}, "started"),
    ({"finished": "2026-11-20T09:00:00+00:00"}, "finished"),
    ({"state": "done", "finished": None}, "finished"),
    ({"state": "running", "started": None, "finished": None}, "started"),
    ({"video_seconds": "long"}, "video_seconds"),
])
def test_bad_values_name_the_line_and_field(tmp_path, change, fragment):
    path = write(tmp_path, row(), row(**change))
    with pytest.raises(JobLogError) as caught:
        read_job_log(path)
    assert "line 2" in str(caught.value) and fragment in str(caught.value)


def test_a_missing_field_is_an_error(tmp_path):
    broken = row()
    del broken["host"]
    with pytest.raises(JobLogError, match="host"):
        read_job_log(write(tmp_path, broken))


def test_not_json_or_not_an_object(tmp_path):
    with pytest.raises(JobLogError, match="line 1"):
        read_job_log(write(tmp_path, raw=['{"job_id": "S02-r0']))
    with pytest.raises(JobLogError, match="line 1"):
        read_job_log(write(tmp_path, raw=["[1, 2]"]))


def test_lenient_reading_keeps_good_lines_and_lists_problems(tmp_path):
    path = write(tmp_path, row(), raw=['{"job_id": "cut-off'])
    job_log = read_job_log(path, strict=False)
    assert len(job_log.logged) == 1
    assert len(job_log.problems) == 1 and "line 2" in job_log.problems[0]
