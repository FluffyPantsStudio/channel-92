"""Where the first film's private files are on this machine, from the environment (docs/first-film-replay.md).

`FLIX_FIRST_FILM` names the folder that holds the first film's working tree (its `films/`, `canon/` and
`workflows/` folders and `baseline.json`). Unset, every test that needs it skips with `UNSET` as its reason. The
kit's own test data is synthetic; the first film's data never sits in this repository.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ENV = "FLIX_FIRST_FILM"
FILM_SLUG = "the-girl-in-the-magic-tub"
UNSET = f"{ENV} is not set: point it at the first film's working folder to run this (docs/first-film-replay.md)"
REPO = Path(__file__).resolve().parents[1]
PRIVATE = REPO / "docs" / "private" / "first-film"


def flix_root() -> Path | None:
    """The folder named by FLIX_FIRST_FILM, or None when it is unset or empty."""
    text = os.environ.get(ENV, "").strip()
    return Path(text) if text else None


def film_folder() -> Path | None:
    """The first film's own folder (`films/<slug>` under FLIX_FIRST_FILM), or None when the variable is unset."""
    root = flix_root()
    return root / "films" / FILM_SLUG if root is not None else None


def under_root(*parts: str) -> Path | None:
    """A path under FLIX_FIRST_FILM, or None when the variable is unset."""
    root = flix_root()
    return root.joinpath(*parts) if root is not None else None


def first_film_star() -> str | None:
    """The singer's name as the first film's own book gives it (`character`), so no name is written in this repo;
    None without the film or the field."""
    folder = film_folder()
    book = folder / "book.json" if folder is not None else None
    if book is None or not book.is_file():
        return None
    name = json.loads(book.read_text(encoding="utf-8")).get("character")
    return name if isinstance(name, str) and name.strip() else None


def sung_record() -> Path | None:
    """The first film's record of its sung shots (`canon/<singer>/singing/shots.json`), or None without it."""
    canon = under_root("canon")
    found = sorted(canon.glob("*/singing/shots.json")) if canon is not None and canon.is_dir() else []
    return found[0] if found else None
