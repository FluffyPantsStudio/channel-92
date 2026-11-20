"""`packet FILM GATE`: the phone-ready files for one asked gate, in send order, with manifest.json and card.md.

The packet is written under the film's desk/ folder (desk/<gate>/ by default; --out names another folder under
desk/) and carries only the film's own files. Its scratch files go to a folder of the build's own, made with
tempfile.mkdtemp inside the packet folder and removed after; clearing an old packet removes only packet files.
Nothing is uploaded or served: the gate session sends the files into the director's own chat (docs/desk.md).
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

from ..formats import stamped
from ..gates import GATES, GateRefused, gate_spec, now_text
from ..gates.machine import ASKED
from ..project import FilmFolder, ProjectError, load_standing, read_film
from ..project.standing import write_atomic
from .builders import BUILDERS, NOUNS, GateContext
from .encode import cap_bytes
from .reply import DeskError
from .sink import PacketFile, Sink, inside

DESK = "desk"
MANIFEST = "manifest.json"
CARD = "card.md"
DEFAULT_MAX_MB = 40.0
WORK_PREFIX = ".work-"
PACKET_FILE = re.compile(r"^\d{2,3}-[\w.-]+\.(?:jpg|png|md|m4a|mp4)$")   # the names Sink gives


@dataclass(frozen=True)
class Packet:
    """A built packet: its folder, its files in send order, its card and any notes on what it could not carry."""

    gate: str
    folder: Path
    files: tuple[PacketFile, ...]
    card: str
    notes: tuple[str, ...] = ()


def _context(root: Path, gate: str) -> tuple[GateContext, str]:
    try:
        spec = gate_spec(gate)
        record = load_standing(FilmFolder(root)).gates.record(gate)
        data = read_film(FilmFolder(root))
    except (GateRefused, ProjectError) as problem:
        raise DeskError(str(problem)) from None
    if record.state != ASKED:
        raise DeskError(f"gate {spec.number} ({spec.title}) has not been asked (it is {record.state}); run "
                        f"`atomic-flix gate FILM ask {gate}` first, so the packet shows what was asked")
    for item in record.shown:
        inside(root, item, f"{item!r}, shown at gate {spec.number},")
    title = str(data.get("name") or root.name)
    return GateContext(root=root, data=data, shown=tuple(record.shown), title=title), record.question


def _groups(files: tuple[PacketFile, ...]) -> str:
    spans = []
    for group, members in groupby(files, key=lambda item: item.group):
        orders = [item.order for item in members]
        span = str(orders[0]) if len(orders) == 1 else f"{orders[0]} to {orders[-1]}"
        spans.append(f"{span}: {group}")
    return "; ".join(spans)


def card_text(gate: str, question: str, files: tuple[PacketFile, ...], facts: list[str]) -> str:
    """The card: the gate, its one question, what each file is, and exactly how to reply. It holds exactly one
    question mark, the question's: a fact is a statement, so any question mark in one is dropped."""
    spec = gate_spec(gate)
    lines = [f"# Gate {spec.number} of {len(GATES)}: {spec.title}", "", question, ""]
    lines.append(f"Files, in order: {_groups(files)}." if files else "No files: the facts are on this card.")
    lines += [fact.replace("?", "") for fact in facts]
    lines += ["", f"Reply in one message: \"yes\" or \"ok\" passes, never with a question mark; anything else sends "
                  f"it back (name each {NOUNS[gate]} by number: \"fix 2, 3 and 5: hand; 7: too dark\"); "
                  "\"question: ...\" asks without answering."]
    card = "\n".join(lines) + "\n"
    if card.count("?") != 1:
        raise DeskError(f"the card for gate {spec.number} must hold one question mark, the question's: {question!r}")
    return card


def _clear(folder: Path) -> None:
    """Remove the packet that was here before: only the packet files its manifest names (by the names Sink gives),
    its card and manifest; anything else in the folder is left alone."""
    manifest = folder / MANIFEST
    if manifest.is_file():
        try:
            names = [str(item["file"]) for item in json.loads(manifest.read_text(encoding="utf-8"))["files"]]
        except (OSError, ValueError, KeyError, TypeError) as problem:
            raise DeskError(f"{manifest} cannot be read ({problem}); remove the old packet by hand") from None
        for name in names:
            path = folder / name
            if PACKET_FILE.match(name) and path.parent == folder and path.is_file() and not path.is_symlink():
                path.unlink()
    for name in (MANIFEST, CARD):
        (folder / name).unlink(missing_ok=True)


def _packet_folder(root: Path, gate: str, out: Path | str | None) -> Path:
    """Where the packet goes: desk/<gate>, or OUT, which must be a folder under the film's desk/ folder."""
    desk = inside(root, DESK, "the film's desk/ folder")
    folder = (root / (out if out is not None else Path(DESK) / gate)).resolve()
    if folder == desk or not folder.is_relative_to(desk):
        where = "is outside the film folder" if not folder.is_relative_to(root) else "is not under desk/"
        raise DeskError(f"--out {out} {where}: a packet goes in a folder under the film's desk/ folder (like "
                        f"desk/{gate}-phone) and writes nowhere else")
    return folder


def _write(root: Path, folder: Path, gate: str, question: str, sink: Sink, card: str, max_mb: float) -> None:
    spec = gate_spec(gate)
    manifest = {"film": root.name, "gate": gate, "number": spec.number, "question": question, "made_at": now_text(),
                "max_mb": max_mb, "folder": folder.relative_to(root.resolve()).as_posix(),
                "notes": list(sink.notes), "files": [item.to_dict() for item in sink.files]}
    write_atomic(folder / MANIFEST, json.dumps(stamped("packet", manifest), indent=1, ensure_ascii=False) + "\n")
    write_atomic(folder / CARD, card)


def build_packet(root: Path | str, gate: str, *, out: Path | str | None = None,
                 max_mb: float = DEFAULT_MAX_MB) -> Packet:
    """Write the packet for GATE (asked, not yet answered) into OUT, default FILM/desk/<gate>/; refuses a folder
    outside the film's desk/ folder, an input outside the film folder, and any file that cannot meet MAX_MB per
    file. A build that fails in any way leaves no packet behind."""
    root = Path(root).resolve()
    cap = cap_bytes(max_mb)
    ctx, question = _context(root, gate)
    folder = _packet_folder(root, gate, out)
    folder.mkdir(parents=True, exist_ok=True)
    _clear(folder)
    sink = Sink(folder, cap, Path(tempfile.mkdtemp(prefix=WORK_PREFIX, dir=folder)))
    try:
        facts = BUILDERS[gate](ctx, sink)
        files = tuple(sink.files)
        card = card_text(gate, question, files, facts)
        _write(root, folder, gate, question, sink, card, max_mb)
    except Exception:
        for item in sink.files:
            (folder / item.file).unlink(missing_ok=True)
        for name in (MANIFEST, CARD):
            (folder / name).unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(sink.work, ignore_errors=True)
    return Packet(gate, folder, files, card, tuple(sink.notes))
