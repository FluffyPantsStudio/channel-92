"""Checks over a placement: a phrase that cost too much or did not place, a rate far from 1x, a pause the render
inserted where the song goes on, and drift (the offset moving along the take, so one offset would not do)."""

from __future__ import annotations

MAX_COST = 0.2
RATE_TOLERANCE = 0.18
DRIFT_LIMIT_S = 0.08


def _flag(flag_id: str, message: str, phrase: int | None = None) -> dict:
    return {"id": flag_id, "level": "WARN", "phrase": phrase, "message": message}


def check_fit(fit: dict, *, max_cost: float = MAX_COST, rate_tolerance: float = RATE_TOLERANCE,
              drift_limit_s: float = DRIFT_LIMIT_S) -> list[dict]:
    """Flags for one placement (the dict `fit_by_sound` returns); an empty list means it holds."""
    flags = []
    for index, phrase in enumerate(fit.get("vocal_spans", [])):
        where = f"phrase {index + 1} ({phrase['from']:.2f} to {phrase['to']:.2f} s)"
        if not phrase.get("ties"):
            flags.append(_flag("unplaced", f"{where} did not place (cost {phrase['cost']:.2f})", index))
        if phrase["cost"] > max_cost:
            flags.append(_flag("cost", f"{where} costs {phrase['cost']:.3f}, over {max_cost}", index))
        rate = phrase.get("rate")
        if rate is not None and abs(rate - 1.0) > rate_tolerance:
            flags.append(_flag("rate", f"{where} runs at {rate:.2f}x, more than {rate_tolerance:.0%} off", index))
    for pause in fit.get("added_rests", []):
        flags.append(_flag("pause", f"the render pauses {pause['seconds']:.2f} s at song {pause['at']:.2f} s "
                                    "where the song goes on"))
    offsets = [rendered - song for song, rendered in fit.get("map", [])]
    if offsets:
        spread = max(offsets) - min(offsets)
        slice_start = fit.get("slice_start", 0.0)
        low, high = min(offsets) + slice_start, max(offsets) + slice_start
        if spread > drift_limit_s:
            flags.append(_flag("drift", f"the offset moves {spread:.2f} s along the take ({low:+.2f} to "
                                        f"{high:+.2f} s); place it by the map, not one offset"))
    return flags
