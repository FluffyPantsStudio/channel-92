"""The director's replies and marks: review/director.json (append-only), review/fixlist.md and the one line back.

director.json holds two lists that only ever grow: `replies` (every reply taken at the desk: gate, outcome, the words
as typed, who, how it arrived, when, how many marks) and `marks` (each item the director marked: gate, item, note,
when, the whole reply it came from, and `after`, how many answers the gate held before that reply). A mark is open
until its gate passes with the director's yes, given after the reply that made the mark and at or after its time.
Everything printed from here goes through `printable`, so a hand-edited file cannot drive the terminal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ..formats import FormatError, check_format, stamped
from ..gates import GateRefused, gate_spec, parse_time
from ..project import FilmFolder, ProjectError, load_standing
from ..project.standing import write_atomic
from .reply import DeskError, Mark, printable

DIRECTOR = "review/director.json"
FIXLIST = "review/fixlist.md"
VIA = "relayed in the Claude app"
OUTCOMES = {"yes": "passed", "redact": "redacted", "question": "question"}
SAID = {"passed": "passed", "redacted": "redacted", "question": "a question, the gate still asked"}


@dataclass(frozen=True)
class Taken:
    """One reply as the desk recorded it."""

    gate: str
    outcome: str
    words: str
    by: str
    at: str
    marks: tuple[Mark, ...] = ()
    after: int | None = None        # how many answers the gate held before this reply


def read_director(root: Path) -> dict[str, list]:
    """director.json as {"replies": [...], "marks": [...]}; empty lists when there is none yet."""
    path = Path(root) / DIRECTOR
    if not path.is_file():
        return {"replies": [], "marks": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        check_format("director", data, DIRECTOR)
    except (OSError, ValueError, FormatError) as problem:
        raise DeskError(f"{DIRECTOR} cannot be read: {problem}") from None
    if not isinstance(data, dict) or not all(isinstance(data.get(key), list) for key in ("replies", "marks")):
        raise DeskError(f"{DIRECTOR} must hold the lists replies and marks")
    return {"replies": list(data["replies"]), "marks": list(data["marks"])}


def append_taken(root: Path, taken: Taken) -> dict[str, list]:
    """Add one reply and its marks to the end of director.json; nothing already there changes."""
    old = read_director(root)
    reply = {"gate": taken.gate, "outcome": taken.outcome, "words": taken.words, "by": taken.by, "via": VIA,
             "at": taken.at, "marks": len(taken.marks)}
    marks = [{"gate": taken.gate, "item": mark.item, "note": mark.note, "at": taken.at, "reply": taken.words,
              **({"after": taken.after} if taken.after is not None else {})} for mark in taken.marks]
    new = {"replies": old["replies"] + [reply], "marks": old["marks"] + marks}
    path = Path(root) / DIRECTOR
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(stamped("director", new), indent=1, ensure_ascii=False) + "\n")
    return new


def _passed_after(answers: Sequence[Any], mark: dict) -> bool:
    """Whether a yes came after MARK: later in the gate's answers than the reply that made it (when the mark says
    where that was) and at or after its time."""
    moment = parse_time(mark["at"])
    after = mark.get("after")
    first = int(after) + 1 if after is not None else 0
    return any(answer.approves and parse_time(answer.at) >= moment for answer in answers[first:])


def open_marks(root: Path) -> list[dict]:
    """The marks whose gate has not passed with a yes since they were made."""
    try:
        book = load_standing(FilmFolder(Path(root))).gates
    except ProjectError as problem:
        raise DeskError(str(problem)) from None
    marks = read_director(root)["marks"]
    try:
        return [mark for mark in marks if not _passed_after(book.record(mark["gate"]).answers, mark)]
    except (GateRefused, KeyError, TypeError, ValueError) as problem:
        raise DeskError(f"{DIRECTOR} holds a mark that cannot be read: {problem}") from None


def counted(number: int, thing: str) -> str:
    return f"{number} {thing}{'' if number == 1 else 's'}"


def _mark_row(mark: dict) -> str:
    item = mark["item"] if mark["item"] is not None else "(no item)"
    return f"- {printable(item)}: {printable(mark['note'])}"


def write_fixlist(root: Path) -> Path:
    """review/fixlist.md: the open marks, grouped by the reply they came from, for the main session."""
    marks = open_marks(root)
    lines = ["# Fix list", "", "The director's open marks, oldest first, words as typed in the Claude app. A mark "
             "closes when its gate passes with the director's yes.", ""]
    if not marks:
        lines.append("Nothing open.")
    seen: tuple[str, str] | None = None
    for mark in marks:
        if (mark["gate"], mark["at"]) != seen:
            seen = (mark["gate"], mark["at"])
            spec = gate_spec(mark["gate"])
            lines += ["", f"## Gate {spec.number}, {spec.title}, {mark['at']}", "",
                      f"Reply: {json.dumps(printable(mark['reply']), ensure_ascii=False)}", ""]
        lines.append(_mark_row(mark))
    path = Path(root) / FIXLIST
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, "\n".join(lines) + "\n")
    return path


def desk_line(root: Path) -> str:
    """ONE line for the main session: the gate, passed or redacted, the director's words, and the open marks."""
    replies = read_director(root)["replies"]
    still_open = counted(len(open_marks(root)), "open mark")
    if not replies:
        return f"no reply at the desk yet; {still_open}"
    last = replies[-1]
    spec = gate_spec(last["gate"])
    words = json.dumps(printable(last["words"]), ensure_ascii=False)
    said = printable(SAID.get(last["outcome"], last["outcome"]))
    return (f"gate {spec.number} ({spec.title}): {said}, {words} "
            f"({printable(last['by'])}, {printable(last.get('via', VIA))}); {still_open}")


def mark_lines(root: Path) -> list[str]:
    """Lines for `progress`: the open director marks, when director.json exists."""
    if not (Path(root) / DIRECTOR).is_file():
        return []
    try:
        marks = open_marks(root)
    except DeskError as problem:
        return [f"error  {DIRECTOR}: {problem}"]
    if not marks:
        return [f"ok     {DIRECTOR}: no open director marks"]
    rows = [f"todo   {FIXLIST}: {counted(len(marks), 'open director mark')}"]
    rows += [f"       gate {gate_spec(m['gate']).number} {_mark_row(m)[2:]}" for m in marks]
    return rows
