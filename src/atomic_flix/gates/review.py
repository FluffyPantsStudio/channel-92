"""Cold review rounds: a cut goes to a fresh reviewer, round after round, before the person sees it.

A reviewer is cold when it has not read the prompts, and fresh when it has not reviewed anything of this film
before. The loop is ready for the person when the latest round, on that very cut, names no clear errors. If the
rounds stop making progress the loop is stalled: the cut goes to the person anyway, with what is still open.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .clock import parse_time
from .steps import GateRefused

MAX_ROUNDS = 6           # rounds without a clean review before the loop counts as stalled
FLAT_SPAN = 2            # rounds over which the open errors must fall


def _text(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GateRefused(f"{what} must be non-empty text, got {value!r}")
    return value


@dataclass(frozen=True)
class ReviewRound:
    """One cold reviewer's reading of one cut: the clear errors it named (none means clean)."""

    cut: str
    reviewer: str
    at: str
    errors: tuple[str, ...] = ()
    cold: bool = True

    def __post_init__(self) -> None:
        _text(self.cut, "the reviewed cut")
        _text(self.reviewer, "the reviewer's id")
        try:
            parse_time(self.at)
        except ValueError as problem:
            raise GateRefused(f"review time: {problem}") from None
        errors = tuple(self.errors) if not isinstance(self.errors, str) else (self.errors,)
        for error in errors:
            _text(error, "each error")
        object.__setattr__(self, "errors", errors)
        if self.cold is not True:
            raise GateRefused(f"reviewer {self.reviewer} has read the prompts; only a cold reviewer counts")

    def to_dict(self) -> dict[str, Any]:
        return {"cut": self.cut, "reviewer": self.reviewer, "at": self.at, "errors": list(self.errors)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewRound":
        return cls(cut=data.get("cut"), reviewer=data.get("reviewer"), at=data.get("at"),
                   errors=tuple(data.get("errors") or ()), cold=data.get("cold", True))


@dataclass(frozen=True)
class ReviewLoop:
    """The rounds before one showing of a cut to the person."""

    rounds: tuple[ReviewRound, ...] = ()

    @property
    def reviewers(self) -> tuple[str, ...]:
        return tuple(r.reviewer for r in self.rounds)

    @property
    def open_errors(self) -> tuple[str, ...]:
        return self.rounds[-1].errors if self.rounds else ()

    @property
    def is_clean(self) -> bool:
        return bool(self.rounds) and not self.rounds[-1].errors

    @property
    def stalled(self) -> str | None:
        """Why the rounds stopped making progress, or None while they still are (or the loop is clean)."""
        if not self.rounds or self.is_clean:
            return None
        if len(self.rounds) >= MAX_ROUNDS:
            return f"{len(self.rounds)} rounds without a clean review"
        if len(self.rounds) > FLAT_SPAN:
            before = len(self.rounds[-1 - FLAT_SPAN].errors)
            now = len(self.rounds[-1].errors)
            if now >= before:
                return f"open errors went from {before} to {now} over the last {FLAT_SPAN} rounds"
        return None

    def add(self, round_: ReviewRound, *, used: Iterable[str] = ()) -> "ReviewLoop":
        """A new loop with ROUND_ added; its reviewer must not appear in this loop or in USED."""
        if round_.reviewer in self.reviewers or round_.reviewer in set(used):
            raise GateRefused(f"reviewer {round_.reviewer} has reviewed this film before; a round needs a fresh one")
        return ReviewLoop(self.rounds + (round_,))

    def ready_for(self, cut: str) -> bool:
        """True when CUT may go to the person: its own round was clean, or the loop stalled on it."""
        if not self.rounds or self.rounds[-1].cut != cut:
            return False
        return self.is_clean or self.stalled is not None

    def to_dict(self) -> dict[str, Any]:
        return {"rounds": [r.to_dict() for r in self.rounds]}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReviewLoop":
        loop = cls()
        for item in (data or {}).get("rounds", []):
            loop = loop.add(ReviewRound.from_dict(item))
        return loop
