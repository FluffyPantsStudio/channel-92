"""Rule data (from `atomic_flix/data/lessons.json`) joined to the code that checks it."""

from __future__ import annotations

import json
from typing import Callable, Iterable

from ..plan.vocab import DATA
from .book import Book
from .findings import Finding

RULE_DATA: dict = json.loads((DATA / "lessons.json").read_text(encoding="utf-8"))
RULE_INDEX: dict[str, dict] = {rule["id"]: rule for rule in RULE_DATA["rules"]}
Check = Callable[[Book], Iterable[tuple[str | None, str]]]
_CHECKS: dict[str, Check] = {}


def rule(rule_id: str) -> Callable[[Check], Check]:
    """Register the check for one rule of the data file; a check yields (shot key or None, message)."""
    if rule_id not in RULE_INDEX:
        raise KeyError(f"rule {rule_id} has no entry in lessons.json")

    def register(check: Check) -> Check:
        _CHECKS[rule_id] = check
        return check

    return register


def rule_ids() -> list[str]:
    return list(_CHECKS)


def check_rule(rule_id: str, book: Book) -> list[Finding]:
    data = RULE_INDEX[rule_id]
    reasons = book.film.get("reasons") or {}
    found = []
    for key, message in _CHECKS[rule_id](book):
        reason = reasons.get(f"{rule_id}:{key}") if data["level"] == "warn" else None
        found.append(Finding(rule=rule_id, level=data["level"], key=key, message=message, hint=data["hint"],
                             lessons=tuple(data["lessons"]), reason=reason))
    return found


def run_rules(book: Book, scopes: Iterable[str] | None = None) -> list[Finding]:
    wanted = set(scopes) if scopes else None
    found = []
    for rule_id in _CHECKS:
        if wanted is None or RULE_INDEX[rule_id]["scope"] in wanted:
            found.extend(check_rule(rule_id, book))
    return found
