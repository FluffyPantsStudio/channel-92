"""The `pulse` stage: beat grid, bar one and swells, written as `pulse.json` and `swells.json`.

Beats come from the drum stem when there is one, else the band stem, else
the mix. Kick and snare are read from the same stem as the beats; chords,
bass and texture from the band stem (else the mix); swells from the mix
(else the band, else the drums). A `downbeat_slot` from film.json overrides the
stage's own decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .swells import Swells, find_swells
from .grid import Grid, beat_grid
from .phase import BarMap, apply_heard_slot, find_bar_one
from .spectral import spectra_of
from ..formats import stamped


@dataclass(frozen=True)
class Pulse:
    """Everything `pulse` found for one song."""

    grid: Grid
    bar: BarMap
    swells: Swells

    def to_dict(self) -> dict:
        beats = self.grid.beats
        phase = self.bar.downbeat_slot
        ones = beats[phase::4] if phase is not None else None
        thirds = beats[(phase + 2) % 4::4] if phase is not None else None
        rounded = lambda xs: [round(float(t), 3) for t in xs] if xs is not None else None
        return {"bpm": round(self.grid.bpm, 2), "beats": rounded(beats), "downbeat_slot": phase,
                "ones": rounded(ones), "thirds": rounded(thirds), "cut_beats": rounded(self.bar.cut_beats(beats)),
                "ruling": self.bar.status, "question": self.bar.question, "grounds": self.bar.to_dict(),
                "tempo": {"times": rounded(self.grid.curve_times),
                          "bpm": [round(float(b), 2) for b in self.grid.tempo_bpm]}}

    def write(self, folder) -> Path:
        """Write `pulse.json` and `swells.json` (UTF-8) into `folder`; returns the folder."""
        out = Path(folder)
        out.mkdir(parents=True, exist_ok=True)
        (out / "pulse.json").write_text(json.dumps(stamped("pulse", self.to_dict()), indent=1), encoding="utf-8")
        (out / "swells.json").write_text(json.dumps(stamped("swells", self.swells.to_dict()), indent=1), encoding="utf-8")
        return out


def pulse(drums: np.ndarray | None, rate: int, *, band: np.ndarray | None = None, mix: np.ndarray | None = None,
          vocal: np.ndarray | None = None, vocal_rate: int | None = None, hint_bpm: float | None = None,
          downbeat_slot: int | None = None) -> Pulse:
    """Run the whole stage on stems given as sample arrays at `rate` Hz."""
    provenance = next((x for x in (drums, band, mix) if x is not None), None)
    if provenance is None:
        raise ValueError("pulse needs a drum, band or mix stem")
    rhythm = spectra_of(provenance, rate)
    grid = beat_grid(rhythm, hint_bpm)
    tonal_audio = band if band is not None else mix
    tonal = spectra_of(tonal_audio, rate) if tonal_audio is not None and tonal_audio is not provenance else rhythm
    loud = next(x for x in (mix, band, drums) if x is not None)
    swells = find_swells(loud, rate, grid.beats, vocal=vocal, vocal_rate=vocal_rate)
    bar = find_bar_one(grid.beats, rhythm, tonal, swells.swells)
    if downbeat_slot is not None:
        bar = apply_heard_slot(bar, downbeat_slot)
    return Pulse(grid, bar, swells)
