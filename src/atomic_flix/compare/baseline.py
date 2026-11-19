"""The first film's numbers, read from its baseline file (the shape of flix/baseline.json).

Each value is looked up by a path through the JSON; text such as "about 4 calendar days" yields its first number,
and anything without a number ("unknown") is None. Kinds of GPU job are found by a word in their key, so the
file's own key names are not built into the kit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
HOUR = 3600.0


@dataclass(frozen=True)
class Known:
    """One number of the first film and where it came from; value None means not recorded."""

    value: float | None
    provenance: str


def number(node: Any) -> float | None:
    """A number from a value, a {"value": ...} item, or the first number written in a text."""
    if isinstance(node, dict):
        node = node.get("value")
    if isinstance(node, bool):
        return None
    if isinstance(node, (int, float)):
        return float(node)
    if isinstance(node, str):
        found = NUMBER.search(node)
        return float(found.group(0).replace(",", "")) if found else None
    return None


def dig(data: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def _provenance(node: Any, fallback: str) -> str:
    return str(node["provenance"]) if isinstance(node, dict) and node.get("provenance") else fallback


def _at(*keys: str, field: str | None = None, scale: float = 1.0) -> Callable[[dict[str, Any]], Known]:
    def read(data: dict[str, Any]) -> Known:
        node = dig(data, *keys)
        value = number(node.get(field) if field and isinstance(node, dict) else node)
        return Known(None if value is None else value * scale, _provenance(node, " / ".join(keys)))
    return read


def _job_hours(word: str) -> Callable[[dict[str, Any]], Known]:
    def read(data: dict[str, Any]) -> Known:
        kinds = dig(data, "gpu", "by_kind_of_job_seconds")
        where = "gpu / by_kind_of_job_seconds"
        if not isinstance(kinds, dict):
            return Known(None, where)
        seconds = [number(item.get("seconds")) for key, item in kinds.items()
                   if word in key and isinstance(item, dict)]
        seconds = [s for s in seconds if s is not None]
        return Known(sum(seconds) / HOUR if seconds else None, _provenance(kinds, where))
    return read


def _total_hours(data: dict[str, Any]) -> Known:
    total = dig(data, "gpu", "by_kind_of_job_seconds", "total")
    where = _provenance(dig(data, "gpu", "by_kind_of_job_seconds"), "gpu / by_kind_of_job_seconds / total")
    if isinstance(total, dict) and number(total.get("hours")) is not None:
        return Known(number(total.get("hours")), where)
    if isinstance(total, dict) and number(total.get("seconds")) is not None:
        return Known(number(total.get("seconds")) / HOUR, where)
    return Known(None, where)


def _renders_per_second(data: dict[str, Any]) -> Known:
    rendered = number(dig(data, "takes", "rendered_total"))
    finished = number(dig(data, "rendered_to_finished", "finished_film_seconds"))
    value = rendered / finished if rendered is not None and finished else None
    return Known(value, "takes / rendered_total over rendered_to_finished / finished_film_seconds")


def _first_key(branch: str, word: str) -> Callable[[dict[str, Any]], Known]:
    def read(data: dict[str, Any]) -> Known:
        items = dig(data, branch)
        if not isinstance(items, dict):
            return Known(None, branch)
        for key, item in items.items():
            if word in key:
                return Known(number(item), _provenance(item, f"{branch} / {key}"))
        return Known(None, branch)
    return read


READERS: Mapping[str, Callable[[dict[str, Any]], Known]] = MappingProxyType({
    "gpu_hours_total": _total_hours,
    "gpu_hours_vocal": _job_hours("sung"),
    "gpu_hours_cutaway": _job_hours("plate"),
    "gpu_hours_still": _job_hours("still"),
    "gpu_hours_test": _job_hours("test"),
    "renders_per_finished_second": _renders_per_second,
    "vocal_renders_per_shot": _at("takes", "sung", field="per_shot_mean"),
    "cutaway_renders_per_shot": _at("takes", "plate", field="per_shot_mean"),
    "reshoot_passes": _first_key("sung_reshoots", "full_passes"),
    "builds": _at("builds_and_reviews", "numbered_builds"),
    "days_to_acceptance": _at("calendar", "start_to_acceptance"),
    "rendered_to_finished": _at("rendered_to_finished", "ratio"),
    "driver_calls": _at("model_calls", "calls"),
    "cost_usd": _at("model_calls", "cost_usd_list_price"),
    "driver_median_tokens": _at("model_calls", "driver_median_tokens_per_call"),
})


def load_baseline(path: Path) -> Mapping[str, Known]:
    """Every metric of the first film from the baseline file at PATH."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must hold one JSON object")
    return MappingProxyType({key: read(data) for key, read in READERS.items()})


def baseline_name(path: Path) -> str:
    """The film's name as the baseline file gives it, without the folder in brackets."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    name = str(data.get("film") or "the first film") if isinstance(data, dict) else "the first film"
    return name.split(" (")[0]
