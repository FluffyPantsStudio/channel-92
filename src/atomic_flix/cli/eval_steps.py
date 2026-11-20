"""Film step `eval`: every rule of the rules map on the film's own files and process record (docs/eval.md).

    atomic-flix eval FILM [--json] [--gate {5,6}] [--stale-ok]

Run it before asking gate 5 and again before gate 6: both gates are refused while the report is missing, stale or
BLOCKED for that gate.
"""

from __future__ import annotations

import json
from typing import Sequence

from ..eval import BLOCKED, ReportError, eval_refusal, read_report, stale_inputs
from ..eval.report import report_dict, write_report
from ..eval.rows import verdict_at
from ..eval.run import evaluate
from ..eval.saved import report_rows
from .common import Film, StepError, film_argument, parser

GATE_BY_NUMBER = {5: "spend", 6: "v1"}


def _summary(report: dict, stale: list[str]) -> str:
    counts = report.get("counts") or {}
    verdicts = report.get("verdicts") or {}
    gates = "; ".join(f"gate {number} {verdicts.get(gate, '?')}" for number, gate in GATE_BY_NUMBER.items())
    lines = [f"{report.get('verdict', '?')}: {counts.get('fail', 0)} fail, {counts.get('unchecked', 0)} unchecked "
             f"({report.get('unchecked_by_design', '?')} by design: a judge, the person or a gap), "
             f"{counts.get('pass', 0)} pass ({gates})",
             "  CLEAN means nothing the kit can check fails; the rules left by design are not counted"]
    stage = report.get("stage")
    lines += [f"  blocks: {row}" for row in (report.get("blocking") or {}).get(stage, [])]
    if report.get("gaps"):
        lines.append(f"  gaps (no way to check yet): {', '.join(report['gaps'])}")
    if stale:
        lines.append(f"  STALE: {len(stale)} input(s) changed since {report.get('made_at')}: {', '.join(stale[:5])}")
    return "\n".join(lines)


def _check_gate(film: Film, number: int) -> int:
    refusal = eval_refusal(film.root, GATE_BY_NUMBER[number])
    if refusal:
        print(refusal)
        return 1
    print(f"gate {number} may be asked: the eval report is fresh and not BLOCKED for it")
    return 0


def _saved(film: Film, as_json: bool) -> int:
    try:
        report = read_report(film.root)
    except ReportError as problem:
        raise StepError(str(problem)) from None
    stale = stale_inputs(film.root, report)
    print(json.dumps(report, indent=1, ensure_ascii=False) if as_json else _summary(report, stale))
    stage = report.get("stage") if report.get("stage") in GATE_BY_NUMBER.values() else "v1"
    blocked = verdict_at(report_rows(report), stage) == BLOCKED      # the rows decide, not the saved verdict
    return 1 if blocked or stale else 0


def _eval(argv: Sequence[str]) -> int:
    p = parser("eval", "Check that the film honored the kit's rules: lint on the real book and on the prompts that\n"
                       "were sent, the never-words in what was sent, the gate and review ledger, scene continuity\n"
                       "and the cut's own checks. Judge and person rules are listed as unchecked. Writes\n"
                       "eval/report.json and eval/report.md. Exit code 1 when BLOCKED.")
    film_argument(p)
    p.add_argument("--json", action="store_true", help="print the report as JSON instead of the summary")
    p.add_argument("--gate", type=int, choices=sorted(GATE_BY_NUMBER),
                   help="run nothing: say whether gate 5 or 6 may be asked now (exit code 1 when not)")
    p.add_argument("--stale-ok", action="store_true",
                   help="run nothing: show the saved report even when stale, marked so (gates still refuse it)")
    args = p.parse_args(argv)
    film = Film.open(args.film)
    if args.gate is not None:
        return _check_gate(film, args.gate)
    if args.stale_ok:
        return _saved(film, args.json)
    try:
        found = evaluate(film.root)
        data, markdown = write_report(film.root, found)
    except OSError as problem:
        raise StepError(f"the eval could not read or write a file: {problem}") from None
    report = report_dict(found)
    print(json.dumps(report, indent=1, ensure_ascii=False) if args.json else _summary(report, []))
    if not args.json:
        print(f"wrote {film.folder.relative(data)} and {film.folder.relative(markdown)}")
    return 1 if found.verdict() == BLOCKED else 0


COMMANDS = {
    "eval": ("check the film against every rule; eval/report.json and report.md (before gates 5 and 6)", _eval),
}
