"""`choose`: a film's setup choices (aspect and year), recorded before anything is generated.

These are not gates. A gate shows one thing and asks one question; a setup choice is a decision the film is then
made under. The aspect is the director's: `choose FILM aspect 4:3 --by NAME --words "..."` writes film.json's setup
block, its frame and final_size from the aspect table, and the words into notes.md word for word. The year only
suggests an aspect. `plan` and `shoot` refuse while the aspect is not chosen.
"""

from __future__ import annotations

from typing import Sequence

from ..aspects import (ASPECTS, FIRST_YEAR, LAST_YEAR, TIERS, AspectError, aspect, check_year,
                       suggested_aspect)
from ..project.setup import (append_note, aspect_note, aspect_refusal, check_chooser, setup_of, with_aspect,
                             with_year, year_note)
from .common import Film, StepError, film_argument, parser


def choose_aspect(film: Film, name: str, tier: str, by: str, words: str) -> Film:
    """Record the director's aspect: film.json first (refused before anything is written), then the notes."""
    try:
        data = with_aspect(film.data, name, tier, by)
    except AspectError as problem:
        raise StepError(str(problem)) from None
    saved = film.save(data)
    append_note(saved.folder, aspect_note(saved.data, by, words))
    return saved


def choose_year(film: Film, year: object, by: str | None = None, words: str | None = None) -> Film:
    try:
        data = with_year(film.data, year, by)
    except AspectError as problem:
        raise StepError(str(problem)) from None
    saved = film.save(data)
    append_note(saved.folder, year_note(saved.data, by, words))
    return saved


def require_aspect(film: Film) -> None:
    """Refuse (StepError, one sentence) while the director has not chosen the aspect."""
    refusal = aspect_refusal(film.data)
    if refusal:
        raise StepError(refusal)


def require_aspect_of(argv: Sequence[str]) -> None:
    """`require_aspect` for a verb whose first plain argument is the film folder."""
    folder = next((arg for arg in argv if not str(arg).startswith("-")), None)
    if folder is not None:
        require_aspect(Film.open(folder))


def add_setup_arguments(p, *, for_new: bool) -> None:
    """--tier, --by and --words (and, for `new`, --aspect and --year)."""
    if for_new:
        p.add_argument("--aspect", help=f"the director's aspect: {', '.join(ASPECTS)} (needs --by and --words)")
        p.add_argument("--year", help=f"the film's Channel 92 year, {FIRST_YEAR} to {LAST_YEAR} (suggests an aspect)")
    p.add_argument("--tier", default="standard", choices=TIERS, help="render frame: standard, or draft for a look")
    p.add_argument("--by", help="the person who chose (the director)")
    p.add_argument("--words", help="their words, quoted exactly (they go into notes.md word for word)")


def check_new_choices(args, error) -> None:
    """`new --aspect/--year` checked before any folder is made; ERROR (argparse's) exits with the reason."""
    try:
        if args.aspect is not None:
            aspect(args.aspect)
        if args.year is not None:
            check_year(args.year)
        check_chooser(args.by)
    except AspectError as problem:
        error(str(problem))
    if args.aspect is not None and (not args.by or not args.words):
        error("--aspect is the director's choice: give --by (their name) and --words (their words, exactly)")


def apply_new_choices(film: Film, args) -> Film:
    """`new --aspect/--year`: the same records as `choose` (checked first by `check_new_choices`)."""
    if args.year is not None:
        film = choose_year(film, args.year, args.by, None if args.aspect else args.words)
    if args.aspect is not None:
        film = choose_aspect(film, args.aspect, args.tier, args.by, args.words)
    return film


def _choose(argv: Sequence[str]) -> int:
    p = parser("choose", "Record a setup choice, before anything is generated (not a gate). `aspect VALUE` is the\n"
                         f"director's choice of picture shape ({', '.join(ASPECTS)}): it sets film.json setup, frame\n"
                         "and final_size from the aspect table and puts the words into notes.md word for word.\n"
                         f"`year YYYY` ({FIRST_YEAR} to {LAST_YEAR}, the years Channel 92 broadcasts) only suggests an "
                         "aspect.\n`plan` and `shoot` refuse until the aspect is chosen.")
    film_argument(p)
    p.add_argument("what", choices=["aspect", "year"])
    p.add_argument("value", help="the aspect (16:9, 4:3, 2.39:1, 9:16) or the year")
    add_setup_arguments(p, for_new=False)
    args = p.parse_args(argv)
    film = Film.open(args.film)
    if args.what == "year":
        film = choose_year(film, args.value, args.by, args.words)
        year = setup_of(film.data)["year"]
        print(f"year {year} recorded; it suggests {suggested_aspect(year)}, the aspect stays the director's choice")
        return 0
    if not args.by or not args.words:
        p.error("the aspect is the director's choice: give --by (their name) and --words (their words, exactly)")
    film = choose_aspect(film, args.value, args.tier, args.by, args.words)
    width, height = film.data["frame"]
    final_w, final_h = film.data["final_size"]
    print(f"aspect {args.value} recorded: renders at {width}x{height} ({args.tier}), delivered at {final_w}x{final_h}")
    return 0


COMMANDS = {
    "choose": ("record a setup choice before anything is generated: the aspect (the director's) or the year",
               _choose),
}
