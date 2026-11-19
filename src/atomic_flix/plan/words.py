"""Lyric text prepared for quoting inside a render prompt.

Video models halt the singer at every period. Where the voice stem carries straight through a period in mid-line,
it is swapped for a comma; the same swap happens at the end of a line whose successor begins under LEGATO seconds
later.
"""

from __future__ import annotations

import re
from typing import Mapping, Sequence

LEGATO = 0.25
_KEEP_CAPITAL = {"i", "i'm", "i'll", "i've", "i'd"}
_WORDLESS_TOKEN = re.compile(r"^[aeiouhmw]+$")


def is_wordless(text: str) -> bool:
    """A line of vowels and hums only ('aa-h', 'ooh', 'mm'), sung as one long note."""
    tokens = [t for t in re.split(r"[\s\-,.!?;:'\"()]+", (text or "").lower()) if t]
    return bool(tokens) and all(_WORDLESS_TOKEN.match(token) for token in tokens)


def _soften(text: str, names: Sequence[str]) -> str:
    """Every full stop between words becomes a comma; the next word loses its capital unless it is 'I' or a name."""
    keep = _KEEP_CAPITAL | {name.lower() for name in names}

    def swap(match: re.Match) -> str:
        word = match.group(1)
        if word.lower() in keep:
            return ", " + word
        return ", " + word[0].lower() + word[1:]

    return re.sub(r"\.\s+([A-Za-z][\w']*)", swap, text)


def _line_text(line, names: Sequence[str]) -> str:
    text = " ".join((line.text or "").split())
    paused = any(b - a >= LEGATO for a, b in (line.gaps or ()))
    return text if paused else _soften(text, names)


def sung_words(keys: Sequence[str], lines: Mapping, names: Sequence[str] = (),
               next_start: float | None = None) -> str:
    """The quoted words for one step: its lines in order, punctuated by how the stem actually breathes.

    `next_start` is when the next sung line after this step starts, if she sings on: a closing stop then becomes a
    comma too."""
    ordered = sorted((lines[key] for key in keys), key=lambda line: line.start)
    out = ""
    for index, line in enumerate(ordered):
        text = _line_text(line, names)
        if index + 1 < len(ordered):
            follows = ordered[index + 1].start - line.end < LEGATO
            if follows and text.endswith("."):
                text = text[:-1] + ","
            elif not re.search(r"[,.!?;:]$", text):
                text = text + ("," if follows else ".")
        if out and out.endswith(","):
            nxt = text.split(" ", 1)[0]
            if nxt.lower() not in _KEEP_CAPITAL and nxt.lower() not in {n.lower() for n in names} and nxt[:1].isupper():
                text = text[0].lower() + text[1:]
        out = f"{out} {text}".strip()
    if next_start is not None and out.endswith(".") and next_start - ordered[-1].end < LEGATO:
        out = out[:-1] + ","
    return out
