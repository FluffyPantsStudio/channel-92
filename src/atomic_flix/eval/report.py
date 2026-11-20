"""The eval's report: `FILM/eval/report.json` ("format": "atomic-flix/eval@1") and a one-page `report.md`."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..formats import stamped
from ..gates.steps import gate_spec
from ..project.standing import write_atomic
from .rows import BLOCKED, CLEAN, EVAL_GATES, FAIL, UNCHECKED, WARN, Row, verdict_at, warning
from .run import Evaluation
from .saved import REPORT_JSON, REPORT_MD

SHOWN_UNCHECKED = 12
MEANING = {CLEAN: "nothing the kit can check fails", WARN: "nothing the kit can check blocks; it warns",
           BLOCKED: "a rule the kit checks blocks"}


def _unit_rule(row: Row) -> str:
    return f"{row.rule} {row.unit}"


def report_dict(found: Evaluation) -> dict:
    counts = Counter(row.verdict for row in found.rows)
    return stamped("eval", {
        "film": found.film, "made_at": found.made_at, "stage": found.stage, "verdict": found.verdict(),
        "verdicts": {gate: found.verdict(gate) for gate in EVAL_GATES},
        "blocking": {gate: [_unit_rule(row) for row in found.blockers(gate)] for gate in EVAL_GATES},
        "counts": {name: counts.get(name, 0) for name in ("pass", "fail", "unchecked")},
        "gaps": sorted({row.rule for row in found.rows if row.method is None}),
        "unchecked_by_design": found.unchecked_by_design, "cut": found.cut,
        "standing_views": dict(found.standing_views), "inputs_hash": found.inputs_hash, "inputs": dict(found.inputs),
        "rows": [row.to_dict() for row in found.rows]})


def _line(row: Row) -> str:
    return f"- **{row.rule}** {row.unit} ({row.method}, {row.level}): {row.evidence}"


def _failures(rows: list[Row], stage: str) -> list[str]:
    due = [row for row in rows if row.due_by(stage)]
    shown = [row for level in ("block", "warn", "note") for row in due
             if row.level == level and (row.verdict == FAIL or row.mistaken)]
    if not shown:
        return ["Nothing fails that is due by this gate.", ""]
    return [f"## Failures ({len(shown)})", ""] + [_line(row) for row in shown] + [""]


def _unchecked(rows: list[Row]) -> list[str]:
    by_design = [row for row in rows if row.verdict == UNCHECKED and not row.mistaken]
    if not by_design:
        return []
    lines = [f"## Unchecked by design ({len(by_design)}): a judge, the person, or a gap", ""]
    lines += [f"- {row.rule} ({row.method or 'gap'}): {row.evidence}" for row in by_design[:SHOWN_UNCHECKED]]
    if len(by_design) > SHOWN_UNCHECKED:
        lines.append(f"- and {len(by_design) - SHOWN_UNCHECKED} more in report.json")
    return lines + [""]


def report_markdown(found: Evaluation) -> str:
    rows = list(found.rows)
    stage = found.stage
    spec = gate_spec(stage)
    counts = Counter(row.verdict for row in rows)
    later = [row for row in rows if not row.due_by(stage)]
    lines = [f"# {found.film}: eval", "",
             f"**{found.verdict()}** before gate {spec.number} ({spec.title}): {MEANING[found.verdict()]}; "
             f"{found.unchecked_by_design} rule(s) are left to a judge, the person or a gap and not counted. "
             + " ".join(f"Gate {gate_spec(g).number}: {verdict_at(rows, g)}." for g in EVAL_GATES), "",
             f"{len(rows)} rows: {counts[FAIL]} fail, {counts[UNCHECKED]} unchecked, {counts['pass']} pass. "
             f"{len(warning(rows, stage))} warning(s). {len(later)} row(s) are not due until a later gate.", ""]
    lines += _failures(rows, stage)
    lines += _unchecked(rows)
    lines += [f"Made {found.made_at}. Inputs hash `{found.inputs_hash[:16]}` over {len(found.inputs)} files; the "
              "report is stale once any of them changes. Every row is in report.json."]
    return "\n".join(lines) + "\n"


def write_report(root: Path | str, found: Evaluation) -> tuple[Path, Path]:
    root = Path(root)
    data, markdown = root / REPORT_JSON, root / REPORT_MD
    data.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(data, json.dumps(report_dict(found), indent=1, ensure_ascii=False) + "\n")
    write_atomic(markdown, report_markdown(found))
    return data, markdown


__all__ = ["REPORT_JSON", "REPORT_MD", "report_dict", "report_markdown", "write_report"]
