"""The lyric as sung, read from `lyric.txt`.

Format: one sung line per text line, repeats written out in full.
`[Section]` lines name the part of the song that follows. A line wholly in
parentheses is sung by the choir; parentheses inside a lead line hold backing
words, which stay in the line's text but are not counted as the lead's words.
Blank lines and lines starting with `#` are ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_VERSE_PART = re.compile(r"^\[(.+)\]$")
_BACKING = re.compile(r"\([^)]*\)")
_TOKEN = re.compile(r"[a-z0-9']+")
_VOWEL_RUN = re.compile(r"[aeiouy]+")
_VOCALISE = re.compile(r"^[aeiouyhmnl]+$")

_DIGITS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_TEENS = ("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
          "eighteen", "nineteen")
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")


@dataclass(frozen=True)
class LyricLine:
    """One sung line: `words` are the normalised lead words used for matching."""

    id: str
    part: str
    verse_part: str
    text: str
    words: tuple[str, ...]
    wordless: bool

    @property
    def syllables(self) -> int:
        return max(1, sum(syllables(w) for w in self.words))


def _number_words(digits: str) -> list[str]:
    value = int(digits)
    if value < 10:
        return [_DIGITS[value]]
    if value < 20:
        return [_TEENS[value - 10]]
    if value < 100:
        tens, ones = divmod(value, 10)
        return [_TENS[tens]] + ([_DIGITS[ones]] if ones else [])
    return [_DIGITS[int(d)] for d in digits]


def normalise_words(text: str) -> tuple[str, ...]:
    """Lower case, no punctuation, hyphenated words split, digits spelled out."""
    cleaned = text.lower().replace("’", "'").replace("-", " ")
    out: list[str] = []
    for token in _TOKEN.findall(cleaned):
        token = token.replace("'", "")
        if not token:
            continue
        if token.isdigit():
            out.extend(_number_words(token))
        else:
            out.append(token)
    return tuple(out)


def syllables(word: str) -> int:
    """Rough English syllable count: vowel runs, less a silent final e."""
    runs = len(_VOWEL_RUN.findall(word))
    if word.endswith("e") and not word.endswith(("le", "ee", "ye")) and runs > 1:
        runs -= 1
    return max(1, runs)


def is_wordless(text: str) -> bool:
    """True for a vocalise such as "aa-h-aaaah" or "ooh la la": no real words."""
    tokens = normalise_words(text)
    return bool(tokens) and all(_VOCALISE.match(t) for t in tokens) and any(
        len(t) > 2 or t in ("la", "na", "mm", "hm", "ah", "oo") for t in tokens)


def parse_lyric(text: str) -> list[LyricLine]:
    """Read lyric text into numbered lines `v01`, `v02`, ... in sung order."""
    lines: list[LyricLine] = []
    verse_part = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        heading = _VERSE_PART.match(line)
        if heading:
            verse_part = heading.group(1).strip()
            continue
        whole_choir = line.startswith("(") and line.endswith(")") and _BACKING.sub("", line).strip() == ""
        if whole_choir:
            part, words_from = "choir", line[1:-1]
        else:
            part, words_from = "lead", _BACKING.sub(" ", line)
        lines.append(LyricLine(
            id=f"v{len(lines) + 1:02d}", part=part, verse_part=verse_part, text=line,
            words=normalise_words(words_from), wordless=is_wordless(words_from)))
    return lines
