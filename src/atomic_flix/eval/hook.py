"""The gate hook: gates 5 (spend) and 6 (v1) are not asked, not answered yes, and gate 5 is not shot under, while the
film's eval is BLOCKED for that gate, stale, or missing.

It fails closed and trusts nothing the report says about itself: the verdict is computed again from the rows, the
inputs must match their own hash, every rule of the rules map must have a row, and a report of any other shape
refuses. At an answer and before shooting, the only change allowed since the eval is the gate's own ask and answer
in standing.json. At gate 6 the cut shown must be the cut the eval read. This is bookkeeping, not tamper-proofing:
whoever can edit the rows can edit their verdicts (docs/eval.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..gates.steps import GateRefused, gate_spec
from .inputs import digest
from .rows import BLOCKED, EVAL_GATES, blocking, verdict_at
from .rulesmap import entries
from .saved import ReportError, read_report, report_rows, stale_inputs

SHOWN = 8


def _listed(items: list[str]) -> str:
    more = f" and {len(items) - SHOWN} more" if len(items) > SHOWN else ""
    return ", ".join(items[:SHOWN]) + more


def _cut_problem(report: dict, shown: Sequence[str] | None) -> str | None:
    cut = report.get("cut")
    if not shown:
        return None
    if cut is None:
        return "the eval found no cut"
    first = str(shown[0]).replace("\\", "/")
    if first.startswith((f"{cut}.", f"{cut}-")):
        return None
    return f"the eval read {cut}, not {first}"


def _refusal(root: Path, gate: str, shown: Sequence[str] | None, answering: bool) -> str | None:
    head = f"gate {gate_spec(gate).number} ({gate_spec(gate).title})"
    try:
        report = read_report(root)
        rows = report_rows(report)
    except ReportError as problem:
        return f"{head} needs a fresh eval: {problem}"
    if digest(report["inputs"]) != report["inputs_hash"]:
        return f"{head}: the eval report's inputs do not match its own hash; run `atomic-flix eval FILM` again"
    absent = sorted({entry["id"] for entry in entries()} - {row.rule for row in rows})
    if absent:
        return f"{head}: the eval report has no row for {_listed(absent)}; run `atomic-flix eval FILM` again"
    stale = stale_inputs(root, report, gate if answering else None)
    if stale:
        return (f"{head}: the eval report is stale ({_listed(stale)} changed since it was made); run "
                "`atomic-flix eval FILM` again")
    if verdict_at(rows, gate) == BLOCKED:
        rules = [f"{row.rule} {row.unit}" for row in blocking(rows, gate)]
        return (f"{head} is held: the eval is BLOCKED by {_listed(rules)}; fix those and run `atomic-flix eval "
                "FILM` again (eval/report.md lists them)")
    problem = _cut_problem(report, shown) if gate == "v1" else None
    return f"{head}: {problem}; evaluate the cut you show" if problem else None


def eval_refusal(root: Path | str, gate: str, shown: Sequence[str] | None = None, *,
                 answering: bool = False) -> str | None:
    """Why GATE may not be asked (or, ANSWERING, answered yes and shot under) now; None when it may. SHOWN is what is
    put to the person; at gate 6 its first item must be the evaluated cut. Gates other than 5 and 6 are never held."""
    if gate not in EVAL_GATES:
        return None
    try:
        return _refusal(Path(root), gate, shown, answering)
    except OSError as problem:
        return f"gate {gate_spec(gate).number}: the eval report cannot be checked: {problem}"


def require_eval(root: Path | str, gate: str, shown: Sequence[str] | None = None, *, answering: bool = False) -> None:
    """Raise GateRefused when GATE may not go on now (see `eval_refusal`)."""
    refusal = eval_refusal(root, gate, shown, answering=answering)
    if refusal:
        raise GateRefused(refusal)
