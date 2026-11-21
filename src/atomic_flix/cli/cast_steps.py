"""`refs`: the characters' reference sheets. One picture per view, the figure alone on a plain background.

`refs FILM` writes a prompt for every view of every character the film has not named yet (plan/refs/), and says which
picture each one makes. Render them with the still graph, the front view first and the others from it, save each as a
PNG at the path printed, and list the views in film.json (`characters.NAME.views`, or `star.views`). `lint` blocks a
film whose sheets are missing a view (CHR1) or whose pictures have an environment behind them (CHR2).
"""

from __future__ import annotations

from typing import Sequence

from ..cast import cast_of, measure_view, missing_views, views_of
from ..cast_board import BoardError, make_board
from ..prompts.sheets import RECIPE, sheet_requests, unique_slugs, write_sheet_prompts
from ..runner.places import film_file
from ..runner.template import TemplateError
from .common import Film, StepError, film_argument, parser


def cast_lines(film: Film) -> list[str]:
    """`progress` lines: each character's sheet, what it lacks, and any view with an environment behind it."""
    rules = film.root / "rules"
    rules_dir = rules if rules.is_dir() else None
    lines = []
    for name, person in cast_of(film.data).items():
        absent = missing_views(person, rules_dir)
        if absent:
            lines.append(f"todo   {name}: the sheet has no {', '.join(absent)} view; `atomic-flix refs FILM` writes "
                         "the prompts (plain background, one picture per view)")
            continue
        faults = _faulty_views(film, person)
        lines.append(f"todo   {name}: {'; '.join(faults)}" if faults
                     else f"ok     {name}: the sheet has all its views, tall, filled, on plain backdrops")
    return lines


def _faulty_views(film: Film, person: dict) -> list[str]:
    """What is wrong with the sheet's pictures, one phrase per view: an environment, too small, or unreadable."""
    faults = []
    for view, path in views_of(person).items():
        try:
            aim = film_file(film.root, path, "view")
            if not aim.is_file():
                continue
            found = measure_view(film.root, aim.relative_to(film.root.resolve()).as_posix())
        except (TemplateError, ValueError, OSError):
            faults.append(f"{view} cannot be read as a PNG")
            continue
        if found.environment():
            faults.append(f"{view} has an environment behind the figure")
        if found.small():
            faults.append(f"{view} is too small (a tall portrait the figure fills)")
    return faults


def _refs(argv: Sequence[str]) -> int:
    p = parser("refs", "Write a prompt for every missing view of every character's reference sheet (plan/refs/): the\n"
                       "whole figure on one flat plain background, no environment. Prints the picture each makes.")
    film_argument(p)
    p.add_argument("--force", action="store_true", help="write a prompt again even where its file is there already")
    p.add_argument("--board", action="store_true",
                   help="make each complete sheet's review board (refs/boards/): every view on one picture")
    args = p.parse_args(argv)
    film = Film.open(args.film)
    rules = film.root / "rules"
    rules_dir = rules if rules.is_dir() else None
    if args.board:
        return _boards(film)
    if not sheet_requests(film.data, rules_dir):
        print("every character's sheet names all its views; `lint` checks the pictures (CHR1, CHR2)")
        return 0
    try:
        made = write_sheet_prompts(film.data, film.root, rules_dir, overwrite=args.force)
    except ValueError as problem:
        raise StepError(str(problem)) from None
    for row, path, wrote in made:
        kept = "" if wrote else "  (kept: the file was there; --force writes it again)"
        print(f"{row['name']:<10} {row['view']:<19} {row['size'][0]}x{row['size'][1]} -> {row['picture']}   "
              f"({film.folder.relative(path)}){kept}")
    print("\nHow, from the films made so far (docs/characters.md):")
    for line in RECIPE:
        print(f"  - {line}")
    print("Make the front view first, the others from it, as tall PNG pictures at those sizes and paths; then list "
          "them in film.json under `views` (`atomic-flix refs FILM --board` makes the review board).")
    return 0


def _boards(film: Film) -> int:
    """Each character's review board, from the views the film names; a character with a view missing is named."""
    cast = cast_of(film.data)
    stems = unique_slugs(cast)
    made = 0
    for name, person in cast.items():
        try:
            path = make_board(film.root, stems[name], person, [str(x) for x in person.get("expressions") or []])
        except BoardError as problem:
            print(f"{name}: no board ({problem})")
            continue
        made += 1
        print(f"{name}: {film.folder.relative(path)}")
    return 0 if made or not cast else 1


COMMANDS = {"refs": ("write the prompts for each character's missing sheet views (plain background, plan/refs/)", _refs)}
