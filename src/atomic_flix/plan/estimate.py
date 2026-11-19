"""GPU hours a batch will take, from rates measured on our own renders, printed before anything is queued."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .vocab import DATA

DEFAULT_TAKES = 4


@dataclass(frozen=True)
class Row:
    key: str
    kind: str
    takes: int
    seconds: int
    rate_name: str
    rate: float
    busy_s: float


@dataclass(frozen=True)
class Batch:
    rows: Mapping[str, Row]
    cards: int
    size: tuple[int, int]

    @property
    def takes(self) -> int:
        return sum(row.takes for row in self.rows.values())

    @property
    def busy_s(self) -> float:
        return sum(row.busy_s for row in self.rows.values())

    @property
    def gpu_hours(self) -> float:
        return self.busy_s / 3600

    @property
    def wall_hours(self) -> float:
        return self.gpu_hours / max(1, self.cards)


def load_rates(path: Path | None = None) -> dict:
    data = json.loads(Path(path or DATA / "baseline-rates.json").read_text(encoding="utf-8"))
    return {**data["rates"], "_size": tuple(data.get("size", (1280, 704)))}


def rate_name(task: Mapping) -> str:
    pin = task.get("pin") or "none"
    if task.get("type") == "vocal":
        return {"full": "sung_pinned", "soft": "sung_soft_pin"}.get(pin, "sung_unpinned")
    return "plate_pinned" if pin == "full" else "plate_unpinned"


def estimate_batch(tasks: Mapping[str, Mapping], takes: Mapping[str, int] | int | None = None,
                   rates: Mapping | None = None, cards: int = 1) -> Batch:
    """Per shot: takes x seconds x the measured rate for its kind of render."""
    rates = rates or load_rates()
    rows = {}
    for key, task in tasks.items():
        count = takes if isinstance(takes, int) else (takes or {}).get(key, task.get("takes") or DEFAULT_TAKES)
        name = rate_name(task)
        rate = float(rates[name])
        seconds = int(task["seconds"])
        rows[key] = Row(key, task.get("type", "cutaway"), int(count), seconds, name, rate, seconds * rate * int(count))
    return Batch(rows=rows, cards=cards, size=tuple(rates.get("_size", (1280, 704))))
