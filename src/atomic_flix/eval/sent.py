"""The sent-prompt scan: words that must never reach a model, searched in what was sent, not in what was planned.

What was sent is the `wording` of every job file past `planned` (`renders/<key>/rNNN.job.json`, written by the
runner before a job is submitted and kept after it). The word lists are data: each map entry's `words` names a list
in `atomic_flix/data/rules/` (a film's own `rules/<name>.txt` replaces it) or the film's `never` list. Quoted sung
words are left out, as lint does, so a lyric never trips a rule. The same job files say where each input lay.
"""

from __future__ import annotations

from pathlib import Path

from ..lint.text import strip_quoted
from ..plan.vocab import pattern, terms
from ..runner.names import KIT_MAPS
from ..runner.places import film_file, inside
from ..runner.template import TemplateError
from .context import Context, shot_list
from .rows import FAIL, PASS, UNCHECKED, Row, make
from .rulesmap import entries

NEVER = "film.json never"


def _rules_dir(ctx: Context) -> Path | None:
    folder = ctx.root / "rules"
    return folder if folder.is_dir() else None


def _words(entry: dict, ctx: Context) -> tuple[str, ...]:
    name = entry.get("words")
    if name == NEVER:
        return tuple(str(word).lower() for word in ctx.film_field("never", list, []).value or [])
    return terms(name, _rules_dir(ctx))


def _applies(entry: dict, job: dict) -> bool:
    if entry["id"] == "SP-HANDS":
        return bool(job.get("vocal")) or job.get("kind") == "vocal"
    return True


def _hits(entry: dict, job: dict, words: tuple[str, ...]) -> list[str]:
    text = strip_quoted(str(job.get("wording") or ""))
    return list(dict.fromkeys(match.group(0).lower() for match in pattern(words).finditer(text)))


def _path_problems(ctx: Context, job: dict) -> list[str]:
    found = []
    where = f"r{job['n']:03d}"
    inputs = job.get("inputs") or {}
    if not isinstance(inputs, dict):
        return [f"{where}: its inputs are not a mapping of slot to path"]
    for slot, relative in inputs.items():
        try:
            film_file(ctx.root, relative, f"{where} input {slot}")
        except TemplateError as problem:
            found.append(str(problem))
    graph = job.get("graph")
    if graph:
        given = Path(graph)
        try:
            inside(given if given.is_absolute() else ctx.root / given, (ctx.root, KIT_MAPS), f"{where} graph")
        except TemplateError as problem:
            found.append(str(problem))
    return found


def _evidence(entry: dict, ctx: Context, jobs: list[dict]) -> list[str]:
    if entry["id"] == "SP-PATHS":
        return [line for job in jobs for line in _path_problems(ctx, job)]
    words = _words(entry, ctx)
    return [f"r{job['n']:03d}: {', '.join(hits)}" for job in jobs if _applies(entry, job)
            for hits in [_hits(entry, job, words)] if hits]


def _units(ctx: Context) -> dict[str, list[dict]]:
    """Every shot of the list (sent or not), then any other key a job was sent under, with its sent jobs."""
    units: dict[str, list[dict]] = {shot.key: [] for shot in shot_list(ctx)}
    for job in ctx.sent_jobs:
        units.setdefault(job["key"], []).append(job)
    return units


def sent_rows(ctx: Context) -> list[Row]:
    mapped = entries("sent")
    if not ctx.jobs.ok:
        return [make(entry, "film", UNCHECKED, ctx.jobs.problem) for entry in mapped]
    if not ctx.sent_jobs:
        return [make(entry, "film", UNCHECKED, "no render was sent yet (no job file past planned)")
                for entry in mapped]
    rows = []
    never = ctx.film_field("never", list, [])
    for entry in mapped:
        if entry.get("words") == NEVER and not never.ok:
            rows.append(make(entry, "film", UNCHECKED, never.problem))
            continue
        for key, jobs in _units(ctx).items():
            unit = f"shot:{key}"
            if not jobs:
                rows.append(make(entry, unit, PASS, "nothing sent for this shot"))
                continue
            found = _evidence(entry, ctx, jobs)
            rows.append(make(entry, unit, FAIL, "; ".join(found)) if found else
                        make(entry, unit, PASS, f"{len(jobs)} sent job(s) clean"))
    return rows
