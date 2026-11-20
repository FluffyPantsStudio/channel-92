"""One eval row (a rule on one unit) and the film's verdict at a gate.

A row is `pass`, `fail` or `unchecked`. An unchecked row of a rule the kit can check itself (method auto or ledger)
is unchecked by mistake: an input it needs is missing or unreadable, and it counts like a failure. An unchecked row
of a judge, person or gap rule is unchecked by design and is listed, never counted as a pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

PASS, FAIL, UNCHECKED = "pass", "fail", "unchecked"
VERDICTS = (PASS, FAIL, UNCHECKED)
METHODS = ("auto", "ledger", "judge", "person")
CHECKED_BY_KIT = ("auto", "ledger")
BLOCKED, WARN, CLEAN = "BLOCKED", "WARN", "CLEAN"
EVAL_GATES = ("spend", "v1")            # the gates the eval stands before: 5 and 6
GATE_NUMBER = {"spend": 5, "v1": 6}


@dataclass(frozen=True)
class Row:
    """One rule's verdict on one unit (`shot:<key>`, `scene:<name>` or `film`)."""

    rule: str
    unit: str
    method: str | None
    verdict: str
    level: str
    evidence: str
    due: str
    inputs: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ValueError(f"{self.rule}: verdict {self.verdict!r} is not one of {', '.join(VERDICTS)}")
        if self.due not in EVAL_GATES:
            raise ValueError(f"{self.rule}: due {self.due!r} is not one of {', '.join(EVAL_GATES)}")

    @property
    def mistaken(self) -> bool:
        """Unchecked although the kit could check it: a missing or unreadable input."""
        return self.verdict == UNCHECKED and self.method in CHECKED_BY_KIT

    def due_by(self, gate: str) -> bool:
        return GATE_NUMBER[self.due] <= GATE_NUMBER[gate]

    def to_dict(self) -> dict:
        return {"rule": self.rule, "unit": self.unit, "method": self.method, "verdict": self.verdict,
                "level": self.level, "evidence": self.evidence, "due": self.due, "inputs": self.inputs}

    @classmethod
    def from_dict(cls, data: Mapping) -> "Row":
        return cls(rule=data["rule"], unit=data["unit"], method=data.get("method"), verdict=data["verdict"],
                   level=data["level"], evidence=data.get("evidence", ""), due=data["due"],
                   inputs=data.get("inputs", ""))


def make(entry: Mapping, unit: str, verdict: str, evidence: str) -> Row:
    """A row for one map entry; method, level and due come from the map."""
    return Row(rule=entry["id"], unit=unit, method=entry.get("method"), verdict=verdict, level=entry["level"],
               evidence=evidence, due=entry["due"])


def blocking(rows: Iterable[Row], gate: str) -> list[Row]:
    """Rows due by GATE that block it: a failed block rule, or a kit-checkable block rule left unchecked."""
    return [row for row in rows if row.due_by(gate) and row.level == "block"
            and (row.verdict == FAIL or row.mistaken)]


def warning(rows: Iterable[Row], gate: str) -> list[Row]:
    """Rows due by GATE that lower the verdict to WARN: a failed warn rule, or one the kit left unchecked."""
    return [row for row in rows if row.due_by(gate) and row.level == "warn"
            and (row.verdict == FAIL or row.mistaken)]


def verdict_at(rows: Iterable[Row], gate: str) -> str:
    """BLOCKED, WARN or CLEAN for GATE, from the rows due by then."""
    rows = list(rows)
    if blocking(rows, gate):
        return BLOCKED
    return WARN if warning(rows, gate) else CLEAN
