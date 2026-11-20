"""`evaluate`: every rule of the rules map on a film folder, one row per rule per unit, and the film's verdict.

Each check family (lint, sent prompts, ledger, scenes, cut) yields rows for its own map entries; judge, person and
gap rules come out unchecked with the reason. A family that meets a file of a shape it cannot read gives unchecked
rows naming the problem, and a kit-checkable rule a family left without any row is reported unchecked as a fault of
the eval itself, so no rule is ever silently skipped and no odd file ends the eval with a traceback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from ..gates.clock import now_text
from .context import Context, read_context
from .cutrows import cut_rows, newest_cut
from .inputs import digest, group_files, standing_view
from .ledger import ledger_rows
from .lintrows import lint_rows
from .rows import CHECKED_BY_KIT, EVAL_GATES, UNCHECKED, Row, blocking, make, verdict_at
from .rulesmap import entries
from .scenes import scene_rows
from .sent import sent_rows

FAMILIES: dict[str, Callable[[Context], list[Row]]] = {
    "lint": lint_rows, "sent": sent_rows, "ledger": ledger_rows, "scene": scene_rows, "cut": cut_rows,
}
UNREADABLE = (TypeError, ValueError, KeyError, AttributeError, IndexError)


@dataclass(frozen=True)
class Evaluation:
    """One eval of one film: its rows, the inputs they read and the verdict at gates 5 and 6."""

    film: str
    made_at: str
    stage: str
    rows: tuple[Row, ...]
    inputs: Mapping[str, str]
    cut: str | None = None
    standing_views: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def inputs_hash(self) -> str:
        return digest(self.inputs)

    @property
    def unchecked_by_design(self) -> int:
        return sum(1 for row in self.rows if row.verdict == UNCHECKED and not row.mistaken)

    def verdict(self, gate: str | None = None) -> str:
        return verdict_at(self.rows, gate or self.stage)

    def blockers(self, gate: str | None = None) -> list[Row]:
        return blocking(self.rows, gate or self.stage)


def _unchecked_by_design(entry: dict) -> Row:
    method = entry.get("method")
    kind = "a gap: the kit has no way to check it yet" if method is None else f"method {method}"
    return make(entry, "film", UNCHECKED, f"{kind}; {entry.get('why', '')} (applies per {entry['unit']})")


def _family_rows(ctx: Context, family: str) -> list[Row]:
    stamp = digest(ctx.table, group_files(ctx.root, family))
    try:
        rows = FAMILIES[family](ctx)
    except UNREADABLE as problem:
        rows = [make(entry, "film", UNCHECKED, f"the {family} check cannot read a file of this film: "
                                               f"{type(problem).__name__}: {problem}") for entry in entries(family)]
    return [replace(row, inputs=stamp) for row in rows]


def _stage(ctx: Context) -> str:
    """The gate the film is heading for among 5 and 6: v1 once gate 5 has passed, else spend."""
    gates = (ctx.standing.value or {}).get("gates")
    records = gates.get("gates") if isinstance(gates, dict) else None
    passed = {r.get("gate") for r in records or [] if isinstance(r, dict) and r.get("state") == "passed"}
    return "v1" if "spend" in passed else "spend"


def _standing_raw(root: Path) -> object:
    try:
        return json.loads((root / "standing.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as problem:
        return f"unreadable: {problem}"


def evaluate(root: Path | str) -> Evaluation:
    ctx = read_context(Path(root))
    rows: list[Row] = []
    for family in FAMILIES:
        rows += _family_rows(ctx, family)
    covered = {row.rule for row in rows}
    for entry in entries():
        if entry.get("method") not in CHECKED_BY_KIT:
            rows.append(_unchecked_by_design(entry))
        elif entry["id"] not in covered:
            rows.append(make(entry, "film", UNCHECKED, f"the {entry.get('check')} check gave no row: a fault of the "
                                                       "eval, report it"))
    film = ctx.film.value or {}
    name = str(film.get("name") or ctx.root.name)
    raw = _standing_raw(ctx.root)
    views = MappingProxyType({gate: standing_view(raw, gate) for gate in EVAL_GATES})
    return Evaluation(film=name, made_at=now_text(), stage=_stage(ctx), rows=tuple(rows), inputs=ctx.table,
                      cut=newest_cut(ctx), standing_views=views)


__all__ = ["EVAL_GATES", "Evaluation", "FAMILIES", "evaluate"]
