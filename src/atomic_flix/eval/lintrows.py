"""Real-film lint: lessons.json's rules on the film's own book (plan, prompts, stills, gates) and, for the prompt
rules, also on the wording each render was actually sent with. Every finding is bound to its shot; a shot a rule
found nothing on gets a pass row, so a rule is never silently skipped."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from ..lint import Finding, run_rules
from ..lint.registry import RULE_INDEX
from .context import Context, shot_list
from .rows import FAIL, PASS, UNCHECKED, Row, make
from .rulesmap import entries

PER_SHOT = ("prompt", "plan", "still")


def load_film_book(ctx: Context):
    """The book lint itself reads, with the gate facts from standing.json (the `lint` verb's own loader)."""
    # Imported here: the cli package imports the eval verb, which imports this module.
    from ..cli.common import Film, StepError
    from ..cli.shoot_steps import load_checked_book

    try:
        return load_checked_book(Film.open(ctx.root)), None
    except StepError as problem:
        return None, str(problem)


def sent_wordings(ctx: Context) -> dict[str, list[tuple[str, str]]]:
    """Per shot, each distinct wording that was sent and the first job that carried it ("r003")."""
    found: dict[str, list[tuple[str, str]]] = {}
    for job in ctx.sent_jobs:
        wording = job.get("wording")
        if not isinstance(wording, str):
            continue
        seen = found.setdefault(job["key"], [])
        if wording not in [text for text, _ in seen]:
            seen.append((wording, f"r{job['n']:03d}"))
    return found


def _sent_findings(book, wordings: dict[str, list[tuple[str, str]]]) -> list[tuple[Finding, str]]:
    """Prompt-rule findings on the sent wordings: round N takes each shot's Nth distinct wording."""
    found = []
    rounds = max((len(rows) for rows in wordings.values()), default=0)
    for index in range(rounds):
        sent = {key: rows[index] for key, rows in wordings.items() if index < len(rows)}
        trial = replace(book, prompts={key: text for key, (text, _) in sent.items()})
        for finding in run_rules(trial, ["prompt"]):
            if finding.key in sent:
                found.append((finding, f"sent {sent[finding.key][1]}"))
    return found


def _units(entry: dict, shots) -> list[str]:
    scope = RULE_INDEX[entry["id"]]["scope"]
    return [f"shot:{shot.key}" for shot in shots] if scope in PER_SHOT else ["film"]


def _text(finding: Finding, where: str) -> str:
    reason = f" (reason given: {finding.reason})" if finding.reason else ""
    return f"{where}: {finding.message}{reason}"


def _bind(entry: dict, units: list[str], found: Iterable[tuple[Finding, str]]) -> list[Row]:
    evidence: dict[str, list[str]] = {}
    for finding, where in found:
        unit = f"shot:{finding.key}" if finding.key else "film"
        evidence.setdefault(unit, [])
        if _text(finding, where) not in evidence[unit]:
            evidence[unit].append(_text(finding, where))
    rows = [make(entry, unit, FAIL, "; ".join(evidence[unit])) for unit in units if unit in evidence]
    rows += [make(entry, unit, FAIL, "; ".join(lines)) for unit, lines in evidence.items() if unit not in units]
    rows += [make(entry, unit, PASS, "nothing found in the film's files") for unit in units if unit not in evidence]
    return rows


def lint_rows(ctx: Context) -> list[Row]:
    mapped = entries("lint")
    book, problem = load_film_book(ctx)
    if book is None:
        return [make(entry, "film", UNCHECKED, f"lint cannot read the film: {problem}") for entry in mapped]
    findings = [(finding, "film files") for finding in run_rules(book)]
    findings += _sent_findings(book, sent_wordings(ctx))
    by_rule: dict[str, list[tuple[Finding, str]]] = {}
    for finding, where in findings:
        by_rule.setdefault(finding.rule, []).append((finding, where))
    shots = shot_list(ctx) or book.shots
    rows = []
    for entry in mapped:
        rows += _bind(entry, _units(entry, shots), by_rule.get(entry["id"], []))
    return rows
