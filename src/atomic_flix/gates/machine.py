"""The gates as a state machine that only a person's recorded answer moves forward.

Each gate is waiting (nothing put to the person yet, or the last answer was a no), asked (shown and questioned,
no answer yet) or passed (the latest answer was a yes). A gate is asked only once every gate before it has
passed, and work behind a gate calls `require` first. An open gate asked with the wrong thing shown may be asked
again (`ask(..., again=True)`) under the same rules; the ask it replaces stays in the record as superseded, never
deleted. Answers carry how they arrived: "person-direct" (typed by the
person at the terminal), "relayed" (passed on as arguments by whoever ran the command, the person's words quoted) or
"person" (given through the Python API, which does not say). This is bookkeeping, not authentication: a program
cannot prove who typed (docs/gates.md). An answer signed by a model or an agent is refused when it is made and again
when a stored book is loaded, and so is a passing answer dated before its question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Sequence

from .clock import parse_time
from .review import ReviewLoop, ReviewRound
from .steps import GATES, GateRefused, GateSpec, gate_spec

PERSON = "person"                   # through the Python API: how it arrived is not recorded
PERSON_DIRECT = "person-direct"     # typed by the person at the terminal
RELAYED = "relayed"                 # passed on as command arguments, the person's words quoted
PROVENANCES = (PERSON_DIRECT, RELAYED, PERSON)
SCOPES = ("film", "standing")       # a note holds for this film only, unless the person makes it a standing rule
WAITING, ASKED, PASSED = "waiting", "asked", "passed"
STATES = (WAITING, ASKED, PASSED)
CUT_GATE = "v1"

MACHINE_WORDS = frozenset({"claude", "assistant", "model", "llm", "ai", "agent", "subagent", "judge", "reviewer",
                           "driver", "bot", "gpt", "gemini", "llama", "sonnet", "opus", "haiku", "fable"})
MACHINE_ENDINGS = ("s", "es", "bot", "bots")
_NAME_PARTS = re.compile(r"[a-z]+|[0-9]+")


def reads_as_machine(name: str) -> bool:
    """Whether NAME reads as a model or an agent: a part of it (split at spaces, punctuation and between letters and
    digits, in any case) is one of MACHINE_WORDS, or one with a plural or -bot ending ("Claude-2", "agent007",
    "Assistants", "GPT4o", "the model")."""
    for part in _NAME_PARTS.findall(name.lower()):
        if part in MACHINE_WORDS or any(part == word + end for word in MACHINE_WORDS for end in MACHINE_ENDINGS):
            return True
    return False


@dataclass(frozen=True)
class Answer:
    """The person's answer at a gate, kept exactly as they gave it."""

    words: str
    by: str
    provenance: str
    at: str
    scope: str = "film"
    approves: bool = True

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCES:
            raise GateRefused(f"a gate takes a person's answer, typed by them ({PERSON_DIRECT}) or relayed word for "
                              f"word ({RELAYED}); this one's source is {self.provenance!r}")
        if not isinstance(self.by, str) or not self.by.strip():
            raise GateRefused("an answer must name the person who gave it")
        if reads_as_machine(self.by):
            raise GateRefused(f"{self.by!r} reads as a model or an agent, not a person")
        if not isinstance(self.words, str) or not self.words.strip():
            raise GateRefused("an answer needs the person's own words")
        if self.scope not in SCOPES:
            raise GateRefused(f"scope must be one of {', '.join(SCOPES)}, not {self.scope!r}")
        if not isinstance(self.approves, bool):
            raise GateRefused("passes must be true or false")
        try:
            parse_time(self.at)
        except ValueError as problem:
            raise GateRefused(f"answer time: {problem}") from None

    def to_dict(self) -> dict[str, Any]:
        return {"words": self.words, "by": self.by, "provenance": self.provenance, "at": self.at,
                "scope": self.scope, "approves": self.approves}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Answer":
        return cls(words=data.get("words"), by=data.get("by"), provenance=data.get("provenance"), at=data.get("at"),
                   scope=data.get("scope", "film"), approves=data.get("approves", False))


@dataclass(frozen=True)
class PastAsk:
    """An ask that was put right before the person answered it (`ask --again`): kept, never deleted."""

    shown: tuple[str, ...]
    question: str
    asked_at: str
    replaced_at: str

    def to_dict(self) -> dict[str, Any]:
        return {"shown": list(self.shown), "question": self.question, "asked_at": self.asked_at,
                "replaced_at": self.replaced_at}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PastAsk":
        return cls(shown=tuple(data.get("shown") or ()), question=data.get("question") or "",
                   asked_at=data.get("asked_at") or "", replaced_at=data.get("replaced_at") or "")


@dataclass(frozen=True)
class GateRecord:
    """Where one gate stands: what was shown, the question, every answer, every reopening, every ask replaced."""

    gate: str
    state: str = WAITING
    shown: tuple[str, ...] = ()
    question: str = ""
    asked_at: str = ""
    open_errors: tuple[str, ...] = ()
    answers: tuple[Answer, ...] = ()
    reopened: tuple[tuple[str, str], ...] = ()
    superseded: tuple[PastAsk, ...] = ()

    @property
    def spec(self) -> GateSpec:
        return gate_spec(self.gate)

    @property
    def latest(self) -> Answer | None:
        return self.answers[-1] if self.answers else None

    def to_dict(self) -> dict[str, Any]:
        return {"gate": self.gate, "state": self.state, "shown": list(self.shown), "question": self.question,
                "asked_at": self.asked_at, "open_errors": list(self.open_errors),
                "answers": [a.to_dict() for a in self.answers],
                "reopened": [{"at": at, "reason": reason} for at, reason in self.reopened],
                "superseded": [past.to_dict() for past in self.superseded]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GateRecord":
        record = cls(gate=data.get("gate"), state=data.get("state", WAITING),
                     shown=tuple(data.get("shown") or ()), question=data.get("question") or "",
                     asked_at=data.get("asked_at") or "", open_errors=tuple(data.get("open_errors") or ()),
                     answers=tuple(Answer.from_dict(a) for a in data.get("answers") or ()),
                     reopened=tuple((r.get("at"), r.get("reason")) for r in data.get("reopened") or ()),
                     superseded=tuple(PastAsk.from_dict(p) for p in data.get("superseded") or ()))
        gate_spec(record.gate)
        if record.state not in STATES:
            raise GateRefused(f"gate {record.gate}: unknown state {record.state!r}")
        if record.state == PASSED and not (record.latest and record.latest.approves):
            raise GateRefused(f"gate {record.gate} is stored as passed without a passing answer from the person")
        if record.state == PASSED:
            _not_before(record.latest, record.asked_at, record.gate)
        if record.state == ASKED and not record.shown:
            raise GateRefused(f"gate {record.gate} is stored as asked with nothing shown")
        return record


def _not_before(answer: Answer, asked_at: str, gate: str) -> None:
    """Refuse an answer dated before the question it answers."""
    try:
        early = bool(asked_at) and parse_time(answer.at) < parse_time(asked_at)
    except ValueError as problem:
        raise GateRefused(f"gate {gate}: {problem}") from None
    if early:
        raise GateRefused(f"gate {gate}: the answer ({answer.at}) is dated before the question ({asked_at})")


def _single_question(question: str) -> str:
    if not isinstance(question, str) or question.count("?") != 1:
        raise GateRefused(f"a gate asks one question, ending in one question mark: {question!r}")
    return question


@dataclass(frozen=True)
class GateBook:
    """Every gate of one film, plus the cold review loop that stands before each showing of a cut."""

    records: tuple[GateRecord, ...]
    review: ReviewLoop = field(default_factory=ReviewLoop)
    past_reviews: tuple[ReviewLoop, ...] = ()

    @classmethod
    def empty(cls) -> "GateBook":
        return cls(records=tuple(GateRecord(spec.id) for spec in GATES))

    def record(self, gate: str) -> GateRecord:
        return self.records[gate_spec(gate).number - 1]

    def passed(self, gate: str) -> bool:
        return self.record(gate).state == PASSED

    def next_gate(self) -> GateSpec | None:
        """The first gate without a passing answer, or None when all six have passed."""
        for record in self.records:
            if record.state != PASSED:
                return record.spec
        return None

    def require(self, gate: str) -> None:
        """Refuse unless GATE and every gate before it hold a passing answer from the person."""
        aim = gate_spec(gate)
        for record in self.records[:aim.number]:
            if record.state != PASSED:
                spec = record.spec
                raise GateRefused(f"gate {spec.number} ({spec.title}) has no passing answer from the person yet, "
                                  f"so nothing behind gate {aim.number} ({aim.title}) may run")

    def _with(self, record: GateRecord, **changes: Any) -> "GateBook":
        records = list(self.records)
        records[record.spec.number - 1] = record
        return replace(self, records=tuple(records), **changes)

    def ask(self, gate: str, shown: Sequence[str], *, at: str, question: str | None = None,
            again: bool = False) -> "GateBook":
        """Record that SHOWN was put to the person with one question; earlier gates must have passed.

        AGAIN asks an open gate (asked, no answer since) again, when it was asked with the wrong thing shown: the
        earlier ask is kept in the record as superseded, and SHOWN or QUESTION left out keep the earlier ones."""
        spec = gate_spec(gate)
        record = self.record(gate)
        if again:
            return self._ask_again(record, shown, at=at, question=question)
        if record.state == PASSED:
            raise GateRefused(f"gate {spec.number} ({spec.title}) has passed; reopen it before asking again")
        if record.state == ASKED:
            raise GateRefused(f"gate {spec.number} ({spec.title}) is already waiting on the person's answer; to put "
                              "it right before they answer, ask it with --again")
        return self._with(self._asked(record, shown, at=at, question=question or spec.question))

    def _ask_again(self, record: GateRecord, shown: Sequence[str], *, at: str, question: str | None) -> "GateBook":
        spec = record.spec
        head = f"gate {spec.number} ({spec.title})"
        if record.state == PASSED:
            raise GateRefused(f"{head} has the person's yes; reopen it (`gate FILM reopen {spec.id} --reason ...`) "
                              "and ask it again")
        if record.state != ASKED and record.answers:
            raise GateRefused(f"{head} has no open question: the person answered the last one, and that answer "
                              "stays on record; ask it with plain `ask`")
        if record.state != ASKED:
            raise GateRefused(f"{head} has never been asked; ask it with plain `ask`")
        try:
            early = parse_time(at) < parse_time(record.asked_at)
        except ValueError as problem:
            raise GateRefused(f"ask time: {problem}") from None
        if early:
            raise GateRefused(f"{head}: the new ask ({at}) is dated before the one it replaces ({record.asked_at})")
        items = shown if (isinstance(shown, str) or shown) else record.shown
        past = PastAsk(record.shown, record.question, record.asked_at, at)
        asked = self._asked(record, items, at=at, question=question or record.question)
        return self._with(replace(asked, superseded=record.superseded + (past,)))

    def _asked(self, record: GateRecord, shown: Sequence[str], *, at: str, question: str) -> GateRecord:
        """RECORD as asked: SHOWN put to the person at AT with QUESTION, once the machine's rules allow it."""
        spec, gate = record.spec, record.gate
        if spec.number > 1:
            self.require(GATES[spec.number - 2].id)
        items = tuple(shown) if not isinstance(shown, str) else (shown,)
        if not items or not all(isinstance(item, str) and item.strip() for item in items):
            raise GateRefused("a gate needs something shown: name each file or thing put in front of the person")
        try:
            parse_time(at)
        except ValueError as problem:
            raise GateRefused(f"ask time: {problem}") from None
        open_errors: tuple[str, ...] = ()
        if gate == CUT_GATE:
            if not self.review.ready_for(items[0]):
                raise GateRefused(f"{items[0]} has not had a clean cold review (and the rounds have not stalled); "
                                  "review it before the person sees it")
            open_errors = self.review.open_errors
        return replace(record, state=ASKED, shown=items, question=_single_question(question), asked_at=at,
                       open_errors=open_errors)

    def answer(self, gate: str, answer: Answer) -> "GateBook":
        """Record the person's answer to the question now waiting at GATE."""
        spec = gate_spec(gate)
        record = self.record(gate)
        if not isinstance(answer, Answer):
            raise GateRefused("an answer must be an Answer from the person")
        if record.state != ASKED:
            raise GateRefused(f"gate {spec.number} ({spec.title}) has not been asked; show it and ask first")
        _not_before(answer, record.asked_at, gate)
        answered = replace(record, state=PASSED if answer.approves else WAITING, answers=record.answers + (answer,))
        if gate == CUT_GATE:
            return self._with(answered, review=ReviewLoop(), past_reviews=self.past_reviews + (self.review,))
        return self._with(answered)

    def reopen(self, gate: str, reason: str, *, at: str) -> "GateBook":
        """Open a passed gate again (the person changed their mind); work behind it stops until it passes."""
        spec = gate_spec(gate)
        record = self.record(gate)
        if record.state != PASSED:
            raise GateRefused(f"gate {spec.number} ({spec.title}) is not passed, so there is nothing to reopen")
        if not isinstance(reason, str) or not reason.strip():
            raise GateRefused("reopening a gate needs a reason")
        try:
            parse_time(at)
        except ValueError as problem:
            raise GateRefused(f"reopen time: {problem}") from None
        return self._with(replace(record, state=WAITING, reopened=record.reopened + ((at, reason),)))

    def reviewed(self, cut: str, reviewer: str, errors: Sequence[str], *, at: str, cold: bool = True) -> "GateBook":
        """Add a cold review round of CUT; the reviewer must be new to this film."""
        used = [name for loop in self.past_reviews for name in loop.reviewers]
        round_ = ReviewRound(cut=cut, reviewer=reviewer, at=at, errors=tuple(errors), cold=cold)
        return replace(self, review=self.review.add(round_, used=used))

    def to_dict(self) -> dict[str, Any]:
        return {"gates": [r.to_dict() for r in self.records], "review": self.review.to_dict(),
                "past_reviews": [loop.to_dict() for loop in self.past_reviews]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GateBook":
        records = tuple(GateRecord.from_dict(item) for item in data.get("gates") or ())
        if tuple(r.gate for r in records) != tuple(spec.id for spec in GATES):
            raise GateRefused("stored gates are not the six gates in order")
        book = cls(records=records)
        for stored in data.get("past_reviews") or ():
            for round_ in ReviewLoop.from_dict(stored).rounds:
                book = book.reviewed(round_.cut, round_.reviewer, round_.errors, at=round_.at)
            book = replace(book, review=ReviewLoop(), past_reviews=book.past_reviews + (book.review,))
        for round_ in ReviewLoop.from_dict(data.get("review")).rounds:
            book = book.reviewed(round_.cut, round_.reviewer, round_.errors, at=round_.at)
        return book
