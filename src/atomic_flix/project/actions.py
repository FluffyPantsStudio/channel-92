"""Moving a film through its gates: every step reads standing.json, changes it through the gate machine, writes
the person's words into notes.md, then saves. A refused step writes nothing.

A yes at gate 5 (spend) also copies the batch it approved from plan/budget.json (takes, frame size, GPU seconds)
into standing.json; takes are drawn on it as they are planned (`draw_batch`), so one yes covers one batch. A plan
that differs, or takes past its count, need the gate reopened and a new answer.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

from ..gates import GATES, PERSON_DIRECT, RELAYED, Answer, GateRefused, gate_spec, now_text
from .layout import FilmFolder
from .standing import BatchApproval, ProjectError, Standing, fingerprint, load_standing, save_standing

SONG_GATE = "song"
SPEND_GATE = "spend"
BUDGET_FILE = "plan/budget.json"
ARRIVALS = {PERSON_DIRECT: "typed by the person", RELAYED: "relayed, the person's words quoted"}
UNSAID_ARRIVAL = "how it arrived not recorded"


def _folder(film: FilmFolder | Path | str) -> FilmFolder:
    return film if isinstance(film, FilmFolder) else FilmFolder(Path(film))


def read_film(folder: FilmFolder) -> dict[str, Any]:
    """film.json as a dict, read as UTF-8."""
    try:
        data = json.loads(folder.film.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProjectError(f"{folder.film} is missing") from None
    except json.JSONDecodeError as problem:
        raise ProjectError(f"{folder.film} is not JSON: {problem}") from None
    if not isinstance(data, dict):
        raise ProjectError(f"{folder.film} must hold one JSON object")
    return data


def quote(words: str) -> str:
    """WORDS as a Markdown quote, every line kept exactly, so the notes hold them word for word."""
    return "".join(f"> {line}\n" if line else ">\n" for line in words.split("\n"))


def arrival(answer: Answer) -> str:
    """How an answer reached the kit, in plain words (bookkeeping, not proof: docs/gates.md)."""
    return ARRIVALS.get(answer.provenance, UNSAID_ARRIVAL)


def _append_notes(folder: FilmFolder, block: str) -> None:
    with folder.notes.open("a", encoding="utf-8", newline="\n") as notes:
        notes.write(block)


def _answer_block(standing: Standing, gate: str, answer: Answer) -> str:
    spec = gate_spec(gate)
    record = standing.gates.record(gate)
    scope = "a standing rule" if answer.scope == "standing" else "this film only"
    outcome = "The gate passes." if answer.approves else "The gate stays open."
    lines = [f"\n## {answer.at}: gate {spec.number}, {spec.title}\n\n",
             f"Shown: {', '.join(record.shown)}\n",
             f"Asked: \"{record.question}\"\n"]
    if record.open_errors:
        lines.append(f"Still open after the cold review rounds: {'; '.join(record.open_errors)}\n")
    lines.append(f"\n{answer.by} (the person; {arrival(answer)}), {answer.at}, for {scope}:\n\n")
    lines.append(quote(answer.words))
    lines.append(f"\n{outcome}\n")
    return "".join(lines)


def ask_gate(film: FilmFolder | Path, gate: str, shown: Sequence[str], *, at: str | None = None,
             question: str | None = None) -> Standing:
    """Record that SHOWN was put to the person at GATE with one question."""
    folder = _folder(film)
    standing = load_standing(folder)
    updated = replace(standing, gates=standing.gates.ask(gate, shown, at=at or now_text(), question=question))
    save_standing(folder, updated)
    return updated


def _approved_batch(folder: FilmFolder, answer: Answer) -> BatchApproval | None:
    """The batch plan/budget.json describes, as approved by ANSWER; None when there is no budget file."""
    budget = folder.root / BUDGET_FILE
    if not budget.is_file():
        return None
    try:
        data = json.loads(budget.read_text(encoding="utf-8"))
        width, height = data["size"]
        return BatchApproval(takes=int(data["takes"]), size=(int(width), int(height)),
                             busy_s=float(data["busy_s"]), at=answer.at)
    except (OSError, ValueError, KeyError, TypeError) as problem:
        raise ProjectError(f"{BUDGET_FILE} cannot be read for gate 5: {problem}") from None


def answer_gate(film: FilmFolder | Path, gate: str, answer: Answer) -> Standing:
    """Record the person's ANSWER at GATE: in notes.md word for word, then in standing.json.

    A yes at the song gate also fingerprints the mix it approved, so a changed file is caught later; a yes at the
    spend gate copies the batch it approved from plan/budget.json (any answer there drops the batch before).
    """
    folder = _folder(film)
    standing = load_standing(folder)
    book = standing.gates.answer(gate, answer)
    song, batch = standing.song, standing.batch
    if gate == SONG_GATE and answer.approves:
        relative = str(read_film(folder).get("stems", {}).get("mix") or "")
        mix = folder.root / relative
        if not relative or not mix.is_file():
            raise ProjectError(f"the song gate needs the mix the person heard; {relative or 'stems.mix'} is missing")
        song = fingerprint(mix, relative)
    if gate == SPEND_GATE:
        batch = _approved_batch(folder, answer) if answer.approves else None
    _append_notes(folder, _answer_block(standing, gate, answer))
    updated = replace(standing, gates=book, song=song, batch=batch)
    save_standing(folder, updated)
    return updated


def reopen_gate(film: FilmFolder | Path, gate: str, reason: str, *, at: str | None = None) -> Standing:
    """Open a passed gate again; the reason goes into the notes. Reopening gate 5 drops its batch."""
    folder = _folder(film)
    standing = load_standing(folder)
    stamp = at or now_text()
    book = standing.gates.reopen(gate, reason, at=stamp)
    spec = gate_spec(gate)
    _append_notes(folder, f"\n## {stamp}: gate {spec.number}, {spec.title}, reopened\n\n{reason}\n")
    updated = replace(standing, gates=book, batch=None if gate == SPEND_GATE else standing.batch)
    save_standing(folder, updated)
    return updated


def draw_batch(film: FilmFolder | Path, count: int, *, plan: tuple[int, tuple[int, int], float] | None = None,
               check_only: bool = False) -> str:
    """Draw COUNT takes on gate 5's approved batch and return the approval's stamp (its answer time), which each
    job planned under it carries. PLAN, when given, is (takes, (width, height), GPU seconds) of the plan as it
    stands now; it must be the approved one. Refuses (ProjectError) past the batch's count or on a different plan;
    CHECK_ONLY checks without drawing."""
    folder = _folder(film)
    standing = load_standing(folder)
    try:
        standing.gates.require(SPEND_GATE)
    except GateRefused as problem:
        raise ProjectError(str(problem)) from None
    batch = standing.batch
    if batch is None:
        raise ProjectError("gate 5's yes has no batch on record (run `atomic-flix budget`, reopen gate 5 and ask "
                           "again, so the answer names the takes, size and hours it approves)")
    if plan is not None:
        takes, size, busy_s = plan
        approved = (batch.takes, tuple(batch.size), round(batch.busy_s, 1))
        if (int(takes), tuple(size), round(float(busy_s), 1)) != approved:
            raise ProjectError(f"the plan ({takes} takes at {size[0]}x{size[1]}, {busy_s / 3600:.2f} GPU h) differs "
                               f"from the one approved at gate 5 ({batch.takes} takes at {batch.size[0]}x"
                               f"{batch.size[1]}, {batch.busy_s / 3600:.2f} GPU h); it needs a new answer")
    if count < 0 or batch.drawn + count > batch.takes:
        raise ProjectError(f"gate 5's yes covers {batch.takes} takes and {batch.drawn} are planned already, so "
                           f"{count} more need a new answer (reopen gate 5 and ask again)")
    if not check_only:
        save_standing(folder, replace(standing, batch=replace(batch, drawn=batch.drawn + count)))
    return batch.at


def review_cut(film: FilmFolder | Path, cut: str, reviewer: str, errors: Sequence[str], *, at: str | None = None,
               cold: bool = True) -> Standing:
    """Add one cold review round of CUT with the clear errors the reviewer named (none: clean)."""
    folder = _folder(film)
    standing = load_standing(folder)
    book = standing.gates.reviewed(cut, reviewer, errors, at=at or now_text(), cold=cold)
    updated = replace(standing, gates=book)
    save_standing(folder, updated)
    return updated


def set_record(film: FilmFolder | Path, **values: Any) -> Standing:
    """Write numbers into the record (see RECORD_FIELDS); unknown names and wrong types are refused."""
    folder = _folder(film)
    updated = load_standing(folder).with_record(**values)
    save_standing(folder, updated)
    return updated


def require_gate(film: FilmFolder | Path, gate: str) -> None:
    """Refuse (GateRefused) unless GATE and all gates before it hold the person's yes."""
    load_standing(_folder(film)).gates.require(gate)


def where_it_stands(film: FilmFolder | Path) -> str:
    """A few plain lines: the next gate, what it shows and asks, the gates passed (and how each answer arrived),
    gate 5's batch, the review loop."""
    standing = load_standing(_folder(film))
    book = standing.gates
    upcoming = book.next_gate()
    lines = []
    if upcoming is None:
        lines.append(f"{standing.film}: all {len(GATES)} gates have passed.")
    else:
        record = book.record(upcoming.id)
        lines.append(f"{standing.film}: next is gate {upcoming.number} of {len(GATES)}, {upcoming.title} "
                     f"({record.state}).")
        lines.append(f"Shows: {', '.join(record.shown) if record.shown else upcoming.shows}")
        lines.append(f"Asks: \"{record.question or upcoming.question}\"")
    passed = [f"{r.spec.number} {r.spec.title} ({r.latest.at[:10]}, {arrival(r.latest)})"
              for r in book.records if r.state == "passed"]
    lines.append("Passed: " + ("; ".join(passed) if passed else "none yet"))
    if standing.batch is not None:
        batch = standing.batch
        lines.append(f"Gate 5 covers {batch.takes} takes at {batch.size[0]}x{batch.size[1]}, "
                     f"{batch.busy_s / 3600:.2f} GPU h; {batch.drawn} planned so far.")
    loop = book.review
    if loop.rounds:
        state = "clean" if loop.is_clean else (f"stalled: {loop.stalled}" if loop.stalled else "open")
        lines.append(f"Review: {len(loop.rounds)} review rounds on the way to the person, {len(loop.open_errors)} "
                     f"open errors, {state}.")
    return "\n".join(lines)


__all__ = ["answer_gate", "arrival", "ask_gate", "draw_batch", "quote", "read_film", "reopen_gate", "require_gate",
           "review_cut", "set_record", "where_it_stands"]
