"""Film steps around the folder itself: `new` (a film from the template), `status` and `gate` (the person's answers).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from ..gates import GATE_IDS, PERSON_DIRECT, RELAYED, Answer, GateRefused, gate_spec, now_text
from ..project import (FilmFolder, ProjectError, answer_gate, ask_gate, create_project, reopen_gate, validate,
                       where_it_stands)
from ..timing import parse_lyric
from .common import LINEUP_FILE, Film, StepError, film_argument, parser

STEMS = ("mix", "voice", "band", "drums", "choir")
WHAT_STEMS_DO = {
    "mix": "the finished song: the person hears it at gate 2, the cut lays it back over the picture",
    "voice": "the lead vocal alone: `time` reads every line from it and every vocal render hears its own lines",
    "band": "everything but the voice: chords and bass for the bar's one",
    "drums": "the drum stem: the beat grid and kick and snare for the bar's one (else band, else mix)",
    "choir": "backing vocals, only when the lyric has lines in parentheses",
}


def _copy_inputs(film: Film, args) -> Film:
    data = dict(film.data)
    stems = dict(data.get("stems") or {})
    for name in STEMS:
        provenance = getattr(args, "song" if name == "mix" else name)
        if provenance is None:
            continue
        if not Path(provenance).is_file():
            raise StepError(f"--{'song' if name == 'mix' else name}: no file at {provenance}")
        aim = film.path(f"audio/{name}{Path(provenance).suffix.lower() or '.wav'}")
        shutil.copyfile(provenance, aim)
        stems[name] = film.folder.relative(aim)
    data["stems"] = stems
    if args.lyric is not None:
        if not Path(args.lyric).is_file():
            raise StepError(f"--lyric: no file at {args.lyric}")
        film.folder.lyric.write_text(Path(args.lyric).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    data["lineup_rows"] = LINEUP_FILE
    if args.shots is not None:
        if not Path(args.shots).is_file():
            raise StepError(f"--shots: no file at {args.shots}")
        shutil.copyfile(args.shots, film.path(LINEUP_FILE))
    if args.star:
        data["star"] = {"name": args.star, "who": args.who or ""}
    return film.save(data)


def readiness(film: Film) -> list[str]:
    """What the folder lacks before each step, in plain lines: the validator's findings, then the kit's own."""
    stems = film.data.get("stems") or {}
    explained = {stems.get(name) for name in STEMS if name not in ("mix", "voice")}
    lines = [str(finding) for finding in validate(film.folder) if finding.path not in explained]
    lyric = film.folder.lyric.read_text(encoding="utf-8") if film.folder.lyric.is_file() else ""
    if lyric.strip():
        parsed = parse_lyric(lyric)
        parts = sorted({line.part for line in parsed})
        lines.append(f"ok     lyric.txt: {len(parsed)} sung lines ({', '.join(parts)})")
    if not film.lineup_rows.is_file() or not film.lineup_rows.read_text(encoding="utf-8").strip():
        lines.append(f"todo   {LINEUP_FILE}: the shot list is missing; needed by plan (gate 4, the board)")
    star = film.data.get("star") or {}
    if not star.get("name") or not star.get("who"):
        lines.append("todo   film.json: singer.name and singer.who (one sentence from canon, approved by the person) "
                     "are needed by the still prompts")
    for name in STEMS:
        relative = stems.get(name)
        if relative and film.stem(name) is None:
            lines.append(f"       {relative} is {WHAT_STEMS_DO[name]}" if name in ("mix", "voice")
                         else f"todo   {relative}: {WHAT_STEMS_DO[name]}")
    return lines


def _new(argv: Sequence[str]) -> int:
    p = parser("new", "Make a film folder from the template: the folders, film.json, notes.md, standing.json and an\n"
                      "empty ledger, with the stems, lyric and shot list copied in. Then say what is still missing.")
    p.add_argument("film", type=Path, help="the new folder; its last part is the film's slug (lower case, hyphens)")
    p.add_argument("--name", help="the film's title (default: from the slug)")
    p.add_argument("--song", type=Path, help="the finished mix (WAV)")
    for name in STEMS[1:]:
        p.add_argument(f"--{name}", type=Path, help=f"the {name} stem (WAV)")
    p.add_argument("--lyric", type=Path, help="the lyric as sung: repeats written out, [Section] lines, backing in ()")
    p.add_argument("--shots", type=Path, help="the shot list (plain text, one shot per paragraph)")
    p.add_argument("--star", help="the singer's name as the prompts write it")
    p.add_argument("--who", help="one sentence from canon saying who the singer is")
    p.add_argument("--dry-run", action="store_true", help="build it in a temporary folder, report, keep nothing")
    args = p.parse_args(argv)
    aim = args.film
    name = args.name or aim.name.replace("-", " ").title()
    if args.dry_run:
        with tempfile.TemporaryDirectory() as scratch:
            film = _make(Path(scratch), aim.name, name, args)
            account = readiness(film)
        print(f"dry run: {aim} was not written. A new film there would have every folder and starter file;")
        print("this is what it would still need, error first:")
    else:
        film = _make(aim.parent, aim.name, name, args)
        account = readiness(film)
        print(f"made {film.root}")
    print("\n".join(account) if account else "nothing missing")
    return 0


def _make(parent: Path, slug: str, name: str, args) -> Film:
    try:
        folder = create_project(parent, slug, name)
    except ProjectError as problem:
        raise StepError(str(problem)) from None
    return _copy_inputs(Film.open(folder.root), args)


def _progress(argv: Sequence[str]) -> int:
    p = parser("progress", "Where the film stands: the next gate and its question, then everything missing or stale.")
    film_argument(p)
    film = Film.open(p.parse_args(argv).film)
    print(where_it_stands(film.folder))
    findings = readiness(film)
    print("\n".join(findings) if findings else "nothing missing or stale")
    return 1 if any(line.startswith("error") for line in findings) else 0


def _typed(label: str) -> str:
    print(label, end="", flush=True)
    return sys.stdin.readline().rstrip("\r\n")


def _answer(film: FilmFolder, args, error) -> None:
    """Record an answer and how it arrived: words passed as --words were relayed by whoever ran the command; with
    no --words at a terminal the person types them here (person-direct). Neither proves who typed (docs/gates.md)."""
    if args.words is not None:
        if not args.by:
            error("a relayed answer needs --by (the person's name) and --words (their words, quoted exactly)")
        by, words, provenance = args.by, args.words, RELAYED
    elif sys.stdin.isatty():
        by = args.by or _typed("Your name: ")
        words = _typed(f"Your answer at gate {gate_spec(args.gate).number}, in your own words: ")
        provenance = PERSON_DIRECT
    else:
        error("answer needs --by and --words (relayed, quoted exactly), or a terminal for the person to type at")
    answer = Answer(words=words, by=by, provenance=provenance, at=args.at or now_text(),
                    scope="standing" if args.standing_rule else "film", approves=not args.no)
    answer_gate(film, args.gate, answer)


def _gate(argv: Sequence[str]) -> int:
    p = parser("gate", "Record the person's part at one of the six gates. `ask` records what was shown and the one\n"
                       "question; `answer` records the person's words exactly and how they arrived (typed here, or\n"
                       "relayed with --words; bookkeeping, not proof of who typed: docs/gates.md); `reopen` opens\n"
                       f"a passed gate again. Gates, in order: {', '.join(GATE_IDS)}.")
    film_argument(p)
    p.add_argument("action", choices=["show", "ask", "answer", "reopen"])
    p.add_argument("gate", nargs="?", choices=GATE_IDS)
    p.add_argument("--shown", action="append", default=[], help="ask: a file or thing put in front of the person")
    p.add_argument("--question", help="ask: the one question (default: the gate's own)")
    p.add_argument("--by", help="answer: the person's name")
    p.add_argument("--words", help="answer: the person's words, quoted exactly (recorded as relayed); leave it out "
                                   "at a terminal and the person types them (recorded as typed by the person)")
    p.add_argument("--no", action="store_true", help="answer: the person said no; the gate stays open")
    p.add_argument("--standing-rule", action="store_true", help="answer: the person made it a standing rule")
    p.add_argument("--reason", help="reopen: why, in the person's words")
    p.add_argument("--at", help="an ISO 8601 time (default: now)")
    args = p.parse_args(argv)
    film = Film.open(args.film)
    if args.action != "show" and not args.gate:
        p.error(f"{args.action} needs a gate")
    try:
        if args.action == "ask":
            _ask(film, args)
        elif args.action == "answer":
            _answer(film.folder, args, p.error)
        elif args.action == "reopen":
            reopen_gate(film.folder, args.gate, args.reason or "", at=args.at)
    except (GateRefused, ProjectError) as problem:
        raise StepError(str(problem)) from None
    print(where_it_stands(film.folder))
    return 0


def _ask(film: Film, args) -> None:
    shown = list(args.shown)
    if args.gate == "spend":
        budget = film.path("plan/budget.json")
        if not budget.is_file():
            raise StepError("gate 5 shows the hours: run `atomic-flix budget` first")
        shown = shown or ["plan/report.md", "plan/budget.json"]
    if not shown:
        raise StepError(f"name what is shown at gate {gate_spec(args.gate).number} with --shown")
    ask_gate(film.folder, args.gate, shown, at=args.at, question=args.question)


COMMANDS = {
    "new": ("make a film folder from the template, copy the stems in, list what is missing", _new),
    "progress": ("the next gate, and what is missing or stale in the folder", _progress),
    "gate": ("record what the person was shown and their answer, word for word", _gate),
}
