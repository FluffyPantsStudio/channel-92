"""Seeded random streams, one per (scene seed, block instance, purpose).

A draw for one block instance never depends on how many other pieces a scene has, so adding a block does not
reshuffle the rest of the set.
"""

from __future__ import annotations

import hashlib
import random


def stream(seed: int, *labels: object) -> random.Random:
    text = "\x1f".join([str(seed), *map(str, labels)])
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))
