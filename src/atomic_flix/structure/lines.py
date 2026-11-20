"""The timed lead lines with the lyric's [Section] each belongs to, read from `analysis/voice-lines.json`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..timing import parse_lyric

UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class TimedLine:
    """One timed lead line: its lyric section `label`, which written block of the lyric it is in (a section sung
    three times is three blocks), and whether `time` was unsure where it goes."""

    id: str
    label: str
    block: int
    start: float
    end: float
    flagged: bool = False


def _blocks(lyric: str) -> dict[str, tuple[str, int]]:
    """Per lead line id: its [Section] name and block number (a new block wherever the section name changes)."""
    out, block, previous = {}, -1, None
    for line in parse_lyric(lyric):
        if line.verse_part != previous:
            block, previous = block + 1, line.verse_part
        if line.part == "lead":
            out[line.id] = (line.verse_part, block)
    return out


def _other_lyric(lyric: str, rows: list[Mapping[str, Any]]) -> list[str]:
    written = {line.id: line.text for line in parse_lyric(lyric)}
    return [row.get("id", "?") for row in rows if written.get(row.get("id")) != row.get("text")]


def timed_lines(lyric: str, voice_lines: Mapping[str, Any]) -> tuple[tuple[TimedLine, ...], tuple[str, ...]]:
    """The lead lines of `voice_lines` (the parsed voice-lines.json) that have a time, and plain notes on the rest."""
    rows = [row for row in voice_lines.get("lines") or [] if row.get("part", "lead") == "lead"]
    differ = _other_lyric(lyric, rows)
    if differ:
        return (), (f"analysis/voice-lines.json was timed on another lyric ({', '.join(differ[:5])} differ from "
                    "lyric.txt); its lines are not used: run `atomic-flix time` again",)
    blocks = _blocks(lyric)
    found, untimed, unsure = [], [], []
    for row in rows:
        if row.get("start") is None or row.get("end") is None:
            untimed.append(row["id"])
            continue
        flagged = any(UNCERTAIN in flag for flag in row.get("flags") or [])
        unsure += [row["id"]] if flagged else []
        label, block = blocks[row["id"]]
        found.append(TimedLine(row["id"], label, block, float(row["start"]), float(row["end"]), flagged))
    notes = []
    if untimed:
        notes.append(f"{len(untimed)} lead line(s) have no time from `time`: {', '.join(untimed)}")
    if unsure:
        notes.append(f"{len(unsure)} of {len(rows)} lead lines are flagged uncertain by `time` ({', '.join(unsure)}): "
                     "a section edge at one of them is only as sure as that line")
    return tuple(sorted(found, key=lambda x: x.start)), tuple(notes)
