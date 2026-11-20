"""A film's setup choices: decisions recorded before anything is generated, not gates.

A gate asks the person one question about something shown. A setup choice is a decision the film is made under:

    aspect  the director's choice of picture shape (16:9, 4:3, 2.39:1 or 9:16, `aspects.py`). It sets film.json
            `frame` (the render frame of the chosen tier) and `final_size` (the delivery size).
    year    the Channel 92 year the film belongs to (1950 to 2010). It only suggests an aspect, and it picks the
            film's era (`eras.py`), whose look `finish` lays on.

Both live in film.json's `setup` block; the person's words go into notes.md word for word, with the date. A frame
and final_size without a `setup` block are not a choice: the aspect still counts as not chosen.
"""

from __future__ import annotations

from datetime import date
from typing import Mapping

from ..aspects import ASPECTS, AspectError, aspect, check_year, suggested_aspect
from ..eras import era_of_year, year_look
from ..gates import reads_as_machine
from .actions import quote
from .layout import FilmFolder

SETUP = "setup"
CHOOSE_ASPECT = f"atomic-flix choose FILM aspect {'|'.join(ASPECTS)} --by NAME --words \"...\""
CHOOSE_YEAR = "atomic-flix choose FILM year YYYY"


def check_chooser(by: str | None) -> None:
    """Refuse (AspectError) a --by that reads as a model or an agent: a setup choice is a person's, as at the gates."""
    if by and reads_as_machine(by):
        raise AspectError(f"{by!r} reads as a model or an agent, not a person; a setup choice is the director's")


def setup_of(film: Mapping) -> dict:
    block = film.get(SETUP)
    return dict(block) if isinstance(block, Mapping) else {}


def chosen_aspect(film: Mapping) -> str | None:
    """The aspect the director chose, or None (a frame without a setup block is not a choice)."""
    name = setup_of(film).get("aspect")
    return name if name in ASPECTS else None


def with_aspect(film: Mapping, name: str, tier: str, by: str) -> dict:
    """FILM with the aspect chosen: the setup block, the render frame of TIER and the delivery size."""
    check_chooser(by)
    row = aspect(name)
    frame = row.frame(tier)
    setup = {**setup_of(film), "aspect": row.name, "tier": tier, "aspect_by": by}
    return {**film, SETUP: setup, "frame": list(frame), "final_size": list(row.delivery)}


def with_year(film: Mapping, year: object, by: str | None = None) -> dict:
    """FILM with its Channel 92 year (checked); the aspect is left as it is."""
    check_chooser(by)
    setup = {**setup_of(film), "year": check_year(year)}
    if by:
        setup["year_by"] = by
    return {**film, SETUP: setup}


def aspect_refusal(film: Mapping) -> str | None:
    """One plain sentence when the aspect is not chosen, else None."""
    if chosen_aspect(film):
        return None
    return (f"this film has no aspect yet, and the director chooses one before anything is planned or shot: "
            f"{CHOOSE_ASPECT}")


def _words_block(by: str | None, words: str | None) -> str:
    if not words:
        return f"Recorded for {by}.\n" if by else ""
    return f"{by or 'The person'}, in their own words:\n\n{quote(words)}"


def aspect_note(film: Mapping, by: str, words: str, today: date | None = None) -> str:
    """The notes.md block for an aspect choice, the words kept exactly."""
    setup = setup_of(film)
    width, height = film["frame"]
    final_w, final_h = film["final_size"]
    stamp = (today or date.today()).isoformat()
    return (f"\n## {stamp}: setup choice, aspect {setup['aspect']}\n\n"
            f"Renders at {width}x{height} ({setup['tier']}), delivered at {final_w}x{final_h}.\n\n"
            + _words_block(by, words))


def year_note(film: Mapping, by: str | None, words: str | None, today: date | None = None) -> str:
    year = setup_of(film)["year"]
    stamp = (today or date.today()).isoformat()
    return (f"\n## {stamp}: setup choice, year {year}\n\n"
            f"The year suggests {suggested_aspect(year)}; the aspect stays the director's choice.\n\n"
            + _words_block(by, words))


def append_note(folder: FilmFolder, block: str) -> None:
    with folder.notes.open("a", encoding="utf-8", newline="\n") as notes:
        notes.write(block)


def era_line(film: Mapping) -> str:
    """What `progress` says of the film's era: the one its year picks, or none."""
    year = setup_of(film).get("year")
    if year is None:
        return ("       no era: the film has no year, so `finish` delivers it without an era look (atomic-flix choose "
                "FILM year YYYY, or finish --era ID)")
    chosen = era_of_year(year)
    return f"ok     era {chosen.id}, {year_look(year).describe()}; `finish` lays it on: {chosen.medium}"


def setup_lines(film: Mapping) -> list[str]:
    """What `progress` says of the setup choices, in its plain-line form. A year the channel was off the air (a
    hand edit of film.json) is a to-do line, never a crash."""
    year = setup_of(film).get("year")
    try:
        if year is not None:
            check_year(year)
    except AspectError as problem:
        return [*_aspect_lines(film, None), f"todo   setup: film.json setup.year {year!r} cannot be used ({problem}); "
                                            f"set it again: {CHOOSE_YEAR}"]
    return [*_aspect_lines(film, year), era_line(film)]


def _aspect_lines(film: Mapping, year: object) -> list[str]:
    setup = setup_of(film)
    name = chosen_aspect(film)
    if name is None:
        hint = f" (year {year} suggests {suggested_aspect(year)})" if year else ""
        given = film.get("frame")
        unchosen = (f"; film.json frame {given[0]}x{given[1]} is not a choice"
                    if isinstance(given, (list, tuple)) and len(given) == 2 else "")
        return [f"todo   setup: aspect not chosen{hint}{unchosen}; after gate 1 the director chooses it, before "
                f"anything is generated: {CHOOSE_ASPECT}"]
    width, height = film.get("frame") or aspect(name).frame(setup.get("tier", "standard"))
    when = f", year {year}" if year else ", no year set (optional: atomic-flix choose FILM year YYYY)"
    return [f"ok     setup: aspect {name} chosen by {setup.get('aspect_by') or 'the director'}, renders at "
            f"{width}x{height}{when}"]


__all__ = ["CHOOSE_ASPECT", "CHOOSE_YEAR", "SETUP", "append_note", "aspect_note", "aspect_refusal", "check_chooser",
           "chosen_aspect", "era_line", "setup_lines", "setup_of", "with_aspect", "with_year", "year_note"]
