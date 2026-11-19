"""Word lists the plan, prompts and lint share. Each list is a plain text file, one term per line, `#` for comments.

Defaults live in `atomic_flix/data/rules/`; a project's own `rules/<name>.txt` replaces a default list of the same name.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
DEFAULT_RULES = DATA / "rules"


@lru_cache(maxsize=None)
def _read(path: str) -> tuple[str, ...]:
    out = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        term = raw.split("#", 1)[0].strip().lower()
        if term:
            out.append(term)
    return tuple(out)


def terms(name: str, rules_dir: Path | None = None) -> tuple[str, ...]:
    """The terms of one list, from the project's rules folder when it has the list."""
    if rules_dir is not None and (Path(rules_dir) / f"{name}.txt").exists():
        return _read(str(Path(rules_dir) / f"{name}.txt"))
    path = DEFAULT_RULES / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"no word list named {name!r} in {DEFAULT_RULES}")
    return _read(str(path))


def pattern(words: tuple[str, ...] | list[str]) -> re.Pattern:
    """Whole-word, case-blind match of any term; a term may be a phrase."""
    if not words:
        return re.compile(r"(?!x)x")
    escaped = sorted((re.escape(word).replace(r"\ ", r"[\s-]+") for word in words), key=len, reverse=True)
    return re.compile(r"(?<![\w-])(?:" + "|".join(escaped) + r")(?![\w-])", re.IGNORECASE)


def find(name: str, text: str, rules_dir: Path | None = None) -> list[str]:
    """Every term of the list found in the text, in order."""
    return [match.group(0) for match in pattern(terms(name, rules_dir)).finditer(text or "")]


def camera_moves(cam_move: str | None, rules_dir: Path | None = None) -> bool:
    """True when the camera description names a move (anything but a locked frame)."""
    return bool(cam_move) and bool(find("camera-moves", cam_move, rules_dir))
