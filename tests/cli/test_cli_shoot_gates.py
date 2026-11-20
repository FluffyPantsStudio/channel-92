"""Gate 5 and `shoot` (review 2026-11-19): the yes is bound to one batch (A5), the runner's own `shoot` takes the same
road as the film verb (A4), a headroom floor by default (A3), and how a gate answer arrived (A7)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from atomic_flix.cli import main
from atomic_flix.cli import shoot_steps
from atomic_flix.cli.common import Film, StepError
from atomic_flix.gates import Answer
from atomic_flix.project import (FilmFolder, ProjectError, answer_gate, ask_gate, draw_batch, load_standing,
                                 reopen_gate, where_it_stands)
from atomic_flix.runner import __main__ as runner_main
from atomic_flix.runner.shoot import Request, plan_batch

pytestmark = pytest.mark.usefixtures("no_eval_hook")    # gate bookkeeping on bare folders; the hook: tests/eval

AT = "2026-11-19T10:00:00+00:00"
PLAN = {"takes": 4, "size": [1280, 704], "busy_s": 3600.0}
SUNG = {"6": {"class_type": "CLIPTextEncode", "inputs": {"text": "$wording"}},
        "10": {"class_type": "LoadImage", "inputs": {"image": "$opening_still"}},
        "37": {"class_type": "RandomNoise", "inputs": {"noise_seed": "$seed"}},
        "52": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "flix/$save_as"}}}


def _new(tmp_path: Path) -> Path:
    mix = tmp_path / "mix.wav"
    mix.write_bytes(b"RIFF fake")
    film = tmp_path / "films" / "sunny"
    assert main(["new", str(film), "--song", str(mix), "--aspect", "16:9", "--by", "Test Person",
                 "--words", "wide"]) == 0
    return film


def _budget(film: Path, **changes) -> None:
    (film / "plan").mkdir(exist_ok=True)
    (film / "plan" / "budget.json").write_text(json.dumps({**PLAN, **changes}), encoding="utf-8")


def _at_gate_five(tmp_path: Path, answer: bool = True) -> Path:
    film = _new(tmp_path)
    for gate in ("concept", "song", "looks", "board"):
        ask_gate(film, gate, ["shown"], at=AT)
        answer_gate(film, gate, Answer(words="yes", by="Test Person", provenance="person", at=AT))
    _budget(film)
    assert main(["gate", str(film), "ask", "spend"]) == 0
    if answer:
        assert main(["gate", str(film), "answer", "spend", "--by", "Test Person", "--words", "yes, run it"]) == 0
    return film


def _plan_facts() -> tuple:
    return PLAN["takes"], tuple(PLAN["size"]), PLAN["busy_s"]


# A5: one yes, one batch ------------------------------------------------------------------------------------------

def test_the_yes_at_gate_five_records_the_batch_it_approved(tmp_path):
    film = _at_gate_five(tmp_path)
    batch = load_standing(FilmFolder(film)).batch
    assert (batch.takes, batch.size, batch.busy_s, batch.drawn) == (4, (1280, 704), 3600.0, 0)
    assert "4 takes" in where_it_stands(film)


def test_takes_are_drawn_on_the_approval_up_to_its_count(tmp_path):
    film = _at_gate_five(tmp_path)
    folder = FilmFolder(film)
    stamp = draw_batch(folder, 3, plan=_plan_facts())
    assert stamp == load_standing(folder).batch.at
    with pytest.raises(ProjectError, match="new answer"):
        draw_batch(folder, 2, plan=_plan_facts())
    draw_batch(folder, 1, plan=_plan_facts())
    with pytest.raises(ProjectError, match="new answer"):
        draw_batch(folder, 1, plan=_plan_facts())
    assert load_standing(folder).batch.drawn == 4


@pytest.mark.parametrize("changed", [(5, (1280, 704), 3600.0), (4, (1152, 640), 3600.0), (4, (1280, 704), 7200.0)])
def test_a_plan_that_differs_from_the_approved_one_needs_a_new_answer(tmp_path, changed):
    film = _at_gate_five(tmp_path)
    with pytest.raises(ProjectError, match="differs"):
        draw_batch(FilmFolder(film), 1, plan=changed)
    assert load_standing(FilmFolder(film)).batch.drawn == 0


def test_reopening_gate_five_drops_the_batch_and_a_new_yes_starts_afresh(tmp_path):
    film = _at_gate_five(tmp_path)
    folder = FilmFolder(film)
    draw_batch(folder, 4, plan=_plan_facts())
    reopen_gate(folder, "spend", "a second batch", at="2026-11-19T11:00:00+00:00")
    assert load_standing(folder).batch is None
    _budget(film, takes=2, busy_s=1800.0)
    assert main(["gate", str(film), "ask", "spend", "--at", "2026-11-19T11:01:00+00:00"]) == 0
    assert main(["gate", str(film), "answer", "spend", "--by", "Test Person", "--words", "the second batch, yes",
                 "--at", "2026-11-19T11:02:00+00:00"]) == 0
    batch = load_standing(folder).batch
    assert (batch.takes, batch.drawn) == (2, 0)


def test_a_no_at_gate_five_leaves_no_batch(tmp_path):
    film = _at_gate_five(tmp_path, answer=False)
    assert main(["gate", str(film), "answer", "spend", "--by", "Test Person", "--words", "not yet", "--no"]) == 0
    assert load_standing(FilmFolder(film)).batch is None


def test_planned_jobs_from_another_approval_are_refused_before_lint(tmp_path):
    film = _at_gate_five(tmp_path)
    (film / "stills").mkdir(exist_ok=True)
    (film / "stills" / "S01.png").write_bytes(b"png")
    graph = film / "graphs" / "sung.json"
    graph.parent.mkdir()
    graph.write_text(json.dumps(SUNG), encoding="utf-8")
    plan_batch(film, [Request(key="S01", graph=str(graph), wording="w", inputs={"opening_still": "stills/S01.png"},
                              seconds=4)], extra_fields={"approval": "2026-01-01T00:00:00+00:00"})
    with pytest.raises(StepError, match="earlier"):
        shoot_steps.clear_to_shoot(Film.open(film))


# A4: the runner's `shoot` takes the same road ----------------------------------------------------------------------

def test_the_runner_shoot_uses_the_film_verbs_checks():
    assert runner_main.clear_to_shoot is shoot_steps.clear_to_shoot


def test_the_runner_shoot_refuses_a_folder_that_is_not_a_film(tmp_path, capsys):
    (tmp_path / "renders").mkdir()
    assert runner_main.main(["shoot", str(tmp_path), "--hosts", "127.0.0.1:1"]) != 0
    assert "film" in capsys.readouterr().err


def test_the_runner_shoot_refuses_before_gate_five(tmp_path, capsys):
    film = _at_gate_five(tmp_path, answer=False)
    assert runner_main.main(["shoot", str(film), "--hosts", "127.0.0.1:1"]) != 0
    assert "gate 5" in capsys.readouterr().err


def test_the_runner_plan_on_a_film_draws_on_gate_five(tmp_path, capsys):
    film = _new(tmp_path)
    (film / "stills").mkdir(exist_ok=True)
    (film / "stills" / "S01.png").write_bytes(b"png")
    graph = film / "graphs" / "sung.json"
    graph.parent.mkdir()
    graph.write_text(json.dumps(SUNG), encoding="utf-8")
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps({"requests": [{"key": "S01", "graph": "graphs/sung.json", "wording": "w",
                                               "inputs": {"opening_still": "stills/S01.png"}, "seconds": 4}]}),
                     encoding="utf-8")
    assert runner_main.main(["plan", str(film), str(batch)]) == 1
    assert "gate" in capsys.readouterr().err
    assert list((film / "renders").glob("*/*.job.json")) == []


# A3: a headroom floor by default -----------------------------------------------------------------------------------

def test_the_floor_defaults_to_the_heaviest_load_plus_the_margin():
    from atomic_flix.runner.sched import headroom_floor
    heavy = [{"commit_gb": 40}, {"commit_gb": 30}]
    assert headroom_floor(heavy) == 45
    assert headroom_floor([{"commit_gb": 0}]) is None
    assert headroom_floor(heavy, override=60) == 60
    assert headroom_floor(heavy, override=0) is None


def test_shoot_hands_the_runner_the_default_floor(tmp_path, monkeypatch):
    film = _at_gate_five(tmp_path)
    (film / "stills").mkdir(exist_ok=True)
    (film / "stills" / "S01.png").write_bytes(b"png")
    graph = film / "graphs" / "sung.json"
    graph.parent.mkdir()
    graph.write_text(json.dumps(SUNG), encoding="utf-8")
    graph.with_suffix(".meta.json").write_text(json.dumps({"commit_gb": 40}), encoding="utf-8")
    stamp = load_standing(FilmFolder(film)).batch.at
    plan_batch(film, [Request(key="S01", graph=str(graph), wording="w", inputs={"opening_still": "stills/S01.png"},
                              seconds=4)], extra_fields={"approval": stamp})
    seen: dict = {}

    class Recorder:
        def __init__(self, *args, **kwargs) -> None:
            seen.update(kwargs)

        def run(self, keys):
            return {"made": 0, "errored": 0, "gpu_hours": 0.0, "still_running": 0, "not_started": 1, "unknown": 0,
                    "refused": False}

    monkeypatch.setattr(shoot_steps, "clear_to_shoot", lambda film, keys=None: None)
    monkeypatch.setattr(shoot_steps, "Runner", Recorder)
    monkeypatch.setattr(Film, "tasks", lambda self: {"S01": {}})
    assert main(["shoot", str(film), "--hosts", "127.0.0.1:8188"]) == 0
    assert seen["min_headroom_gb"] == 45
    assert main(["shoot", str(film), "--hosts", "127.0.0.1:8188", "--min-headroom", "0"]) == 0
    assert seen["min_headroom_gb"] is None


# A7: how an answer arrived -----------------------------------------------------------------------------------------

def _latest(film: Path, gate: str):
    return load_standing(FilmFolder(film)).gates.record(gate).latest


def test_words_passed_as_arguments_are_recorded_as_relayed(tmp_path, capsys):
    film = _new(tmp_path)
    assert main(["gate", str(film), "ask", "concept", "--shown", "pitches.md"]) == 0
    assert main(["gate", str(film), "answer", "concept", "--by", "Test Person", "--words", "the second one"]) == 0
    assert _latest(film, "concept").provenance == "relayed"
    assert main(["progress", str(film)]) in (0, 1)
    assert "relayed" in capsys.readouterr().out
    assert "relayed" in (film / "notes.md").read_text(encoding="utf-8")


def test_words_typed_at_a_terminal_are_recorded_as_direct(tmp_path, monkeypatch, capsys):
    film = _new(tmp_path)
    assert main(["gate", str(film), "ask", "concept", "--shown", "pitches.md"]) == 0

    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("sys.stdin", Terminal("Test Person\nthe rooftop one\n"))
    assert main(["gate", str(film), "answer", "concept"]) == 0
    answer = _latest(film, "concept")
    assert (answer.provenance, answer.by, answer.words) == ("person-direct", "Test Person", "the rooftop one")
    assert "typed" in where_it_stands(film)


def test_no_words_and_no_terminal_is_refused(tmp_path, monkeypatch, capsys):
    film = _new(tmp_path)
    assert main(["gate", str(film), "ask", "concept", "--shown", "pitches.md"]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with pytest.raises(SystemExit):
        main(["gate", str(film), "answer", "concept", "--by", "Test Person"])
    assert _latest(film, "concept") is None


@pytest.mark.parametrize("by", ["claude2", "Claude-Opus", "assistant_7", "AGENT007", "the-model"])
def test_relayed_answers_signed_by_a_model_are_refused(tmp_path, capsys, by):
    film = _new(tmp_path)
    assert main(["gate", str(film), "ask", "concept", "--shown", "pitches.md"]) == 0
    assert main(["gate", str(film), "answer", "concept", "--by", by, "--words", "yes"]) == 2
    assert _latest(film, "concept") is None


def test_relayed_answers_need_the_words(tmp_path, capsys):
    film = _new(tmp_path)
    assert main(["gate", str(film), "ask", "concept", "--shown", "pitches.md"]) == 0
    assert main(["gate", str(film), "answer", "concept", "--by", "Test Person", "--words", "  "]) == 2
    assert _latest(film, "concept") is None
