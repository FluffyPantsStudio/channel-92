"""Scene continuity: shots that carry the same `scene:` tag share one master still, the same prop references, one
aspect and one look.

The master is film.json `scenes.<name>.master` when the person set it, else the first shot of the scene's own still.
Every later still of the scene must list the master in its record's `refs`. A prop's reference is the record's
`props.<name>` when it says so, else a film prop whose `ref` the record lists. The aspect is the record's `size`
([width, height]) or, failing that, the still's own PNG header. The look is the shot list's `look:` or the record's
`look`; shots that state none share the film's. A still path outside the film folder fails, and a shot whose still
record is missing leaves the rule unchecked: nothing passes on no evidence.
"""

from __future__ import annotations

import struct
from pathlib import Path

from .context import Context, Part, read_json_part, shot_list
from .rows import FAIL, PASS, UNCHECKED, Row, make
from .rulesmap import entries

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ASPECT_PLACES = 2


def png_size(path: Path) -> tuple[int, int] | None:
    """Width and height from a PNG's header, or None when the file is not a readable PNG."""
    try:
        with Path(path).open("rb") as handle:
            head = handle.read(24)
    except OSError:
        return None
    if len(head) < 24 or not head.startswith(PNG_SIGNATURE) or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def _scenes(ctx: Context) -> dict[str, list]:
    found: dict[str, list] = {}
    for shot in shot_list(ctx):
        if shot.scene:
            found.setdefault(shot.scene, []).append(shot)
    return found


def _record(ctx: Context, key: str) -> dict | None:
    part = read_json_part(ctx.path(f"stills/{key}.json"), f"stills/{key}.json")
    return part.value if part.ok else None


def _still(ctx: Context, shot) -> Part:
    """The shot's still as a film-relative name (the task's, else the shot list's), or why it is refused."""
    task = read_json_part(ctx.path(f"plan/{shot.key}.task.json"), "task").value or {}
    named = task.get("still") or shot.still_path
    found = ctx.inside(named, f"{shot.key} still")
    return Part(Path(named).as_posix()) if found.ok else found


def _refused(shots, ctx) -> list[str]:
    return [problem for shot in shots for problem in [_still(ctx, shot).problem] if problem]


def _unit(name: str) -> str:
    return f"scene:{name}"


def _master(entry, ctx, name, shots):
    scenes = ctx.film_field("scenes", dict, {})
    declared = ((scenes.value or {}).get(name) or {}) if scenes.ok else {}
    refused = _refused(shots, ctx)
    master = (declared.get("master") if isinstance(declared, dict) else None) or _still(ctx, shots[0]).value
    if refused or not scenes.ok:
        return make(entry, _unit(name), FAIL, "; ".join(refused or [scenes.problem]))
    if not ctx.inside(master, "the scene's master").ok or not (ctx.root / master).is_file():
        return make(entry, _unit(name), UNCHECKED, f"the master still {master} is not in the film folder")
    problems, missing = [], []
    for shot in shots:
        if _still(ctx, shot).value == master:
            continue
        record = _record(ctx, shot.key)
        if record is None:
            missing.append(shot.key)
        elif not isinstance(record.get("refs") or [], list) or master not in (record.get("refs") or []):
            problems.append(f"{shot.key}'s still was not made from the master {master}")
        elif record.get("master") not in (None, master):
            problems.append(f"{shot.key} names {record['master']} as its master, the scene's is {master}")
    if problems:
        return make(entry, _unit(name), FAIL, "; ".join(problems))
    if missing:
        return make(entry, _unit(name), UNCHECKED, f"no still record for {', '.join(missing)}")
    return make(entry, _unit(name), PASS, f"{len(shots)} shot(s) on the master {master}")


def _prop_refs(record: dict, props: dict) -> dict[str, str]:
    if isinstance(record.get("props"), dict):
        return {str(k): str(v) for k, v in record["props"].items()}
    refs = record.get("refs") or []
    refs = set(refs) if isinstance(refs, list) else set()
    return {name: data["ref"] for name, data in props.items() if isinstance(data, dict) and data.get("ref") in refs}


def _props(entry, ctx, name, shots):
    props = ctx.film_field("props", dict, {})
    if not props.ok:
        return make(entry, _unit(name), UNCHECKED, props.problem)
    records = {shot.key: _record(ctx, shot.key) for shot in shots}
    missing = [key for key, record in records.items() if record is None]
    if missing:
        return make(entry, _unit(name), UNCHECKED, f"no still record for {', '.join(missing)}")
    used: dict[str, dict[str, list[str]]] = {}
    for key, record in records.items():
        for prop, ref in _prop_refs(record, props.value).items():
            used.setdefault(prop, {}).setdefault(ref, []).append(key)
    problems = [f"{prop}: " + "; ".join(f"{ref} in {', '.join(keys)}" for ref, keys in refs.items())
                for prop, refs in used.items() if len(refs) > 1]
    if problems:
        return make(entry, _unit(name), FAIL, "more than one reference for a prop: " + " | ".join(problems))
    return make(entry, _unit(name), PASS, f"{len(used)} prop(s), one reference each")


def _aspect_of(ctx: Context, shot) -> float | None:
    still = _still(ctx, shot)
    size = (_record(ctx, shot.key) or {}).get("size") or (png_size(ctx.root / still.value) if still.ok else None)
    try:
        width, height = (float(value) for value in size)
    except (TypeError, ValueError):
        return None
    return round(width / height, ASPECT_PLACES) if height else None


def _aspect(entry, ctx, name, shots):
    refused = _refused(shots, ctx)
    if refused:
        return make(entry, _unit(name), FAIL, "; ".join(refused))
    aspects = {shot.key: _aspect_of(ctx, shot) for shot in shots}
    unknown = [key for key, value in aspects.items() if value is None]
    if unknown:
        return make(entry, _unit(name), UNCHECKED, f"no size for the still of {', '.join(unknown)}")
    if len(set(aspects.values())) > 1:
        listed = ", ".join(f"{key} {value:g}" for key, value in aspects.items())
        return make(entry, _unit(name), FAIL, f"aspects differ: {listed}")
    return make(entry, _unit(name), PASS, f"one aspect, {next(iter(aspects.values())):g}")


def _look(entry, ctx, name, shots):
    looks, missing = {}, []
    for shot in shots:
        record = _record(ctx, shot.key)
        if (shot.extra or {}).get("look") is None and record is None:
            missing.append(shot.key)
        looks[shot.key] = (shot.extra or {}).get("look") or (record or {}).get("look")
    if missing:
        return make(entry, _unit(name), UNCHECKED, f"no still record and no look: for {', '.join(missing)}")
    stated = {key: str(look) for key, look in looks.items() if look}
    if len(set(stated.values())) > 1:
        listed = "; ".join(f"{key} {look!r}" for key, look in stated.items())
        return make(entry, _unit(name), FAIL, f"looks differ: {listed}")
    return make(entry, _unit(name), PASS, f"one look ({next(iter(stated.values()), 'the film look')})")


CHECKS = {"SC-MASTER": _master, "SC-PROPS": _props, "SC-ASPECT": _aspect, "SC-LOOK": _look}


def scene_rows(ctx: Context) -> list[Row]:
    mapped = entries("scene")
    if not ctx.shots.ok:
        return [make(entry, "film", UNCHECKED, ctx.shots.problem) for entry in mapped]
    scenes = _scenes(ctx)
    if not scenes:
        return [make(entry, "film", PASS, "no shot carries a scene tag") for entry in mapped]
    return [CHECKS[entry["id"]](entry, ctx, name, shots) for entry in mapped if entry["id"] in CHECKS
            for name, shots in scenes.items()]
