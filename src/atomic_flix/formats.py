"""Format tags: every JSON file (and every JSON Lines row) the kit writes says what it is and which version.

    {"format": "atomic-flix/pulse@1", ...}

The tag is the first key. A reader may check it with `check_format`; a file without a tag is read as version 1, since
every format here starts at version 1 (nothing written before the tags existed needs migrating). When a format
changes in a way an old reader would misread, its version goes up here and `docs/formats.md` says what changed.
"""

from __future__ import annotations

from typing import Any, Mapping

PREFIX = "atomic-flix/"

# kind -> version. The file each kind names is listed in docs/formats.md.
VERSIONS: dict[str, int] = {
    "film": 1, "standing": 1, "job": 1, "job-log-row": 1, "machine-log-row": 1, "budget": 1,
    "voice-lines": 1, "word-labels": 1, "pulse": 1, "swells": 1, "cuts": 1, "task": 1, "fit": 1,
    "edit": 1, "audit": 1, "strobe": 1, "tone": 1, "review": 1,
    "scene": 1, "scene-plan": 1, "scene-lock": 1, "scene-job": 1, "viewpoint": 1, "capture": 1, "controls": 1,
    "graph-meta": 1, "graph-map": 1, "fixture-truth": 1, "fixture-manifest": 1, "replay": 1,
}


class FormatError(ValueError):
    """A file whose format tag names another kind or a version this kit cannot read."""


def tag(kind: str) -> str:
    return f"{PREFIX}{kind}@{VERSIONS[kind]}"


def stamped(kind: str, data: Mapping[str, Any]) -> dict[str, Any]:
    """`data` with its format tag first (an existing tag is replaced)."""
    return {"format": tag(kind), **{key: value for key, value in data.items() if key != "format"}}


def check_format(kind: str, data: Mapping[str, Any], where: str = "") -> None:
    """Raise FormatError when `data` carries a tag for another kind or another version."""
    found = data.get("format")
    if found is None or found == tag(kind):
        return
    raise FormatError(f"{where or 'file'}: format {found!r} is not {tag(kind)!r}")
