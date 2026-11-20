"""The eval of the eval: a synthetic film and its clean twin. Each injected violation, one per way of checking (lint
on the real book, the ledger, scene continuity, the prompts as sent, the cut's own checks), must be flagged by its
rule id on its unit, and the clean twin must come out CLEAN with nothing failing and nothing left unchecked by
mistake. If this test fails, the eval no longer proves what it claims to."""

from __future__ import annotations

import contextlib
import io
import shutil

import pytest

from atomic_flix.eval.rows import CHECKED_BY_KIT, FAIL, UNCHECKED
from atomic_flix.eval.rulesmap import entries
from atomic_flix.eval.run import evaluate
from eval_film import INJECTIONS, build_film, scene_other_look


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    with contextlib.redirect_stdout(io.StringIO()):          # the plan stage prints its cuts
        return build_film(tmp_path_factory.mktemp("clean"))


@pytest.fixture
def film(built, tmp_path):
    return shutil.copytree(built, tmp_path / built.name)


def _bad(found) -> list[tuple[str, str]]:
    return [(row.rule, row.unit) for row in found.rows if row.verdict == FAIL or row.mistaken]


def test_the_clean_twin_is_clean(film):
    found = evaluate(film)
    assert found.stage == "v1"
    assert _bad(found) == []
    assert found.verdict("spend") == found.verdict("v1") == "CLEAN"


def test_every_rule_the_kit_checks_gave_a_real_row_on_the_clean_twin(film):
    found = evaluate(film)
    for entry in entries():
        rows = [row for row in found.rows if row.rule == entry["id"]]
        assert rows, entry["id"]
        if entry.get("method") in CHECKED_BY_KIT:
            assert all("fault of the eval" not in row.evidence for row in rows), entry["id"]
            assert all(len(row.inputs) == 64 for row in rows), entry["id"]


def test_judge_person_and_gap_rules_are_unchecked_with_their_reason(film):
    found = evaluate(film)
    for entry in entries():
        if entry.get("method") in CHECKED_BY_KIT:
            continue
        rows = [row for row in found.rows if row.rule == entry["id"]]
        assert [row.verdict for row in rows] == [UNCHECKED], entry["id"]
        assert entry["why"] in rows[0].evidence


@pytest.mark.parametrize("name", sorted(INJECTIONS))
def test_each_injected_violation_is_flagged_by_its_rule(film, name):
    inject, rule, unit = INJECTIONS[name]
    inject(film)
    found = evaluate(film)
    assert (rule, unit) in _bad(found), _bad(found)
    level = next(entry["level"] for entry in entries() if entry["id"] == rule)
    if level == "block":
        assert found.verdict("v1") == "BLOCKED"
        assert any(row.rule == rule for row in found.blockers("v1"))
    else:
        assert found.verdict("v1") in ("WARN", "BLOCKED")


def test_every_kit_checked_process_rule_has_an_injection():
    injected = {rule for _, rule, _ in INJECTIONS.values()}
    process = {entry["id"] for entry in entries() if entry["source"] == "process" and entry.get("check")}
    assert process - injected == {"LG-LOAD", "SP-HANDS"}       # both tested on their own below


def test_a_record_the_gate_machine_refuses_fails_lg_load(film):
    INJECTIONS["ledger-person"][0](film)
    assert ("LG-LOAD", "film") in _bad(evaluate(film))


def test_two_looks_in_one_scene_warn(film):
    scene_other_look(film)
    found = evaluate(film)
    assert _bad(found) == [("SC-LOOK", "scene:dunes")]
    assert found.verdict("v1") == "WARN"


def test_the_injections_cover_every_way_of_checking():
    families = {entry["id"]: entry["check"] for entry in entries() if entry.get("check")}
    covered = {families[rule] for _, rule, _ in INJECTIONS.values()}
    assert covered == {"lint", "ledger", "scene", "sent", "cut"}


def test_a_lint_rule_also_reads_the_wording_that_was_sent(film):
    job = film / "renders" / "S01" / "r001.job.json"
    text = job.read_text(encoding="utf-8").replace('"wording": "', '"wording": "Her hands rest on the rail. ', 1)
    job.write_text(text, encoding="utf-8")
    found = evaluate(film)
    rows = [row for row in found.rows if row.rule == "H1" and row.unit == "shot:S01"]
    assert [row.verdict for row in rows] == [FAIL] and "sent r001" in rows[0].evidence
    assert ("SP-HANDS", "shot:S01") in _bad(found)


def test_nothing_sent_leaves_the_sent_rows_unchecked_and_blocks_v1(film):
    shutil.rmtree(film / "renders")
    found = evaluate(film)
    sent = [row for row in found.rows if row.rule.startswith("SP-")]
    assert sent and all(row.verdict == UNCHECKED and row.mistaken for row in sent)
    assert found.verdict("v1") == "BLOCKED" and found.verdict("spend") == "CLEAN"


def test_a_missing_cut_result_is_unchecked_never_a_pass(film):
    (film / "cuts" / "v01-toned-strobe.json").unlink()
    found = evaluate(film)
    flash = [row for row in found.rows if row.rule == "CT-FLASH"]
    assert [row.verdict for row in flash] == [UNCHECKED] and "missing" in flash[0].evidence
