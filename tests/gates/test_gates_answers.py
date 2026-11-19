"""How an answer arrived, a missing yes, and answer times (review 2026-11-19, A7 to A9)."""

from __future__ import annotations

import pytest

from atomic_flix.gates import Answer, GateBook, GateRefused

ASKED = "2026-11-19T10:00:00+00:00"


def _answer(**changes) -> Answer:
    fields = {"words": "yes, that one", "by": "Test Person", "provenance": "relayed", "at": "2026-11-19T10:05:00+00:00"}
    fields.update(changes)
    return Answer(**fields)


@pytest.mark.parametrize("provenance", ["person-direct", "relayed", "person"])
def test_both_ways_an_answer_arrives_are_taken(provenance):
    assert _answer(provenance=provenance).provenance == provenance


@pytest.mark.parametrize("provenance", ["model", "agent", "", None, "person-relayed"])
def test_other_sources_are_refused(provenance):
    with pytest.raises(GateRefused):
        _answer(provenance=provenance)


@pytest.mark.parametrize("by", ["Claude", "claude2", "Claude-Opus-5", "assistant_7", "Assistants", "AGENT-007",
                                "agent01", "the model", "Model3", "GPT4o", "gpt-5", "subagent", "LLM", "my-ai",
                                "opus", "Sonnet4", "claude.ai"])
def test_names_that_read_as_a_model_or_agent_are_refused(by):
    with pytest.raises(GateRefused):
        _answer(by=by)


@pytest.mark.parametrize("by", ["Test Person", "Aidan", "Claudette Morel", "Agnes", "Mo Delgado", "Gaia"])
def test_ordinary_names_are_taken(by):
    assert _answer(by=by).by == by


def test_relayed_words_may_not_be_empty():
    with pytest.raises(GateRefused):
        _answer(words="   ")


def test_a_stored_answer_without_approves_is_a_refusal():
    stored = _answer().to_dict()
    del stored["approves"]
    assert Answer.from_dict(stored).approves is False


def test_a_stored_passed_gate_whose_answer_lacks_approves_does_not_load():
    book = GateBook.empty().ask("concept", ["pitches.md"], at=ASKED)
    book = book.answer("concept", _answer())
    data = book.to_dict()
    del data["gates"][0]["answers"][0]["approves"]
    with pytest.raises(GateRefused, match="passed"):
        GateBook.from_dict(data)


def test_an_answer_before_the_question_is_refused():
    book = GateBook.empty().ask("concept", ["pitches.md"], at=ASKED)
    with pytest.raises(GateRefused, match="before"):
        book.answer("concept", _answer(at="2026-11-19T09:59:59+00:00"))
    assert book.answer("concept", _answer(at=ASKED)).passed("concept")


def test_a_stored_passing_answer_older_than_its_question_does_not_load():
    book = GateBook.empty().ask("concept", ["pitches.md"], at=ASKED).answer("concept", _answer())
    data = book.to_dict()
    data["gates"][0]["answers"][0]["at"] = "2026-11-18T10:00:00+00:00"
    with pytest.raises(GateRefused, match="before"):
        GateBook.from_dict(data)
