"""The grade, the last step on the picture: every shot toward the film's own black, white and colour strength, then one
look over the whole film. It prints and saves the spread across shots before and after. No grain, ever.

Order on a film: cut, then grade, then the flash check and the review boards on the graded film.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .apply import write_graded
from .correct import (DEFAULT_LOOK, NEUTRAL_LOOK, COLOUR_GAIN, MAX_LEVEL_MOVE, MIN_RANGE, PULL, Correction, Look,
                      luma_table, plan_corrections)
from .measure import Levels, ShotSpan, measure_shots, spread
from ..formats import stamped


@dataclass
class GradeResult:
    corrections: list[Correction]
    before: list[Levels]
    after: list[Levels] = field(default_factory=list)
    spread_before: dict = field(default_factory=dict)
    spread_after: dict = field(default_factory=dict)
    out: Path | None = None
    account: Path | None = None

    def to_dict(self, film: Path, look: Look) -> dict:
        after = {item.key: item for item in self.after}
        return {"film": Path(film).name, "pull": PULL, "max_level_move": MAX_LEVEL_MOVE,
                "colour_gain": list(COLOUR_GAIN), "flat_below": MIN_RANGE, "look": look.to_dict(), "grain": None,
                "spread_before": self.spread_before, "spread_after": self.spread_after,
                "shots": [{**c.to_dict(), "after": after[c.key].to_dict() if c.key in after else None}
                          for c in self.corrections]}

    def text(self) -> str:
        lines = [f"{'shot':<8} {'black':>13} {'white':>13} {'colour':>13}"]
        for c in self.corrections:
            note = "  (flat: levels kept)" if c.flat else ""
            lines.append(f"{c.key:<8} {c.black:.3f} -> {c.new_black:.3f} {c.white:.3f} -> {c.new_white:.3f} "
                         f"{c.colour:.3f} x{c.gain:.2f}{note}")
        lines.append("spread across shots (standard deviation), before: " + _spread_text(self.spread_before))
        if self.spread_after:
            lines.append("spread across shots (standard deviation), after:  " + _spread_text(self.spread_after))
        return "\n".join(lines)


def _spread_text(values: dict) -> str:
    return ", ".join(f"{name} {value:.4f}" for name, value in values.items())


def measure_cut(cut: Path | str, shots: Sequence[ShotSpan], fps: float) -> GradeResult:
    """Measure only: what the grade would do, written nowhere."""
    before = measure_shots(cut, shots, fps)
    return GradeResult(corrections=plan_corrections(before), before=before, spread_before=spread(before))


def grade_cut(cut: Path | str, out: Path | str, shots: Sequence[ShotSpan], fps: float, *, look: Look = DEFAULT_LOOK,
              crf: int = 16, x264_speed: str = "slow") -> GradeResult:
    """Grade `cut` into `out` and write `out` with `.tone.json` beside it (the measures and the spread)."""
    result = measure_cut(cut, shots, fps)
    out = write_graded(cut, out, shots, result.corrections, look, crf=crf, x264_speed=x264_speed)
    result.after = measure_shots(out, shots, fps)
    result.spread_after = spread(result.after)
    result.out = out
    result.account = out.with_suffix(".tone.json")
    result.account.write_text(json.dumps(stamped("tone", result.to_dict(cut, look)), indent=1) + "\n", encoding="utf-8")
    return result


def shots_from_edit(edit) -> list[ShotSpan]:
    """The cut's shots, in the cut's frames, from the edit it was rendered from."""
    return [ShotSpan(shot.key, shot.frame_in, shot.end_frame) for shot in edit.shots()]


__all__ = ["DEFAULT_LOOK", "NEUTRAL_LOOK", "Correction", "GradeResult", "Levels", "Look", "ShotSpan", "grade_cut",
           "luma_table", "measure_cut", "measure_shots", "plan_corrections", "shots_from_edit", "spread"]
