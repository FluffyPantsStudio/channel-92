"""Reading prompts: quoted sung words are stripped before testing, steps are parsed from 'a-bs:' rows."""

from __future__ import annotations

import re
from typing import Iterator

from ..plan.vocab import find, pattern, terms

QUOTED = re.compile(r'"[^"\n]*"|\u201c[^\u201d\n]*\u201d')
STEP_ROW = re.compile(r"^\s*(\d+)-(\d+)s:\s*(.*)$", re.MULTILINE)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n+")


def strip_quoted(text: str) -> str:
    """The prompt with every quoted span (sung words) emptied, so lyrics never trip a rule."""
    return QUOTED.sub('""', text or "")


def quoted(text: str) -> list[str]:
    return [match.group(0)[1:-1] for match in QUOTED.finditer(text or "")]


def step_rows(text: str) -> list[tuple[int, int, str]]:
    return [(int(a), int(b), body) for a, b, body in STEP_ROW.findall(text or "")]


def sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT.split(text or "") if part.strip()]


def found(name: str, text: str, rules_dir=None) -> list[str]:
    return find(name, text, rules_dir)


def near_after(first: str, second: str, text: str, reach: int = 25, rules_dir=None) -> Iterator[re.Match]:
    """Matches where a term of list `first` is followed within `reach` characters, in one clause, by `second`."""
    one = pattern(terms(first, rules_dir)).pattern
    two = "|".join(re.escape(term) for term in terms(second, rules_dir))
    joined = re.compile(rf"{one}[^.;\n]{{0,{reach}}}?\b(?:{two})\w*", re.IGNORECASE)
    return joined.finditer(text or "")
