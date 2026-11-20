"""The rules map stays whole: every lessons.json rule and question has an entry, no entry names a rule that does not
exist, and every entry says how it is checked (or why it cannot be)."""

from __future__ import annotations

import copy

from atomic_flix.eval.rulesmap import entries, gaps, load_map, problems
from atomic_flix.formats import tag
from atomic_flix.lint.registry import RULE_DATA


def test_the_map_is_whole():
    assert problems() == []


def test_the_map_carries_its_format_tag():
    assert load_map()["format"] == tag("rules-map")


def test_a_lessons_rule_without_a_map_entry_is_a_problem():
    data = copy.deepcopy(load_map())
    data["rules"] = [row for row in data["rules"] if row["id"] != "H1"]
    assert "H1: in lessons.json without a rules-map entry" in problems(data)


def test_a_map_entry_for_a_rule_that_does_not_exist_is_a_problem():
    data = copy.deepcopy(load_map())
    data["rules"].append({**data["rules"][0], "id": "ZZ9"})
    assert "ZZ9: in the rules map, not in lessons.json" in problems(data)


def test_a_reviewer_question_without_an_entry_is_a_problem():
    data = copy.deepcopy(load_map())
    data["rules"] = [row for row in data["rules"] if row["id"] != "RV-hands"]
    assert any(line.startswith("RV-hands:") for line in problems(data))


def test_a_level_that_disagrees_with_lessons_is_a_problem():
    data = copy.deepcopy(load_map())
    first = data["rules"][0]
    first["level"] = "note" if first["level"] != "note" else "block"
    assert any(line.startswith(f"{first['id']}: level") for line in problems(data))


def test_an_unchecked_method_needs_a_reason_and_no_check_family():
    data = copy.deepcopy(load_map())
    row = next(row for row in data["rules"] if row["method"] == "person")
    row.pop("why")
    row["check"] = "ledger"
    found = problems(data)
    assert any("says `why`" in line for line in found) and any("must be null" in line for line in found)


def test_a_lint_rule_cannot_be_remapped_out_of_the_verdict():
    data = copy.deepcopy(load_map())
    row = next(row for row in data["rules"] if row["id"] == "H1")
    row.update(method="person", check=None, why="moved away")
    assert any(line.startswith("H1:") and "auto" in line for line in problems(data))


def test_a_lessons_rule_keeps_the_unit_and_gate_its_scope_gives():
    data = copy.deepcopy(load_map())
    row = next(row for row in data["rules"] if row["id"] == "H1")
    row.update(unit="film", due="v1")
    found = [line for line in problems(data) if line.startswith("H1:")]
    assert any("unit" in line for line in found) and any("due" in line for line in found)


def test_every_lessons_rule_and_question_is_in_the_map():
    ids = {row["id"] for row in entries()}
    assert {rule["id"] for rule in RULE_DATA["rules"]} <= ids
    assert {f"RV-{item['id']}" for item in RULE_DATA["reviewer"]} <= ids
    assert {f"AB-{item['id']}" for item in RULE_DATA["after_the_batch"]} <= ids


def test_the_gaps_are_named():
    assert {row["id"] for row in gaps()} == {"GP-HEAVY", "GP-MINE"}
    assert all(row["why"] for row in gaps())
