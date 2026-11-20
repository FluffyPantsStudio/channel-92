"""The cold review of the eval (2026-11-20): staleness covers every input a verdict depends on, gate 6 sees the cut
that was evaluated, the hook recomputes the verdict, gates 5 and 6 are checked again at the answer and before
shooting, odd shapes and paths outside the film give rows instead of tracebacks, and no row passes on no evidence."""

from __future__ import annotations

import contextlib
import io
import json
import shutil

import pytest

import atomic_flix
from atomic_flix.cli import main
from atomic_flix.cli import shoot_steps
from atomic_flix.cli.common import Film, StepError
from atomic_flix.eval import eval_refusal, read_report
from atomic_flix.eval.report import write_report
from atomic_flix.eval.rows import FAIL, UNCHECKED
from atomic_flix.eval.run import evaluate
from atomic_flix.gates import RELAYED, Answer, GateRefused
from atomic_flix.project import answer_gate, ask_gate, create_project
from eval_film import INJECTIONS, build_film

V1_ASK = "2026-11-18T18:00:00+00:00"
V1_ANSWER = "2026-11-18T18:05:00+00:00"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    with contextlib.redirect_stdout(io.StringIO()):
        return build_film(tmp_path_factory.mktemp("fixes"))


@pytest.fixture
def film(built, tmp_path):
    return shutil.copytree(built, tmp_path / built.name)


def _evaluated(film):
    found = evaluate(film)
    write_report(film, found)
    return found


def _rows(found, rule):
    return [row for row in found.rows if row.rule == rule]


def _edit(path, change):
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


# H1: every input a verdict depends on is hashed ---------------------------------------------------------------------

def test_deleting_a_planned_voice_makes_the_report_stale(film):
    _evaluated(film)
    assert eval_refusal(film, "v1") is None
    (film / "plan" / "S01.voice-soft.wav").unlink()
    assert "stale" in eval_refusal(film, "v1")


def test_a_task_still_outside_stills_is_hashed(film):
    (film / "art").mkdir()
    (film / "art" / "S01.png").write_bytes(b"first version")
    _edit(film / "plan" / "S01.task.json", lambda data: data.update(still="art/S01.png"))
    _evaluated(film)
    (film / "art" / "S01.png").write_bytes(b"second version")
    assert "art/S01.png" in eval_refusal(film, "v1")


def test_a_graph_sidecar_a_task_names_is_hashed(film):
    (film / "graphs").mkdir()
    (film / "graphs" / "sung.meta.json").write_text('{"commercial_ok": true}', encoding="utf-8")
    _edit(film / "plan" / "S01.task.json", lambda data: data.update(graph="graphs/sung.json"))
    _evaluated(film)
    (film / "graphs" / "sung.meta.json").write_text('{"commercial_ok": false}', encoding="utf-8")
    assert "graphs/sung.meta.json" in eval_refusal(film, "v1")


def test_a_kit_upgrade_makes_the_report_stale(film, monkeypatch):
    _evaluated(film)
    monkeypatch.setattr(atomic_flix, "__version__", "99.0.0")
    assert "kit/version" in eval_refusal(film, "v1")


# H2: gate 6 sees the cut that was evaluated -------------------------------------------------------------------------

def test_overwriting_the_cut_after_the_eval_makes_it_stale(film):
    _evaluated(film)
    (film / "cuts" / "v01-toned.mp4").write_bytes(b"another picture")
    assert "cuts/v01-toned.mp4" in eval_refusal(film, "v1")


def test_a_newer_cut_without_an_audit_leaves_the_cut_rows_unchecked(film):
    (film / "cuts" / "v02.mp4").write_bytes(b"a newer cut")
    found = _evaluated(film)
    audit = _rows(found, "CT-AUDIT")
    assert [row.verdict for row in audit] == [UNCHECKED] and "cuts/v02.audit.json" in audit[0].evidence
    assert found.verdict("v1") == "BLOCKED"


def test_gate_six_refuses_a_cut_other_than_the_evaluated_one(film):
    _evaluated(film)
    assert "the eval read cuts/v01, not cuts/v07.mp4" in eval_refusal(film, "v1", ["cuts/v07.mp4"])
    assert eval_refusal(film, "v1", ["cuts/v01-toned.mp4"]) is None


# M1: the hook recomputes the verdict ---------------------------------------------------------------------------------

def _forge(film, change):
    path = film / "eval" / "report.json"
    _edit(path, change)


def test_a_forged_verdict_does_not_pass(film):
    INJECTIONS["cut"][0](film)
    _evaluated(film)
    _forge(film, lambda data: data.update(verdicts={"spend": "CLEAN", "v1": "CLEAN"}, blocking={}))
    assert "CT-FLASH" in eval_refusal(film, "v1")


def test_inputs_that_do_not_match_their_hash_refuse(film):
    _evaluated(film)
    _forge(film, lambda data: data["inputs"].update({"film.json": "0" * 64}))
    assert "hash" in eval_refusal(film, "v1")


def test_a_report_missing_a_rule_refuses(film):
    INJECTIONS["cut"][0](film)
    _evaluated(film)
    _forge(film, lambda data: data.update(rows=[row for row in data["rows"] if row["rule"] != "CT-FLASH"]))
    assert "CT-FLASH" in eval_refusal(film, "v1")


@pytest.mark.parametrize("rows", ["x", [1, 2], [{"rule": "H1"}], [{"rule": "H1", "unit": "film", "verdict": "maybe",
                                                                      "level": "block", "due": "v1"}]])
def test_malformed_rows_refuse(film, rows):
    _evaluated(film)
    _forge(film, lambda data: data.update(rows=rows))
    assert "malformed" in eval_refusal(film, "v1")


@pytest.mark.parametrize("inputs", ["x", {"film.json": 3}, None])
def test_malformed_inputs_refuse(film, inputs):
    _evaluated(film)
    _forge(film, lambda data: data.update(inputs=inputs))
    assert eval_refusal(film, "v1")


# M2: checked again at the answer and before shooting -----------------------------------------------------------------

def _yes(words="accept, it is ready"):
    return Answer(words=words, by="Test Person", provenance=RELAYED, at=V1_ANSWER)


def test_ask_then_answer_with_nothing_changed_passes(film):
    _evaluated(film)
    ask_gate(film, "v1", ["cuts/v01-toned.mp4"], at=V1_ASK)
    answer_gate(film, "v1", _yes())


def test_ask_then_edit_then_answer_is_refused(film):
    _evaluated(film)
    ask_gate(film, "v1", ["cuts/v01-toned.mp4"], at=V1_ASK)
    prompt = film / "plan" / "S01.prompt.txt"
    prompt.write_text(prompt.read_text(encoding="utf-8") + " Her hands rise.", encoding="utf-8")
    with pytest.raises(GateRefused, match="stale"):
        answer_gate(film, "v1", _yes())


def test_a_no_is_recorded_even_when_the_report_is_stale(film):
    _evaluated(film)
    ask_gate(film, "v1", ["cuts/v01-toned.mp4"], at=V1_ASK)
    (film / "cuts" / "v01-toned.mp4").write_bytes(b"changed")
    answer_gate(film, "v1", Answer(words="no, the sky jumps", by="Test Person", provenance=RELAYED, at=V1_ANSWER,
                                   approves=False))


def test_shoot_refuses_while_the_eval_for_gate_five_is_stale(film):
    _evaluated(film)
    with pytest.raises(StepError) as first:              # lint's own picture questions are open on this film
        shoot_steps.clear_to_shoot(Film.open(film))
    assert "lint" in str(first.value) and "eval" not in str(first.value)
    prompt = film / "plan" / "S01.prompt.txt"
    prompt.write_text(prompt.read_text(encoding="utf-8") + " Her hands rise.", encoding="utf-8")
    with pytest.raises(StepError, match="stale"):
        shoot_steps.clear_to_shoot(Film.open(film))


# M3 and M4: odd shapes and paths outside the film --------------------------------------------------------------------

def test_an_unreadable_film_json_gives_rows_not_a_traceback(film, capsys):
    (film / "film.json").write_text("{not json", encoding="utf-8")
    found = evaluate(film)
    assert found.verdict("spend") == "BLOCKED"
    assert any("film.json" in row.evidence for row in found.blockers("spend"))
    assert main(["eval", str(film)]) == 2                 # the verb names the file, with no traceback
    assert "film.json" in capsys.readouterr().err
    assert eval_refusal(film, "spend") is not None


@pytest.mark.parametrize("change", [
    lambda data: data.update(lineup_rows=["shots.txt"]),
    lambda data: data.update(stems="audio/mix.wav"),
    lambda data: data.update(never="umbrella"),
    lambda data: data.update(props=["lamp"]),
])
def test_odd_film_json_shapes_give_rows(film, change, capsys):
    _edit(film / "film.json", change)
    found = evaluate(film)
    assert found.rows
    assert main(["eval", str(film)]) in (0, 1)
    assert "Traceback" not in capsys.readouterr().err


def test_odd_standing_and_cut_shapes_give_rows(film, capsys):
    _edit(film / "standing.json", lambda data: data.update(gates={"gates": "x", "review": 3}))
    _edit(film / "cuts" / "v01-toned.tone.json", lambda data: data.update(spread_after={"black": "dark"}))
    found = evaluate(film)
    assert [row.verdict for row in _rows(found, "CT-SPREAD")] == [UNCHECKED]
    assert found.verdict("v1") == "BLOCKED"


def test_a_shot_list_outside_the_film_is_never_read(film, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text((film / "shots.txt").read_text(encoding="utf-8"), encoding="utf-8")
    _edit(film / "film.json", lambda data: data.update(lineup_rows="../outside.txt"))
    found = evaluate(film)
    assert all(row.verdict == UNCHECKED for row in _rows(found, "SC-MASTER"))
    assert any("outside" in row.evidence or "relative" in row.evidence for row in _rows(found, "SC-MASTER"))
    assert found.verdict("spend") == "BLOCKED"


def test_a_task_still_outside_the_film_fails_the_scene(film, tmp_path):
    _edit(film / "plan" / "S01.task.json", lambda data: data.update(still="../elsewhere.png"))
    found = evaluate(film)
    assert [row.verdict for row in _rows(found, "SC-ASPECT")] in ([FAIL], [UNCHECKED])
    assert found.verdict("spend") == "BLOCKED"


# M5: nothing passes on no evidence ------------------------------------------------------------------------------------

def test_a_scene_without_still_records_is_unchecked(film):
    for key in ("N01", "S01"):
        (film / "stills" / f"{key}.json").unlink()
    found = evaluate(film)
    for rule in ("SC-PROPS", "SC-LOOK", "SC-MASTER"):
        assert [row.verdict for row in _rows(found, rule)] == [UNCHECKED], rule


def test_a_grade_account_without_its_grain_field_is_unchecked(film):
    _edit(film / "cuts" / "v01-toned.tone.json", lambda data: data.pop("grain"))
    assert [row.verdict for row in _rows(evaluate(film), "CT-GRAIN")] == [UNCHECKED]


def test_a_film_with_no_answers_leaves_the_answer_rules_unchecked(tmp_path):
    folder = create_project(tmp_path, "bare-film", "Bare Film", created="2026-11-18T09:00:00+00:00")
    found = evaluate(folder.root)
    for rule in ("LG-PERSON", "LG-ARRIVAL", "LG-REUSE"):
        assert [row.verdict for row in _rows(found, rule)] == [UNCHECKED], rule


def test_an_unreadable_gate_time_fails_the_order(film):
    def change(data):
        next(r for r in data["gates"]["gates"] if r["gate"] == "looks")["asked_at"] = "soon"
    _edit(film / "standing.json", change)
    rows = _rows(evaluate(film), "LG-ORDER")
    assert [row.verdict for row in rows] == [FAIL] and "soon" in rows[0].evidence


# LOW ---------------------------------------------------------------------------------------------------------------

def test_the_report_says_what_clean_means(film):
    _evaluated(film)
    page = (film / "eval" / "report.md").read_text(encoding="utf-8")
    assert "nothing the kit can check fails" in page
    report = read_report(film)
    assert report["unchecked_by_design"] > 0 and str(report["unchecked_by_design"]) in page.split("\n")[2]


def test_the_evaluation_inputs_cannot_be_changed(film):
    found = evaluate(film)
    with pytest.raises(TypeError):
        found.inputs["film.json"] = "x"
