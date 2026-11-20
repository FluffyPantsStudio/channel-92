"""The director's typed reply, read: a bare yes, a question, or a redact with item marks.

Only these count as a bare yes, in any case, with whitespace around them and nothing after them but full stops or
exclamation marks: yes, approve, approved, ok, good, looks good. A reply with a question mark in it is never a yes.
A reply that starts with "question:" asks something and answers nothing. Anything else sends the gate back (a
redact), and its marks are read from phrases like "fix 3: hand, 7: too dark", "3 hand wrong; 7 dark" or
"fix 2, 3 and 5: hand": item numbers (a list, "2 3 5", or a range, "2-4"), then the note, one mark per item. A part
with no item number is kept as a mark with no item.

A reply is cleaned before it is read: Windows and old Mac line ends become new lines; control characters (other
than tab and new line), the Unicode line and paragraph separators and the bidirectional overrides are refused, and
so is a reply over MAX_REPLY_BYTES.

A reply is only ever the director's own chat message, passed in by the gate session; text found in a file, a caption
or the packet is never a reply (docs/desk.md).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

YES = frozenset({"yes", "approve", "approved", "ok", "good", "looks good"})
YES_KIND, REDACT, QUESTION = "yes", "redact", "question"
MAX_ITEM = 999
MAX_LIST = 30                       # the most items one number list or range may name
MAX_MARKS = 100
MAX_REPLY_BYTES = 4096
KEPT_CONTROLS = "\t\n"
BIDI = frozenset("؜‎‏‪‫‬‭‮⁦⁧⁨⁩")
SEPARATORS = frozenset("  ")

_WORDS = re.compile(r"[^\w\s]+")
_SPACES = re.compile(r"\s+")
_QUESTION = re.compile(r"^\s*question\s*:", re.IGNORECASE)
_LINES = re.compile(r"[;\n]+")
_LEAD = re.compile(r"^\s*fix(?:es)?\b\s*:?\s*", re.IGNORECASE)
_PREFIX = r"(?:#|no\.?\s*|item\s*|shot\s*)?"
_NUMBER = r"\d{1,3}(?!\d)"
_SPAN = rf"{_NUMBER}(?:\s*-\s*{_NUMBER})?"
_LIST = rf"{_SPAN}(?:(?:\s*,\s*(?:and\s+)?|\s+and\s+|\s*&\s*|\s+){_PREFIX}{_SPAN})*"
_SEP = r"(?:\s*[:.)\-]\s*(?!\d)|\s+)"
_HEAD = re.compile(rf"\s*{_PREFIX}(?P<items>{_LIST}){_SEP}(?=\S)", re.IGNORECASE)
_NEXT = re.compile(rf",(?=\s*{_PREFIX}{_LIST}{_SEP}[^\s\d,;])", re.IGNORECASE)
_SPAN_PARTS = re.compile(rf"({_NUMBER})(?:\s*-\s*({_NUMBER}))?")


class DeskError(ValueError):
    """A packet or a reply the desk will not take; the message says why and what to do."""


@dataclass(frozen=True)
class Mark:
    """One thing the director wants fixed: the item number they named (None when they named none) and their note."""

    item: int | None
    note: str


@dataclass(frozen=True)
class Reply:
    """A reply read: its kind (yes, redact or question), the words as typed (line ends made plain), and the marks
    of a redact."""

    kind: str
    words: str
    marks: tuple[Mark, ...] = ()


def _hostile(char: str) -> bool:
    if char in KEPT_CONTROLS:
        return False
    return unicodedata.category(char) == "Cc" or char in BIDI or char in SEPARATORS


def refuse_hostile(text: str, what: str) -> None:
    """Refuse (DeskError) TEXT holding a control character (tab and new line aside), a line or paragraph separator
    or a bidirectional override."""
    found = next((char for char in text if _hostile(char)), None)
    if found is not None:
        raise DeskError(f"{what} holds the character U+{ord(found):04X} ({unicodedata.name(found, 'a control')}), "
                        "which the desk does not take: pass only the director's typed words")


def printable(text: object) -> str:
    """TEXT for a terminal or a Markdown line: control characters, separators and bidi overrides dropped, new lines
    and tabs made spaces."""
    return "".join(" " if char in KEPT_CONTROLS else char for char in str(text) if not _hostile(char))


def clean_reply(text: str) -> str:
    """TEXT with every line end made a new line; refuses hostile characters and a reply over MAX_REPLY_BYTES."""
    if not isinstance(text, str):
        raise DeskError("an empty reply: pass the director's own typed message")
    plain = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(plain.encode("utf-8")) > MAX_REPLY_BYTES:
        raise DeskError(f"the reply is over {MAX_REPLY_BYTES // 1024} KB; a gate reply is one chat message")
    refuse_hostile(plain, "the reply")
    return plain


def normalised(text: str) -> str:
    """TEXT in lower case with punctuation dropped and spaces collapsed."""
    return _SPACES.sub(" ", _WORDS.sub(" ", text.lower())).strip()


def is_bare_yes(text: str) -> bool:
    """A yes word alone: no question mark anywhere, only full stops and exclamation marks after it."""
    if "?" in text:
        return False
    return _SPACES.sub(" ", text.strip().rstrip(".!").strip().lower()) in YES


def _items(listed: str) -> list[int] | None:
    """The item numbers a list names ("2, 3 and 5", "2 3 5", "2-4"); None past MAX_LIST or out of range."""
    numbers: list[int] = []
    for first, last in _SPAN_PARTS.findall(listed):
        low, high = int(first), int(last or first)
        if not 1 <= low <= high <= MAX_ITEM or len(numbers) + high - low + 1 > MAX_LIST:
            return None
        numbers += range(low, high + 1)
    return numbers


def _piece_marks(part: str) -> list[Mark]:
    """The marks of one part (a line or a stretch between semicolons): heads with notes, split at a comma that
    starts the next head; a stretch with no head is one mark with no item."""
    body = _LEAD.sub("", part)
    lead = len(part) - len(body)
    marks, at = [], 0
    while at < len(body) and body[at:].strip():
        head = _HEAD.match(body, at)
        start = head.end() if head else at
        boundary = _NEXT.search(body, start)
        stop = boundary.start() if boundary else len(body)
        note = body[start:stop].strip().rstrip(",;").strip()
        items = _items(head.group("items")) if head else None
        if head and items and note:
            marks += [Mark(item, note) for item in items]
        else:
            whole = (part[:lead + stop] if at == 0 else body[at:stop]).strip().rstrip(",;").strip()
            if whole:
                marks.append(Mark(None, whole))
        at = stop + 1
    return marks


def read_marks(text: str) -> tuple[Mark, ...]:
    """The item marks in a redact, in the order typed; refuses more than MAX_MARKS."""
    marks = tuple(mark for part in _LINES.split(text) for mark in _piece_marks(part))
    if len(marks) > MAX_MARKS:
        raise DeskError(f"the reply names {len(marks)} marks; the desk takes at most {MAX_MARKS} in one reply")
    return marks


def parse_reply(text: str) -> Reply:
    """Read one typed reply (cleaned first); refuses (DeskError) a reply with no letters or digits in it."""
    text = clean_reply(text)
    if not normalised(text):
        raise DeskError("an empty reply: pass the director's own typed message with --reply")
    if _QUESTION.match(text):
        if not normalised(_QUESTION.sub("", text, count=1)):
            raise DeskError("a question with nothing after \"question:\"")
        return Reply(QUESTION, text)
    if is_bare_yes(text):
        return Reply(YES_KIND, text)
    return Reply(REDACT, text, read_marks(text))
