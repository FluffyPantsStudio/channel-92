"""Every rule trips on its bad example and passes its good one; reviewer questions are listed, never faked."""

import pytest

from atomic_flix.lint import RULE_DATA, book_from_case, check_rule, preflight, rule_ids

RULES = RULE_DATA["rules"]


def bad_case(rule):
    return rule.get("bad_case", {"prompt": rule["example_bad"]})


def good_case(rule):
    return rule.get("good_case", {"prompt": rule["example_good"]})


@pytest.mark.parametrize("rule", RULES, ids=[rule["id"] for rule in RULES])
def test_rule_trips_on_its_bad_example(rule):
    found = check_rule(rule["id"], book_from_case(bad_case(rule)))
    assert found, f"{rule['id']} did not trip on: {rule['example_bad']}"
    for finding in found:
        assert finding.rule == rule["id"]
        assert finding.level == rule["level"]
        assert finding.lessons == tuple(rule["lessons"])
        assert finding.hint == rule["hint"]


@pytest.mark.parametrize("rule", RULES, ids=[rule["id"] for rule in RULES])
def test_rule_passes_its_good_example(rule):
    found = check_rule(rule["id"], book_from_case(good_case(rule)))
    assert not found, f"{rule['id']} tripped on its good example: {[f.message for f in found]}"


def test_every_rule_in_the_data_has_a_check_and_back():
    assert set(rule_ids()) == {rule["id"] for rule in RULES}


def test_every_lesson_rule_names_a_known_level():
    assert {rule["level"] for rule in RULES} <= {"block", "warn", "note"}


def test_quoted_sung_words_are_not_tested_for_hands():
    book = book_from_case({"prompt": '1-5s: she sings "hold my hand"; she sways gently with the music.'})
    assert not check_rule("H1", book)


def test_a_smile_in_her_eyes_passes_h2_but_a_smile_on_her_mouth_does_not():
    assert not check_rule("H2", book_from_case({"prompt": "While she sings there is a smile in her eyes."}))
    assert check_rule("H2", book_from_case({"prompt": "She sings with a small smile."}))


def test_never_turns_away_is_the_allowed_negative():
    assert not check_rule("H3", book_from_case({"prompt": "Her eyes on us; she never turns away."}))
    assert check_rule("H3", book_from_case({"prompt": "Her eyes on us; she does not smile."}))


def test_hand_words_outside_a_vocal_prompt_are_not_h1():
    book = book_from_case({"kind": "cutaway", "shot": {"figures": True},
                           "prompt": "0-5s: ants walk down her palm and along her wrist."})
    assert not check_rule("H1", book)


def test_findings_name_the_shot():
    found = check_rule("H1", book_from_case({"prompt": "Her hands stay down."}))
    assert found[0].key == "S01"
    assert "hands" in found[0].message


def test_reviewer_questions_are_listed_with_the_still_and_not_answered_for_the_person():
    book = book_from_case({"film": {"characters": {"Frankie": {"identity": "refs/front.png"}}},
                           "still": {"figures": ["Frankie"]}})
    verdict = preflight(book)
    awaiting = {item.id for item in verdict.review if item.key == "S01" and item.answer is None}
    assert {"hands", "mouth", "identity", "gaze", "flat"} <= awaiting
    mouth = next(item for item in verdict.review if item.id == "mouth")
    assert "stills/S01.png" in mouth.question
    assert mouth.lessons == ("L014", "L030")
    assert verdict.blocked


def test_a_recorded_answer_clears_its_question():
    items = {"hands": "PASS", "mouth": "PASS", "gaze": "PASS", "flat": "PASS"}
    book = book_from_case({"still": {"judge": {"verdict": "PASS", "full_size": True, "items": items}}})
    verdict = preflight(book)
    assert not [item for item in verdict.review if item.key == "S01" and item.answer is None]
    assert all(item.answer == "PASS" for item in verdict.review if item.key == "S01")


def test_a_shot_that_picks_up_from_another_may_share_its_first_frame():
    shots = [{"key": "S01", "kind": "cutaway", "still": "stills/S01.png"},
             {"key": "S02", "kind": "cutaway", "still": "stills/S01.png", "extra": {"picks_up_from": "S01"}}]
    assert not check_rule("I1", book_from_case({"shots": shots}))
    shots[1]["extra"] = {"picks_up_from": "S07"}
    assert check_rule("I1", book_from_case({"shots": shots}))
