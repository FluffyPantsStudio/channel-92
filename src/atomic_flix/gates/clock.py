"""Timestamps as ISO 8601 text, read the same way everywhere in the kit."""

from __future__ import annotations

from datetime import datetime, timezone


def parse_time(text: object) -> datetime:
    """Read an ISO 8601 stamp; a trailing Z means UTC and a stamp with no offset is taken as UTC.

    Raises ValueError for anything that is not such a stamp.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"not a timestamp: {text!r}")
    cleaned = text.strip()
    if cleaned[-1] in "Zz":
        cleaned = cleaned[:-1] + "+00:00"
    moment = datetime.fromisoformat(cleaned)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def now_text() -> str:
    """The current moment in UTC, to the second."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
