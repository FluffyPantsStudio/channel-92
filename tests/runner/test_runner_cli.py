"""The runner's command line: plan a batch from a file, the gate-5 budget, shoot against a fake host, status."""

from __future__ import annotations

import json

from atomic_flix.runner.__main__ import main


def _batch(tmp_path, film_dir, graph) -> str:
    batch = {"requests": [{"key": "S02", "graph": str(graph), "wording": "Frankie sings", "seconds": 9, "vocal": True,
                           "inputs": {"opening_still": "stills/S02.png", "audio": "plan/S02.voice-soft.wav"}}]}
    path = tmp_path / "batch.json"
    path.write_text(json.dumps(batch), encoding="utf-8")
    return str(path)


def test_plan_budget_shoot_and_status(film_dir, sung_graph, fake_hosts, tmp_path, capsys, monkeypatch, cleared):
    (fake,) = fake_hosts(1)
    monkeypatch.setattr("atomic_flix.runner.__main__.LoadGate", lambda: _Roomy())
    log = tmp_path / "log" / "jobs.jsonl"
    assert main(["plan", str(film_dir), _batch(tmp_path, film_dir, sung_graph)]) == 0
    assert "S02 r001: planned, 217 frames" in capsys.readouterr().out

    assert main(["budget", str(film_dir), "--hosts", fake.host, "--log", str(log)]) == 0
    assert "no measured renders" in capsys.readouterr().out

    assert main(["shoot", str(film_dir), "--hosts", fake.host, "--log", str(log), "--max-hours", "0.5"]) == 1
    assert "max-hours" in capsys.readouterr().err

    assert main(["shoot", str(film_dir), "S02", "--hosts", fake.host, "--log", str(log), "--timeout", "10",
                 "--min-headroom", "0"]) == 0          # this machine's own headroom is not part of the test
    assert "1 renders, 0 errored" in capsys.readouterr().out
    assert (film_dir / "renders" / "S02" / "r001.mp4").is_file()

    assert main(["progress", str(film_dir)]) == 0
    assert "S02: 1 done" in capsys.readouterr().out


def test_plan_refuses_a_bad_batch(film_dir, silent_graph, tmp_path, capsys):
    assert main(["plan", str(film_dir), _batch(tmp_path, film_dir, silent_graph)]) == 1
    assert "refused" in capsys.readouterr().err


def test_ping_reports_each_host(fake_hosts, capsys):
    (fake,) = fake_hosts(1)
    code = main(["ping", "--hosts", fake.host])
    out = capsys.readouterr().out
    assert fake.gpu_name in out
    assert code in (0, 1)          # 1 when ffmpeg or UTF-8 mode is missing on this machine


class _Roomy:
    """A load gate that always has room: the machine's commit charge is not part of these tests."""

    def fits_alongside(self, _gb: float) -> bool:
        return True

    def acquire(self, *_args) -> bool:
        return True

    def release(self, *_args) -> None:
        return None

    def note(self, *_args) -> None:
        return None

    def pending_gb(self, *_args, **_kwargs) -> float:
        return 0.0
