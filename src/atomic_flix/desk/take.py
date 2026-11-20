"""Taking the director's reply at one gate: a yes passes it, a redact answers no word for word and keeps the marks,
a question goes to the notes and leaves the gate asked.

Everything that can be refused is checked before anything is written (the gate, the name, the time, the reply, the
echo of the packet, a readable review/director.json). The writes then go as one: the director record and the notes,
then the gate answer last; when any of them fails, every file the take touched is put back as it was.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..gates import RELAYED, Answer, GateRefused, gate_spec, now_text, parse_time, reads_as_machine
from ..gates.machine import ASKED
from ..project import FilmFolder, ProjectError, answer_gate, load_standing
from ..project.actions import quote
from .ledger import DIRECTOR, FIXLIST, OUTCOMES, VIA, Taken, append_taken, read_director, write_fixlist
from .reply import QUESTION, YES_KIND, DeskError, Reply, normalised, parse_reply, refuse_hostile

PACKET_ROOT = "desk"
MAX_NAME = 80
NAME_MARKS = " .'-"     # besides letters, the only characters a --by name may hold
ECHO_WORDS = 4          # packet text this long or longer is refused anywhere inside a reply; shorter, only whole


def _asked(folder: FilmFolder, gate: str):
    try:
        spec = gate_spec(gate)
        record = load_standing(folder).gates.record(gate)
    except (GateRefused, ProjectError) as problem:
        raise DeskError(str(problem)) from None
    if record.state != ASKED:
        raise DeskError(f"gate {spec.number} ({spec.title}) has not been asked (it is {record.state}); run "
                        f"`atomic-flix gate FILM ask {gate}` and send its packet first")
    return spec, record


def _read_packet_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as problem:
        raise DeskError(f"{path} cannot be read ({problem}); build the packet again with `atomic-flix packet`, so "
                        "the desk can tell its text from the director's reply") from None


def _packet_text(folder: FilmFolder, gate: str, question: str) -> set[str]:
    """The packet's own words (its question, every card line and every caption), which are never a reply."""
    texts = {question}
    packet = folder.root / PACKET_ROOT / gate
    manifest, card = packet / "manifest.json", packet / "card.md"
    if manifest.is_file():
        try:
            texts |= {str(item["caption"]) for item in json.loads(_read_packet_file(manifest))["files"]}
        except (ValueError, KeyError, TypeError) as problem:
            raise DeskError(f"{manifest} cannot be read ({problem}); build the packet again with "
                            "`atomic-flix packet`, so the desk can tell its text from the director's reply") from None
    if card.is_file():
        texts |= set(_read_packet_file(card).splitlines())
    return {normalised(text) for text in texts if normalised(text)}


def _collapsed(text: str) -> str:
    return " ".join(text.lower().split())


def _echoes(reply: str, packet: set[str], question: str) -> bool:
    """Whether REPLY is, or holds, the packet's own text: the question as asked (question mark and all), or a card
    line or caption (punctuation aside; one of under ECHO_WORDS words only when it is the whole reply)."""
    said = normalised(reply)
    padded = f" {said} "
    if _collapsed(question) in _collapsed(reply):
        return True
    return any(said == text or (len(text.split()) >= ECHO_WORDS and f" {text} " in padded) for text in packet)


def _check_by(by: str) -> None:
    if not isinstance(by, str) or not by.strip():
        raise DeskError("a reply needs --by, the director's name")
    refuse_hostile(by, "--by")
    name = by.strip()
    if len(by) > MAX_NAME or not any(char.isalpha() for char in name) or \
            not all(char.isalpha() or char in NAME_MARKS for char in name):
        raise DeskError(f"--by {by!r} is not a name: use letters, spaces and . ' - only")
    if reads_as_machine(by):
        raise DeskError(f"{by!r} reads as a model or an agent, not the director")


def _check_at(at: str | None, record) -> str:
    """The reply's time: --at (checked) or now; never before the question or the gate's last answer."""
    stamp = now_text() if at is None else at
    if at is not None:
        refuse_hostile(at, "--at")
    try:
        moment = parse_time(stamp)
    except ValueError as problem:
        raise DeskError(f"--at: {problem}") from None
    earlier = [("the question", record.asked_at)] + ([("the gate's last answer", record.latest.at)]
                                                     if record.latest else [])
    for what, when in earlier:
        if when and moment < parse_time(when):
            raise DeskError(f"--at {stamp} is before {what} ({when}); a reply comes after what it answers")
    return stamp


def _question_note(folder: FilmFolder, gate: str, reply: Reply, by: str, at: str) -> None:
    spec = gate_spec(gate)
    block = (f"\n## {at}: gate {spec.number}, {spec.title}, a question\n\n{by} (the person; {VIA}), {at}; the gate "
             f"stays asked:\n\n{quote(reply.words)}")
    with folder.notes.open("a", encoding="utf-8", newline="\n") as notes:
        notes.write(block)


def _arrival_note(folder: FilmFolder) -> None:
    with folder.notes.open("a", encoding="utf-8", newline="\n") as notes:
        notes.write(f"Arrived: {VIA} (the director's own typed message, passed in by the gate session).\n")


@contextmanager
def _all_or_nothing(paths: list[Path]) -> Iterator[None]:
    """Put every one of PATHS back as it was when the block fails (a file that was not there is removed)."""
    kept = {path: path.read_bytes() if path.is_file() else None for path in paths}
    try:
        yield
    except BaseException:
        for path, data in kept.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                temporary = path.with_name(path.name + ".restoring")
                temporary.write_bytes(data)
                os.replace(temporary, path)
        raise


def take_reply(root: Path | str, gate: str, text: str, by: str, *, at: str | None = None) -> Taken:
    """Record the director's typed reply TEXT at GATE, given by BY; returns what was recorded."""
    folder = FilmFolder(Path(root))
    spec, record = _asked(folder, gate)
    _check_by(by)
    stamp = _check_at(at, record)
    reply = parse_reply(text)
    if _echoes(reply.words, _packet_text(folder, gate, record.question), record.question):
        raise DeskError("that is the packet's own text, not the director's reply; pass only their typed message")
    read_director(folder.root)
    taken = Taken(gate=gate, outcome=OUTCOMES[reply.kind], words=reply.words, by=by, at=stamp, marks=reply.marks,
                  after=len(record.answers))
    touched = [folder.root / DIRECTOR, folder.root / FIXLIST, folder.notes, folder.standing]
    with _all_or_nothing(touched):
        append_taken(folder.root, taken)
        if reply.kind == QUESTION:
            _question_note(folder, gate, reply, by, stamp)
        else:
            answer = Answer(words=reply.words, by=by, provenance=RELAYED, at=stamp,
                            approves=reply.kind == YES_KIND)
            try:
                answer_gate(folder, gate, answer)
            except (GateRefused, ProjectError) as problem:
                raise DeskError(f"gate {spec.number} ({spec.title}): {problem}") from None
            _arrival_note(folder)
        write_fixlist(folder.root)
    return taken
