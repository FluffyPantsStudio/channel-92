"""A new film folder from the kit's template."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..gates import now_text, parse_time
from .layout import FOLDERS, FilmFolder
from .standing import ProjectError, Standing, save_standing, write_atomic
from ..formats import tag

SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def starter_film(name: str) -> dict[str, Any]:
    """film.json for a film with nothing in it yet, in the core spec's shape."""
    return {
        "format": tag("film"), "name": name, "fps": 24, "frame": [1280, 704], "final_size": [1920, 1080],
        "stems": {"mix": "audio/mix.wav", "voice": "audio/voice.wav", "band": "audio/band.wav",
                  "drums": "audio/drums.wav"},
        "lyric": "lyric.txt", "star": None, "wardrobe": {}, "tone": "serious and soulful",
        "vocal_patches": {}, "downbeat_slot": None, "lineup": [],
        "picks": {}, "shift": {}, "hands_by_shot": {}, "crops": {},
    }


def starter_notes(name: str) -> str:
    return (f"# {name}: notes\n\n"
            "The person's answers at each gate, quoted word for word under what was shown and asked. A note holds\n"
            "for this film only unless the person calls it a standing rule. Nothing here is extended by guessing.\n")


def create_project(parent: Path, slug: str, name: str, *, created: str | None = None) -> FilmFolder:
    """Make PARENT/SLUG with every folder and starter file; refuse a folder that already holds anything."""
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ProjectError(f"a film slug is lower-case letters and digits joined by single hyphens, not {slug!r}")
    if not isinstance(name, str) or not name.strip():
        raise ProjectError("a film needs a name")
    stamp = created or now_text()
    try:
        parse_time(stamp)
    except ValueError as problem:
        raise ProjectError(f"created: {problem}") from None
    root = Path(parent) / slug
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ProjectError(f"{root} is not empty; a new film never writes over an old one")
    folder = FilmFolder(root)
    root.mkdir(parents=True, exist_ok=True)
    for sub, _purpose in FOLDERS:
        (root / sub).mkdir()
    write_atomic(folder.film, json.dumps(starter_film(name), indent=1, ensure_ascii=False) + "\n")
    write_atomic(folder.lyric, "")
    write_atomic(folder.notes, starter_notes(name))
    write_atomic(folder.job_log, "")
    save_standing(folder, Standing.new(name, stamp))
    return folder
