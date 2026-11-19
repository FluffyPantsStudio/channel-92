"""What vet and preflight return."""

from __future__ import annotations

from dataclasses import dataclass

LEVELS = ("block", "warn", "note")


@dataclass(frozen=True)
class Finding:
    """One rule tripped on one shot (or on the film when `key` is None)."""

    rule: str
    level: str
    key: str | None
    message: str
    hint: str
    lessons: tuple[str, ...] = ()
    reason: str | None = None          # a warn the person has answered in film.json reasons

    def line(self) -> str:
        where = self.key or "film"
        lessons = f" [{', '.join(self.lessons)}]" if self.lessons else ""
        answered = f" (reason: {self.reason})" if self.reason else ""
        return f"{self.level.upper():<5} {self.rule:<5} {where:<6} {self.message}{lessons}{answered}\n      fix: {self.hint}"


@dataclass(frozen=True)
class ReviewItem:
    """A check only a person or a model looking at the picture can make. It is asked, never guessed."""

    key: str
    id: str
    question: str
    lessons: tuple[str, ...]
    answer: str | None = None

    @property
    def awaiting(self) -> bool:
        return self.answer is None

    @property
    def passed(self) -> bool:
        return (self.answer or "").strip().upper().startswith("PASS")


@dataclass(frozen=True)
class Verdict:
    """The result of a preflight: blocked means no GPU time is spent."""

    blocked: bool
    findings: tuple[Finding, ...]
    review: tuple[ReviewItem, ...]
    batch: object | None = None

    def of_level(self, level: str) -> list[Finding]:
        return [finding for finding in self.findings if finding.level == level]

    @property
    def stoppers(self) -> list[Finding]:
        return self.of_level("block")

    @property
    def warns(self) -> list[Finding]:
        return self.of_level("warn")

    @property
    def open_review(self) -> list[ReviewItem]:
        return [item for item in self.review if not item.passed]
