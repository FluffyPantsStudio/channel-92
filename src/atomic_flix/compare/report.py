"""Set a film's numbers beside the first film's and write the comparison as plain Markdown."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .baseline import Known
from .measure import Measured
from .metrics import AT_MOST, BELOW_FIRST, METRICS, TARGETS_FROM, UNDER, Metric

SAME_WITHIN = 0.05          # a change of 5 % or less either way is "same"
BETTER, WORSE, SAME, UNKNOWN = "better", "worse", "same", "unknown"
UNFINISHED_KEY = "days_to_acceptance"     # no value here means the film is not accepted yet


@dataclass(frozen=True)
class Row:
    key: str
    label: str
    first: float | None
    this: float | None
    verdict: str
    aim: str
    target_met: str
    first_source: str
    note: str
    digits: int


def verdict(first: float | None, this: float | None) -> str:
    if first is None or this is None:
        return UNKNOWN
    if first == 0:
        return SAME if this == 0 else WORSE
    change = (this - first) / abs(first)
    if abs(change) <= SAME_WITHIN:
        return SAME
    return BETTER if change < 0 else WORSE


def target_met(metric: Metric, first: float | None, this: float | None) -> str:
    rule, limit = metric.aim.rule, metric.aim.limit
    if this is None:
        return UNKNOWN
    if rule == BELOW_FIRST:
        return UNKNOWN if first is None else ("yes" if this < first else "no")
    if rule == AT_MOST:
        return "yes" if this <= limit else "no"
    if rule == UNDER:
        return "yes" if this < limit else "no"
    return UNKNOWN if first is None else ("yes" if this < limit * first else "no")


def compare_film(baseline: Mapping[str, Known], measured: Mapping[str, Measured]) -> tuple[Row, ...]:
    """One row per metric: both values, the verdict, the target and whether it is met."""
    rows = []
    for metric in METRICS:
        known = baseline.get(metric.key, Known(None, "not in the baseline"))
        got = measured.get(metric.key, Measured(None, "not measured"))
        rows.append(Row(key=metric.key, label=metric.label, first=known.value, this=got.value,
                        verdict=verdict(known.value, got.value), aim=metric.aim.describe(known.value),
                        target_met=target_met(metric, known.value, got.value), first_source=known.provenance,
                        note=got.note, digits=metric.digits))
    return tuple(rows)


def _show(value: float | None, digits: int) -> str:
    return "not recorded" if value is None else f"{value:,.{digits}f}"


def render_report(rows: Iterable[Row], *, film_name: str, baseline_name: str) -> str:
    """The comparison as Markdown: a table, then notes on this film's numbers and the first film's sources."""
    rows = tuple(rows)
    lines = [
        f"# {film_name} against {baseline_name}", "",
        "Every number here is better when lower. A verdict is better or worse when the change is over "
        f"{SAME_WITHIN:.0%}, same within it, and unknown when either film has no record of it.", "",
    ]
    if any(row.key == UNFINISHED_KEY and row.this is None for row in rows):
        lines += ["The person has not accepted this film's v1 yet, so its numbers are counts so far.", ""]
    lines += [
        "| Metric | First film | This film | Verdict | Aim | Aim met |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| {row.label} | {_show(row.first, row.digits)} | {_show(row.this, row.digits)} | "
                     f"{row.verdict} | {row.aim} | {row.target_met} |")
    counts = {word: sum(1 for row in rows if row.verdict == word) for word in (BETTER, WORSE, SAME, UNKNOWN)}
    lines += ["", "Verdicts: " + ", ".join(f"{n} {word}" for word, n in counts.items()) + ".", ""]
    notes = [f"- {row.label}: {row.note}" for row in rows if row.note]
    if notes:
        lines += ["## This film's numbers", "", *notes, ""]
    lines += ["## Where the targets come from", ""]
    lines += [f"- {text}." for text in TARGETS_FROM.values()]
    lines += ["- Every other target: below the first film, the roadmap's aim of a better and cheaper film.", ""]
    lines += ["## Where the first film's numbers come from", ""]
    lines += [f"- {row.label}: {row.first_source}" for row in rows]
    return "\n".join(lines) + "\n"
