"""A plain-text report of the line table: one row per line, for a person to check."""

from __future__ import annotations

from .lines import Timing


def _seconds(value: float | None) -> str:
    return f"{value:8.2f}" if value is not None else "       -"


def timing_report(timing: Timing) -> str:
    """Each line's id, part, start, end, confidence, flags and why it sits where it does."""
    rows = [f"quiet line {timing.floor_db:.1f} dB (working {timing.sung_db:.1f}); "
            f"labels {'used' if timing.marked else 'not given'}",
            "id    part      start      end  conf  text  [flags]  why: ..."]
    for line in timing.lines:
        conf = f"{line.confidence:4.2f}" if line.confidence is not None else "   -"
        flags = f"  [{'; '.join(line.flags)}]" if line.flags else ""
        rows.append(f"{line.id:5s} {line.part:6s} {_seconds(line.start)} {_seconds(line.end)}  {conf}  "
                    f"{line.text}{flags}  why: {line.why}")
    uncertain = [ln.id for ln in timing.lines if any("uncertain" in f for f in ln.flags)]
    rows.append(f"unplaced: {', '.join(timing.unplaced) or 'none'}; uncertain: {', '.join(uncertain) or 'none'}")
    return "\n".join(rows) + "\n"
