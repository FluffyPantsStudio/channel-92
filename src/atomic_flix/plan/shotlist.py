"""The plain-text shot list a person writes.

One shot per paragraph. The first line is `KEY TYPE` with, for a vocal shot, `: ` and the ids of the lines she sings.
Indented `field: value` lines follow. `act <line id>: <clause>` gives the movement for one sung line; `beat:` may repeat
and lists what happens in a cutaway or silent shot, in order. A `#` after a space starts a comment.

    S02 vocal: v02 v03
      still: stills/S02.png
      setup: salt
      scene: desert       (optional: shots of one scene share a master still, props, aspect and look)
      crop: 0.8
      place: a white salt desert
      act v02: her lips in a soft round oo

    N08 cutaway
      at: 77.6            (a time the person set; or a line id: on the bar line before that line starts)
      figures: yes
      cam_move: locked
      beat: the tub walks toward us on long thin legs
"""

from __future__ import annotations

import re

from .model import KINDS, PlanError, ShotSpec

_TOP_ROW = re.compile(r"^(?P<key>[A-Za-z][\w-]*)\s+(?P<kind>[a-z]+)\s*(?::\s*(?P<lines>.*))?$")
_FIELD = re.compile(r"^(?P<name>[a-z_]+)(?:\s+(?P<arg>[\w-]+))?\s*:\s*(?P<value>.*)$")
_TEXT_FIELDS = ("still", "closing_still", "setup", "framing", "place", "goal", "cam_move", "pin", "at", "outfit",
                "scene")
_YES = {"yes", "true", "y", "1"}
_NO = {"no", "false", "n", "0"}


def _strip_comment(raw: str) -> str:
    return re.split(r"\s#", raw, maxsplit=1)[0].rstrip() if not raw.lstrip().startswith("#") else ""


def _yes_no(value: str, where: str) -> bool:
    low = value.strip().lower()
    if low in _YES:
        return True
    if low in _NO:
        return False
    raise PlanError(f"{where}: expected yes or no, got {value!r}")


def _number(value: str, where: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise PlanError(f"{where}: expected a number, got {value!r}") from None


def _build(head_row: dict, fields: list[tuple[str, str | None, str, int]]) -> ShotSpec:
    spec: dict = {"key": head_row["key"], "kind": head_row["kind"], "sings": head_row["sings"]}
    acts: dict[str, str] = {}
    beats: list[str] = []
    extra: dict[str, str] = {}
    for name, arg, value, number in fields:
        where = f"line {number}"
        if name == "act":
            if not arg:
                raise PlanError(f"{where}: write `act <line id>: <clause>`")
            acts[arg] = value
        elif name == "beat":
            beats.append(value)
        elif name in _TEXT_FIELDS:
            spec[name] = value
        elif name == "crop":
            spec["crop"] = _number(value, where)
        elif name == "late_in":
            spec["late_in"] = _number(value, where)
        elif name in ("count", "takes"):
            spec[name] = int(_number(value, where))
        elif name == "figures":
            spec["figures"] = _yes_no(value, where)
        else:
            extra[name if not arg else f"{name} {arg}"] = value
    return ShotSpec(**spec, acts=acts, beats=tuple(beats), extra=extra)


def parse_shot_list(text: str) -> list[ShotSpec]:
    """Shots in film order from the plain-text list."""
    shots: list[ShotSpec] = []
    head_row: dict | None = None
    fields: list = []
    for number, raw in enumerate(text.splitlines(), start=1):
        body = _strip_comment(raw)
        if not body.strip():
            continue
        if not raw[0].isspace():
            if head_row is not None:
                shots.append(_build(head_row, fields))
            found = _TOP_ROW.match(body.strip())
            if not found or found["kind"] not in KINDS:
                raise PlanError(f"line {number}: expected `KEY vocal|mute|cutaway[: line ids]`, got {body.strip()!r}")
            head_row = {"key": found["key"], "kind": found["kind"], "sings": tuple((found["lines"] or "").split())}
            fields = []
            continue
        if head_row is None:
            raise PlanError(f"line {number}: a field before the first shot")
        found = _FIELD.match(body.strip())
        if not found:
            raise PlanError(f"line {number}: expected `field: value`, got {body.strip()!r}")
        fields.append((found["name"], found["arg"], found["value"].strip(), number))
    if head_row is not None:
        shots.append(_build(head_row, fields))
    keys = [shot.key for shot in shots]
    doubled = sorted({key for key in keys if keys.count(key) > 1})
    if doubled:
        raise PlanError(f"shot keys used twice: {', '.join(doubled)}")
    return shots
