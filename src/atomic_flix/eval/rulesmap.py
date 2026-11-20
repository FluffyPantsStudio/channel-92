"""The rules map (`atomic_flix/data/rules-map.json`): every rule the kit states, with how the eval checks it.

Each entry names the rule's id, its source (lessons.json, its reviewer or after-the-batch questions, or the process
rules of AGENTS.md and the gates), its method (auto, ledger, judge, person, or null for a gap), the unit it is
checked on (shot, scene, film), its level, the gate it is due by (spend or v1) and the eval family that reads it.
`problems` lists every way the map and lessons.json disagree; a test keeps that list empty.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Mapping

from ..formats import check_format
from ..lint.findings import LEVELS
from ..lint.registry import RULE_DATA, rule_ids
from ..plan.vocab import DATA
from .rows import CHECKED_BY_KIT, EVAL_GATES, METHODS

MAP_FILE = DATA / "rules-map.json"
UNITS = ("shot", "scene", "film")
FAMILIES = ("lint", "sent", "ledger", "scene", "cut")
SOURCES = {"lessons:reviewer": "reviewer", "lessons:after_the_batch": "after_the_batch"}
PREFIXES = {"lessons:reviewer": "RV-", "lessons:after_the_batch": "AB-"}
SCOPE_UNITS = {"prompt": "shot", "plan": "shot", "still": "shot", "process": "film"}
DUE_AFTER_SPEND = frozenset({"L127"})   # it checks gate 5's own approval of the hours, so it holds only after it


@lru_cache(maxsize=1)
def load_map() -> dict:
    data = json.loads(MAP_FILE.read_text(encoding="utf-8"))
    check_format("rules-map", data, str(MAP_FILE))
    return data


def entries(family: str | None = None) -> list[dict]:
    """The map's entries in order; with FAMILY, only those that family checks."""
    rows = load_map()["rules"]
    return [dict(row) for row in rows if family is None or row.get("check") == family]


def _entry_problems(row: Mapping) -> list[str]:
    rid = row.get("id", "?")
    found = []
    method, check = row.get("method"), row.get("check")
    if method is not None and method not in METHODS:
        found.append(f"{rid}: method {method!r} is not one of {', '.join(METHODS)} or null")
    for name, allowed in (("unit", UNITS), ("level", LEVELS), ("due", EVAL_GATES)):
        if row.get(name) not in allowed:
            found.append(f"{rid}: {name} {row.get(name)!r} is not one of {', '.join(allowed)}")
    if method in CHECKED_BY_KIT and check not in FAMILIES:
        found.append(f"{rid}: method {method} needs a check family, one of {', '.join(FAMILIES)}")
    if method not in CHECKED_BY_KIT and check is not None:
        found.append(f"{rid}: a {method or 'gap'} rule is not checked by the kit, so its check must be null")
    if method not in CHECKED_BY_KIT and not row.get("why"):
        found.append(f"{rid}: a {method or 'gap'} rule says `why` it is not checked by the kit")
    if row.get("source") == "process" and not row.get("says"):
        found.append(f"{rid}: a process rule carries its wording in `says`")
    return found


def _lessons_rule_problems(rid: str, row: Mapping, rule: Mapping, checked: set[str]) -> list[str]:
    """A lessons.json rule keeps its level, the unit and gate its scope gives, and, when lint checks it, the auto
    method: a rule lint checks cannot be remapped to a judge or the person and so drop out of the verdict."""
    found = []
    if row.get("level") != rule["level"]:
        found.append(f"{rid}: level {row.get('level')} in the map, {rule['level']} in lessons.json")
    if row.get("unit") != SCOPE_UNITS[rule["scope"]]:
        found.append(f"{rid}: unit {row.get('unit')} in the map, {SCOPE_UNITS[rule['scope']]} by its scope")
    due = "v1" if rid in DUE_AFTER_SPEND else "spend"
    if row.get("due") != due:
        found.append(f"{rid}: due {row.get('due')} in the map, {due} by its scope")
    if rid in checked and (row.get("method") != "auto" or row.get("check") != "lint"):
        found.append(f"{rid}: lint checks it, so it must be mapped auto with check lint")
    if row.get("method") == "auto" and rid not in checked:
        found.append(f"{rid}: mapped as an auto lint rule but lint registers no check for it")
    return found


def _lessons_problems(rows: list[Mapping]) -> list[str]:
    index = {rule["id"]: rule for rule in RULE_DATA["rules"]}
    checked = set(rule_ids())
    by_id = {row.get("id"): row for row in rows}
    mapped = {row["id"]: row for row in rows if row.get("source") == "lessons"}
    found = [f"{rid}: in lessons.json without a rules-map entry" for rid in index if rid not in mapped]
    found += [f"{rid}: lint checks it, so its map source must be lessons" for rid in sorted(checked)
              if rid in by_id and rid not in mapped]
    for rid, row in mapped.items():
        if rid not in index:
            found.append(f"{rid}: in the rules map, not in lessons.json")
            continue
        found += _lessons_rule_problems(rid, row, index[rid], checked)
    for source, part in SOURCES.items():
        ids = {PREFIXES[source] + item["id"] for item in RULE_DATA.get(part, [])}
        named = {row["id"] for row in rows if row.get("source") == source}
        found += [f"{rid}: a {part} question without a rules-map entry" for rid in sorted(ids - named)]
        found += [f"{rid}: in the rules map, not a {part} question in lessons.json" for rid in sorted(named - ids)]
    return found


def problems(data: Mapping | None = None) -> list[str]:
    """Every disagreement between the map, its own shape and lessons.json; empty when the map is whole."""
    rows = list((data or load_map())["rules"])
    found = []
    ids = [row.get("id") for row in rows]
    found += [f"{rid}: listed twice" for rid in sorted({rid for rid in ids if ids.count(rid) > 1})]
    for row in rows:
        found += _entry_problems(row)
    sources = set(SOURCES) | {"lessons", "process"}
    found += [f"{row.get('id')}: unknown source {row.get('source')!r}" for row in rows
              if row.get("source") not in sources]
    return found + _lessons_problems(rows)


def gaps() -> list[dict]:
    """Rules with no method: stated by the kit, with no way to check them yet."""
    return [row for row in entries() if row.get("method") is None]
