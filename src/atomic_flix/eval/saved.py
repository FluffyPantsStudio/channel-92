"""A saved eval report read back: `FILM/eval/report.json`, checked for shape, and whether it is stale.

Kept apart from the eval itself, since the gate actions read it before gates 5 and 6. A report of any other shape
raises ReportError, so a reader fails closed instead of trusting or crashing on it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..formats import FormatError, check_format
from ..lint.findings import LEVELS
from .inputs import changed, input_table, standing_view
from .rows import EVAL_GATES, Row

REPORT_JSON = "eval/report.json"
REPORT_MD = "eval/report.md"
TEXT_FIELDS = ("rule", "unit", "verdict", "level", "evidence", "due", "inputs")


class ReportError(ValueError):
    """There is no usable eval report: missing, unreadable, of another format or of another shape."""


def _text_map(value: object, name: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise ReportError(f"{REPORT_JSON} is malformed: {name} is not a map of names to hashes")
    return value


def _row(data: object) -> Row:
    if not isinstance(data, dict) or not all(isinstance(data.get(name, ""), str) for name in TEXT_FIELDS):
        raise ReportError(f"{REPORT_JSON} is malformed: a row is not a record of text fields: {data!r}")
    if not (data.get("method") is None or isinstance(data.get("method"), str)) or data.get("level") not in LEVELS:
        raise ReportError(f"{REPORT_JSON} is malformed: a row has no usable method or level: {data!r}")
    try:
        return Row.from_dict(data)
    except (KeyError, ValueError) as problem:
        raise ReportError(f"{REPORT_JSON} is malformed: {problem}") from None


def report_rows(report: Mapping) -> list[Row]:
    rows = report.get("rows")
    if not isinstance(rows, list):
        raise ReportError(f"{REPORT_JSON} is malformed: rows is not a list")
    return [_row(row) for row in rows]


def _check_shape(data: dict) -> None:
    _text_map(data.get("inputs"), "inputs")
    views = _text_map(data.get("standing_views"), "standing_views")
    if set(views) != set(EVAL_GATES):
        raise ReportError(f"{REPORT_JSON} is malformed: standing_views must name {', '.join(EVAL_GATES)}")
    if not isinstance(data.get("inputs_hash"), str):
        raise ReportError(f"{REPORT_JSON} is malformed: inputs_hash is not text")
    if not (data.get("cut") is None or isinstance(data.get("cut"), str)):
        raise ReportError(f"{REPORT_JSON} is malformed: cut is not text")
    report_rows(data)


def read_report(root: Path | str) -> dict:
    """The saved report, its format and shape checked (ReportError otherwise)."""
    path = Path(root) / REPORT_JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ReportError(f"no eval report ({REPORT_JSON}); run `atomic-flix eval FILM`") from None
    except (OSError, ValueError) as problem:
        raise ReportError(f"{REPORT_JSON} cannot be read: {problem}") from None
    if not isinstance(data, dict) or "format" not in data:
        raise ReportError(f"{REPORT_JSON} is not an eval report")
    try:
        check_format("eval", data, REPORT_JSON)
    except FormatError as problem:
        raise ReportError(str(problem)) from None
    _check_shape(data)
    return data


def _standing_now(root: Path) -> object:
    try:
        return json.loads((root / "standing.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as problem:
        return f"unreadable: {problem}"


def stale_inputs(root: Path | str, report: Mapping, answering: str | None = None) -> list[str]:
    """Inputs added, removed or changed since REPORT was made (empty when it is fresh). With ANSWERING (a gate), a
    standing.json that changed only by asking and answering that gate (`standing_view`) does not count."""
    root = Path(root)
    found = changed(_text_map(report.get("inputs"), "inputs"), input_table(root))
    if answering and "standing.json" in found:
        views = _text_map(report.get("standing_views"), "standing_views")
        if views.get(answering) == standing_view(_standing_now(root), answering):
            found = [name for name in found if name != "standing.json"]
    return found
