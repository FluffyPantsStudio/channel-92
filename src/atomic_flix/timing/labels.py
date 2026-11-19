"""Word labels from a speech recogniser, and matching them to the lyric.

Labels are optional input made outside this package (for example by a
large speech model run on the voice stem). They are trusted for one thing
only: which lyric words were heard around which time. Their start times are
not used as line starts: recognisers often date a phrase's opening word
early when silence precedes it, sometimes by about two seconds.

File format (`analysis/word-labels.json`):
`{"model": "...", "words": [{"text": "float", "from": 188.1, "to": 188.4, "conf": 0.91}]}`
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from .lyric import LyricLine, normalise_words
from ..formats import tag

EXACT_SCORE = 2
PREFIX_SCORE = 1
PREFIX_LETTERS = 4
MAX_SPREAD_S = 12.0


@dataclass(frozen=True)
class Label:
    """One recognised word and the stretch of time the recogniser gave it."""

    text: str
    start: float
    end: float
    conf: float = 1.0


def load_labels(path) -> list[Label]:
    """Read a word-labels file in the format above (UTF-8)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Label(str(w["text"]), float(w["from"]), float(w["to"]), float(w.get("conf", 1.0)))
            for w in data["words"]]


def save_labels(labels: Sequence[Label], path, model: str = "") -> Path:
    """Write labels in the format above (UTF-8)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    words = [{"text": lb.text, "from": lb.start, "to": lb.end, "conf": lb.conf} for lb in labels]
    out.write_text(json.dumps({"format": tag("word-labels"), "model": model, "words": words}, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _prefix(word: str) -> str:
    return word[:PREFIX_LETTERS] if len(word) >= PREFIX_LETTERS else "\0" + word


def _align(lyric_tokens: list[str], label_tokens: list[str]) -> list[tuple[int, int]]:
    """Best in-order pairing of lyric tokens with label tokens (skips allowed on both sides).

    Exact matches score 2 and matches on the first four letters score 1; the
    pairing with the highest total wins. Returns (lyric_pos, label_pos) pairs.
    """
    n, m = len(lyric_tokens), len(label_tokens)
    if n == 0 or m == 0:
        return []
    heard = np.array(label_tokens, dtype=object)
    heard_prefix = np.array([_prefix(t) for t in label_tokens], dtype=object)
    table = np.zeros((n + 1, m + 1), dtype=np.int32)
    for i, word in enumerate(lyric_tokens):
        gain = np.where(heard == word, EXACT_SCORE, np.where(heard_prefix == _prefix(word), PREFIX_SCORE, 0))
        diagonal = np.where(gain > 0, table[i, :-1] + gain, 0)
        candidate = np.maximum(table[i, 1:], diagonal)
        table[i + 1, 1:] = np.maximum.accumulate(candidate)
    pairs = []
    i, j = n, m
    while i > 0 and j > 0:
        if table[i, j] == table[i - 1, j]:
            i -= 1
        elif table[i, j] == table[i, j - 1]:
            j -= 1
        else:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
    pairs.reverse()
    return pairs


def _compact(indices: list[int], labels: Sequence[Label]) -> list[int]:
    """Drop matches far in time from the rest of their line's matches."""
    if len(indices) < 3:
        return indices
    centre = float(np.median([labels[i].end for i in indices]))
    return [i for i in indices if abs(labels[i].end - centre) <= MAX_SPREAD_S]


def match_labels(lines: Sequence[LyricLine], labels: Sequence[Label]) -> dict[str, list[int]]:
    """For each line id, the indices of the labels matched to its words, in order.

    Only lead lines with real words take part: the recogniser hears the lead
    stem, and a vocalise has nothing to match.
    """
    lyric_tokens: list[str] = []
    owner: list[str] = []
    for line in lines:
        if line.part != "lead" or line.wordless:
            continue
        lyric_tokens.extend(line.words)
        owner.extend([line.id] * len(line.words))
    label_tokens: list[str] = []
    provenance: list[int] = []
    for index, label in enumerate(labels):
        for token in normalise_words(label.text):
            label_tokens.append(token)
            provenance.append(index)
    found: dict[str, list[int]] = {line.id: [] for line in lines}
    for lyric_pos, label_pos in _align(lyric_tokens, label_tokens):
        bucket = found[owner[lyric_pos]]
        index = provenance[label_pos]
        if index not in bucket:
            bucket.append(index)
    return {key: _compact(value, labels) for key, value in found.items()}
