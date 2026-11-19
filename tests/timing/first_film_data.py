"""The first film's lyric, labels and hand-fixed line table, read from the fixture pack.

The fixture's build files come from the earlier tools and use their own key
names; this module turns them into this package's inputs (lyric text and
`Label`s) so the package itself never reads that format.
"""

from __future__ import annotations

import json
from pathlib import Path

from atomic_flix.timing.labels import Label

FIRST_FILM = Path(__file__).resolve().parents[2] / "fixtures" / "first-film"


def _old_table() -> list[dict]:
    return json.loads((FIRST_FILM / "build" / "lines.json").read_text(encoding="utf-8"))["lines"]


def lyric_text() -> str:
    """The lyric as sung, with section headers and choir lines in parentheses."""
    out, section = [], None
    for row in _old_table():
        if row.get("section") != section:
            section = row.get("section")
            out.append(f"[{section}]")
        words = row["words"]
        out.append(f"({words})" if row["who"] != "lead" else words)
    return "\n".join(out) + "\n"


def truth() -> list[tuple[float, float]]:
    """(start, end) of every line in the final hand-checked table, in lyric order."""
    return [(row["t0"], row["t1"]) for row in _old_table()]


def hand_fixed() -> list[bool]:
    return [bool(row.get("fixed")) for row in _old_table()]


def labels() -> list[Label]:
    data = json.loads((FIRST_FILM / "build" / "words.json").read_text(encoding="utf-8"))
    return [Label(w["w"], float(w["t0"]), float(w["t1"]), float(w.get("p", 1.0))) for w in data["words"]]
