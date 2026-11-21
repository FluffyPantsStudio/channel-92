"""ACT1 and ACT2: an action shot is staged in Blender, and the scene it names exists (docs/action.md). The rules' own
bad and good cases run in test_lint_rules; these cover what a case cannot: the reason, the sung shot, the findings."""

from __future__ import annotations

from atomic_flix.lint.book import book_from_case
from atomic_flix.lint.registry import check_rule

CHASE = ["the android sprints down the street and leaps the rail"]


def _found(rule: str, **case):
    return check_rule(rule, book_from_case({"kind": "cutaway", **case}))


def test_an_action_beat_with_no_blender_scene_blocks_and_names_the_words():
    (finding,) = _found("ACT1", shot={"key": "N09", "beats": CHASE})
    assert (finding.level, finding.key) == ("block", "N09")
    assert "sprints" in finding.message
    assert "no_blender" in finding.hint


def test_a_blender_scene_clears_it():
    assert not _found("ACT1", shot={"beats": CHASE, "blender": "scenes/S01.json"}, files=["scenes/S01.json"])


def test_the_persons_written_reason_clears_it():
    assert not _found("ACT1", shot={"beats": CHASE, "no_blender": "one frame of the film's own footage"})


def test_an_empty_reason_does_not_clear_it():
    assert _found("ACT1", shot={"beats": CHASE, "no_blender": " "})


def test_a_calm_shot_is_not_touched():
    assert not _found("ACT1", shot={"beats": ["dust drifts slowly through the light"]})


def test_a_sung_shots_clauses_are_never_read_as_action():
    assert not check_rule("ACT1", book_from_case({"shot": {"acts": {"v01": "she punches the wall"}}}))
    assert not check_rule("ACT4", book_from_case({"shot": {"acts": {"v01": "she kicks off her shoes"}}}))


def test_a_figure_of_speech_is_a_warning_for_a_person_not_a_block():
    case = {"shot": {"beats": ["a tear runs down her cheek"]}}
    assert not _found("ACT1", **case)
    (finding,) = _found("ACT4", **case)
    assert finding.level == "warn" and "runs down" in finding.message


def test_the_persons_reason_in_the_film_answers_the_warning():
    book = book_from_case({"kind": "cutaway", "shot": {"key": "N09", "beats": ["a tear runs down her cheek"]},
                           "film": {"reasons": {"ACT4:N09": "a tear, not a run"}}})
    (finding,) = check_rule("ACT4", book)
    assert finding.reason == "a tear, not a run"


def test_a_plan_older_than_the_shot_list_blocks_either_way():
    blender = {"route": "blender", "blender": {"scene": "scenes/S01.json", "out": "blender/S01", "guide": "depth"}}
    (late,) = _found("ACT3", shot={"blender": "scenes/S01.json"}, files=["scenes/S01.json"])
    assert late.level == "block" and "run `plan` again" in late.message
    (removed,) = _found("ACT3", task=blender)
    assert "none" in removed.message and "scenes/S01.json" in removed.message
    (moved,) = _found("ACT3", shot={"blender": "scenes/other.json"}, task=blender)
    assert "scenes/other.json" in moved.message
    assert not _found("ACT3", shot={"blender": "scenes/S01.json"}, task=blender)
    assert not _found("ACT3")


def test_a_scene_file_that_is_not_there_blocks():
    (finding,) = _found("ACT2", shot={"blender": "scenes/S01.json"}, files=[])
    assert finding.level == "block" and "scenes/S01.json" in finding.message


def test_a_scene_file_that_is_there_passes():
    assert not _found("ACT2", shot={"blender": "scenes/S01.json"}, files=["scenes/S01.json"])
