"""The report on disk, staleness, the `eval` verb, and the hook on gates 5 and 6, which fails closed."""

from __future__ import annotations

import contextlib
import io
import json
import shutil

import pytest

from atomic_flix.cli import main
from atomic_flix.eval import eval_refusal, read_report, stale_inputs
from atomic_flix.eval.report import write_report
from atomic_flix.eval.run import evaluate
from atomic_flix.formats import tag
from atomic_flix.gates import GateRefused
from atomic_flix.project import FilmFolder, ask_gate, load_standing
from eval_film import INJECTIONS, build_film

V1_ASK = "2026-11-18T18:00:00+00:00"
ROW_FIELDS = {"rule", "unit", "method", "verdict", "level", "evidence", "due", "inputs"}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    with contextlib.redirect_stdout(io.StringIO()):
        return build_film(tmp_path_factory.mktemp("hook"))


@pytest.fixture
def film(built, tmp_path):
    return shutil.copytree(built, tmp_path / built.name)


def _evaluated(film):
    write_report(film, evaluate(film))
    return read_report(film)


def test_the_report_has_its_format_and_every_row_its_fields(film):
    report = _evaluated(film)
    assert report["format"] == tag("eval") == "atomic-flix/eval@1"
    assert report["verdict"] == "CLEAN" and report["verdicts"] == {"spend": "CLEAN", "v1": "CLEAN"}
    assert all(set(row) == ROW_FIELDS for row in report["rows"])
    assert len(report["inputs_hash"]) == 64 and "standing.json" in report["inputs"]
    assert any(name.startswith("kit/") for name in report["inputs"])
    page = (film / "eval" / "report.md").read_text(encoding="utf-8")
    assert page.startswith("# Dune Test: eval") and "**CLEAN**" in page and "Unchecked by design" in page


def test_a_fresh_report_is_not_stale_and_any_changed_input_makes_it_stale(film):
    report = _evaluated(film)
    assert stale_inputs(film, report) == []
    record = film / "stills" / "S01.json"
    record.write_text(record.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert stale_inputs(film, report) == ["stills/S01.json"]


def test_a_new_input_file_makes_the_report_stale(film):
    report = _evaluated(film)
    (film / "cuts" / "v02.audit.json").write_text("{}", encoding="utf-8")
    assert stale_inputs(film, report) == ["cuts/v02.audit.json"]


def test_gate_six_is_asked_when_the_report_is_fresh_and_clean(film):
    _evaluated(film)
    ask_gate(film, "v1", ["cuts/v01-toned.mp4"], at=V1_ASK)
    assert load_standing(FilmFolder(film)).gates.record("v1").state == "asked"


def test_gate_six_fails_closed_without_a_report(film):
    with pytest.raises(GateRefused, match="needs a fresh eval"):
        ask_gate(film, "v1", ["cuts/v01-toned.mp4"], at=V1_ASK)
    assert load_standing(FilmFolder(film)).gates.record("v1").state == "waiting"


def test_gate_six_refuses_a_stale_report(film):
    _evaluated(film)
    INJECTIONS["cut"][0](film)
    with pytest.raises(GateRefused, match="stale"):
        ask_gate(film, "v1", ["cuts/v01-toned.mp4"], at=V1_ASK)


def test_gate_six_refuses_a_blocked_film_and_names_the_rule(film):
    INJECTIONS["cut"][0](film)
    _evaluated(film)
    with pytest.raises(GateRefused, match="BLOCKED by CT-FLASH film"):
        ask_gate(film, "v1", ["cuts/v01-toned.mp4"], at=V1_ASK)


def test_an_unreadable_report_refuses(film):
    _evaluated(film)
    (film / "eval" / "report.json").write_text("{not json", encoding="utf-8")
    assert "cannot be read" in eval_refusal(film, "v1")
    (film / "eval" / "report.json").write_text(json.dumps({"format": tag("edit")}), encoding="utf-8")
    assert "atomic-flix/eval@1" in eval_refusal(film, "spend")


def test_the_hook_ignores_the_reports_own_verdicts_and_reads_the_rows(film):
    report = _evaluated(film)
    report["verdicts"], report["blocking"] = {"v1": "BLOCKED"}, {}
    (film / "eval" / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert eval_refusal(film, "v1") is None


def test_only_gates_five_and_six_are_held(film):
    for gate in ("concept", "song", "looks", "board"):
        assert eval_refusal(film, gate) is None
    assert eval_refusal(film, "spend") is not None


def test_a_rule_due_at_gate_six_does_not_hold_gate_five(film):
    INJECTIONS["cut"][0](film)
    report = _evaluated(film)
    assert report["verdicts"] == {"spend": "CLEAN", "v1": "BLOCKED"}
    assert eval_refusal(film, "spend") is None and "CT-FLASH" in eval_refusal(film, "v1")


# The verb ----------------------------------------------------------------------------------------------------------

def test_the_verb_writes_the_report_and_exits_by_the_verdict(film, capsys):
    assert main(["eval", str(film)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("CLEAN:") and "gaps (no way to check yet): GP-HEAVY, GP-MINE" in out
    assert (film / "eval" / "report.json").is_file() and (film / "eval" / "report.md").is_file()
    INJECTIONS["auto"][0](film)
    assert main(["eval", str(film)]) == 1
    assert "blocks: H1 shot:S01" in capsys.readouterr().out


def test_the_verb_answers_whether_a_gate_may_be_asked(film, capsys):
    assert main(["eval", str(film), "--gate", "6"]) == 1
    assert "needs a fresh eval" in capsys.readouterr().out
    assert main(["eval", str(film)]) == 0
    assert main(["eval", str(film), "--gate", "6"]) == 0
    INJECTIONS["sent-prompt"][0](film)
    assert main(["eval", str(film), "--gate", "6"]) == 1
    assert "stale" in capsys.readouterr().out


def test_stale_ok_shows_the_saved_report_marked_stale(film, capsys):
    assert main(["eval", str(film), "--stale-ok"]) == 2
    assert "no eval report" in capsys.readouterr().err
    assert main(["eval", str(film)]) == 0
    INJECTIONS["sent-prompt"][0](film)
    assert main(["eval", str(film), "--stale-ok"]) == 1
    assert "STALE: 1 input(s) changed" in capsys.readouterr().out


def test_json_prints_the_whole_report(film, capsys):
    assert main(["eval", str(film), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["format"] == "atomic-flix/eval@1"


def test_the_gate_verb_reports_the_hook_as_a_refusal(film, capsys):
    assert main(["gate", str(film), "ask", "v1", "--shown", "cuts/v01-toned.mp4"]) == 2
    assert "needs a fresh eval" in capsys.readouterr().err
