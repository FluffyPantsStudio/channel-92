"""Which beat is the bar's one.

A phase p says the one falls on every beat whose index mod 4 is p; counts one
to four follow. For each beat we measure kick strength, snare strength, chord
change (keys and voices, 130 Hz to 2 kHz), bass change (40 to 130 Hz) and any
accent snapped to it, each z-scored over the song. A phase scores

    kick(1) + kick(3) + chord(1) + accent(1) + snare(2) + snare(4) - snare(1) - snare(3)

where feature(n) is the feature's mean over the beats that phase calls count n.

Two kinds of mistake are told apart.

* One against two (phases an odd number apart): kicks against snares. This
  is the dangerous one, a cut a beat late. Its margin is `pair_margin`.
* One against three (phases two apart): kicks and snares repeat every two
  beats, so only chords, swells, the bass and the song's eight-bar phrases
  can separate them. When they cannot, the result says "one or three": cuts
  on either are fine, and a person decides the rest by ear with a click.

The stage never picks silently. Under 0.3 z of margin, under 80 % of 16-bar
stretches agreeing, or with a change of phase inside the song (an inserted
short bar), the status is `needs_click_check`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Sequence

import numpy as np

from .spectral import Spectra

MARGIN_Z = 0.3
FLAT_SHARE = 0.05
MAX_EXCURSION_BLOCKS = 4
AGREE_SHARE = 0.8
STRETCH_BEATS = 64
MIN_STRETCH_BEATS = 32
BLOCK_BEATS = 16
SWITCH_COST = 8.0
SWITCH_SHARE = 0.5
PHRASE_BEATS = 32
NOVELTY_BEATS = 16
PEAK_REACH_BEATS = 2
PEAK_SPREADS = 1.0
PHRASE_SCALE = 2.0
KICK_WINDOW = (-0.03, 0.07)
PROFILE_NEAR, PROFILE_FAR = 0.15, 0.8


@dataclass(frozen=True)
class BarMap:
    """Bar-one evidence and the decision taken from it."""

    status: str
    downbeat_slot: int | None
    one_or_three: tuple[int, int] | None
    slot_scores: tuple[float, float, float, float]
    clearance: float
    pair_margin: float
    within_pair: dict
    stretches: tuple[dict, ...]
    spans_backing: str
    phase_changes: tuple[dict, ...] = ()
    notes: tuple[str, ...] = ()
    question: str = ""

    def phases_for_cuts(self) -> tuple[int, ...]:
        """Phases whose ones and threes are safe cut points."""
        if self.downbeat_slot is not None:
            return (self.downbeat_slot,)
        if self.one_or_three is not None:
            return (self.one_or_three[0],)
        return ()

    def cut_beats(self, beats: np.ndarray) -> np.ndarray:
        """Beat times on counts one or three (the same set for either phase of a tie)."""
        index = np.arange(len(beats))
        keep = np.zeros(len(beats), dtype=bool)
        for p in self.phases_for_cuts():
            keep |= (index - p) % 2 == 0
        return np.asarray(beats)[keep]

    def to_dict(self) -> dict:
        return {"slot_scores": [round(s, 3) for s in self.slot_scores], "clearance": round(self.clearance, 3),
                "pair_margin": round(self.pair_margin, 3), "spans_backing": self.spans_backing,
                "one_or_three": list(self.one_or_three) if self.one_or_three else None,
                "within_pair": {k: round(v, 3) for k, v in self.within_pair.items()},
                "stretches": list(self.stretches), "phase_changes": list(self.phase_changes),
                "notes": list(self.notes)}


@dataclass(frozen=True)
class BeatFeatures:
    """Per-beat features, each z-scored over the song (zeros where a feature is flat)."""

    kick: np.ndarray
    snare: np.ndarray
    chord: np.ndarray
    bass: np.ndarray
    accent: np.ndarray
    novelty: np.ndarray = field(repr=False)


def _z(values: np.ndarray) -> np.ndarray:
    """Z-scores, or zeros when the feature barely varies (spread under 5 % of its typical size).

    Without that floor, a feature that is the same on every beat (one kick
    sound on every beat) would have its rounding noise blown up into votes.
    """
    values = np.asarray(values, dtype=np.float64)
    spread = values.std()
    size = max(abs(values.mean()), spread)
    if spread <= 1e-12 or spread < FLAT_SHARE * size:
        return np.zeros_like(values)
    return (values - values.mean()) / spread


def _periods(beats: np.ndarray) -> np.ndarray:
    if len(beats) < 2:
        return np.full(len(beats), 0.5)
    gaps = np.diff(beats)
    return np.concatenate([gaps, gaps[-1:]])


def _change(spectra: Spectra, which: str, beats: np.ndarray) -> np.ndarray:
    """Cosine distance between the pitch profile just before and just after each beat."""
    out = np.zeros(len(beats))
    for i, (t, p) in enumerate(zip(beats, _periods(beats))):
        pre = spectra.profile(which, t - PROFILE_FAR * p, t - PROFILE_NEAR * p)
        post = spectra.profile(which, t + PROFILE_NEAR * p, t + PROFILE_FAR * p)
        norm = np.linalg.norm(pre) * np.linalg.norm(post)
        out[i] = 1.0 - float(pre @ post) / norm if norm > 1e-12 else 0.0
    return out


def _texture(spectra: Spectra, beats: np.ndarray) -> np.ndarray:
    """A small description of the sound over each beat: pitch profile shape and levels."""
    rows = []
    for t, p in zip(beats, _periods(beats)):
        chroma = spectra.profile("chroma", t, t + p)
        bass = spectra.profile("bass", t, t + p)
        total = chroma.sum() + 1e-12
        a, b = spectra.frame(t), spectra.frame(t + p) + 1
        levels = [np.log(chroma.sum() + 1e-9), np.log(bass.sum() + 1e-9),
                  float(spectra.onset[a:b].mean()) if b > a else 0.0, spectra.peak("snare", t, t + p)]
        rows.append(np.concatenate([chroma / total, levels]))
    table = np.array(rows)
    spread = table.std(axis=0)
    return (table - table.mean(axis=0)) / np.where(spread > 1e-12, spread, 1.0)


def _novelty(spectra: Spectra, beats: np.ndarray) -> np.ndarray:
    """How different the next few beats sound from the last few, per beat."""
    table = _texture(spectra, beats)
    out = np.zeros(len(beats))
    for i in range(NOVELTY_BEATS, len(beats) - NOVELTY_BEATS + 1):
        before = table[i - NOVELTY_BEATS:i].mean(axis=0)
        after = table[i:i + NOVELTY_BEATS].mean(axis=0)
        out[i] = float(np.linalg.norm(after - before))
    return out


def beat_features(beats: np.ndarray, drums: Spectra, band: Spectra | None = None,
                  swells: Sequence[dict] = ()) -> BeatFeatures:
    """Measure every beat. `drums` gives kick and snare, `band` the pitch features."""
    beats = np.asarray(beats, dtype=np.float64)
    tonal = band if band is not None else drums
    kick = [drums.peak("low", t + KICK_WINDOW[0], t + KICK_WINDOW[1]) for t in beats]
    snare = [drums.peak("snare", t + KICK_WINDOW[0], t + KICK_WINDOW[1]) for t in beats]
    accent = np.zeros(len(beats))
    for item in swells:
        if len(beats):
            i = int(np.argmin(np.abs(beats - item["t"])))
            accent[i] = max(accent[i], float(item["punch"]))
    return BeatFeatures(kick=_z(kick), snare=_z(snare), chord=_z(_change(tonal, "chroma", beats)),
                        bass=_z(_change(tonal, "bass", beats)), accent=_z(accent),
                        novelty=_z(_novelty(tonal, beats)))


def _weights() -> dict[str, np.ndarray]:
    """Weight of each feature on counts one to four of a bar."""
    return {"kick": np.array([1.0, 0.0, 1.0, 0.0]), "chord": np.array([1.0, 0.0, 0.0, 0.0]),
            "accent": np.array([1.0, 0.0, 0.0, 0.0]), "snare": np.array([-1.0, 1.0, -1.0, 1.0])}


def _contributions(features: BeatFeatures, phase: int, index: np.ndarray) -> np.ndarray:
    """Each beat's share of a phase's score (summed over four beats it equals the score)."""
    count = (index - phase) % 4
    out = np.zeros(len(index))
    for name, weight in _weights().items():
        out += weight[count] * getattr(features, name)
    return out


def _phase_score(features: BeatFeatures, phase: int, index: np.ndarray) -> float:
    count = (index - phase) % 4
    total = 0.0
    for name, weight in _weights().items():
        values = getattr(features, name)
        for c in range(4):
            if weight[c] and np.any(count == c):
                total += weight[c] * values[count == c].mean()
    return float(total)


def _count_mean(values: np.ndarray, index: np.ndarray, phase: int, count: int) -> float:
    sel = (index - phase) % 4 == count
    return float(values[sel].mean()) if sel.any() else 0.0


def _phrase_lean(novelty: np.ndarray, index: np.ndarray, phase: int) -> float:
    """How much more often the sound changes on `phase`'s ones than on its threes, at 8-bar spacing.

    A change is a clear peak of the novelty curve: the highest beat within two
    either side, and above the median by one robust deviation. For each
    place in the 8-bar cycle we count the share of cycles that change there;
    the lean is the best share on the ones less the best share on the threes,
    times PHRASE_SCALE, and nothing unless the best place changes at least twice.
    """
    rounds = len(novelty) // PHRASE_BEATS
    if rounds < 2:
        return 0.0
    reach = PEAK_REACH_BEATS
    padded = np.pad(novelty, reach, mode="constant", constant_values=-np.inf)
    local = np.lib.stride_tricks.sliding_window_view(padded, 2 * reach + 1).max(axis=1)
    centre = np.median(novelty)
    spread = 1.4826 * np.median(np.abs(novelty - centre))
    peaks = (novelty >= local) & (novelty > centre + PEAK_SPREADS * max(spread, 1e-9))
    counts = np.array([peaks[index % PHRASE_BEATS == r].sum() for r in range(PHRASE_BEATS)])
    ones = max(counts[r] for r in range(PHRASE_BEATS) if r % 4 == phase)
    thirds = max(counts[r] for r in range(PHRASE_BEATS) if r % 4 == (phase + 2) % 4)
    if max(ones, thirds) < 2:
        return 0.0
    return float(PHRASE_SCALE * (ones - thirds) / rounds)


def _within_pair(features: BeatFeatures, index: np.ndarray, phase: int, phrase: bool = True) -> dict:
    """Evidence that `phase` rather than `phase + 2` is the one (positive) or the reverse."""
    other = (phase + 2) % 4
    base = _phase_score(features, phase, index) - _phase_score(features, other, index)
    bass = _count_mean(features.bass, index, phase, 0) - _count_mean(features.bass, index, phase, 2)
    lean = _phrase_lean(features.novelty, index, phase) if phrase else 0.0
    return {"chords_accents": base, "bass": bass, "phrase": lean, "total": base + bass + lean}


def _stretches(features: BeatFeatures, index: np.ndarray, pair: tuple[int, int] | None) -> list[dict]:
    out = []
    for first in range(0, len(index), STRETCH_BEATS):
        stop = min(first + STRETCH_BEATS, len(index))
        if stop - first < MIN_STRETCH_BEATS:
            break
        part = BeatFeatures(*(getattr(features, n)[first:stop] for n in
                              ("kick", "snare", "chord", "bass", "accent", "novelty")))
        idx = index[first:stop]
        scores = [_phase_score(part, p, idx) for p in range(4)]
        row = {"from_beat": int(first), "to_beat": int(stop), "best_phase": int(np.argmax(scores))}
        if pair is not None:
            lean = _within_pair(part, idx, pair[0], phrase=False)["total"]
            row["lean"] = round(float(lean), 3)
            row["leans_to"] = int(pair[0] if lean >= 0 else pair[1]) if abs(lean) >= MARGIN_Z else None
        out.append(row)
    return out


def _phase_path(features: BeatFeatures, index: np.ndarray) -> list[int]:
    """Phase per block of 4 bars; a change must pay for itself.

    A change costs half of what a typical block's best phase wins by over its
    runner-up, and never less than SWITCH_COST.
    """
    chunks = list(range(0, len(index), BLOCK_BEATS))
    contrib = np.stack([_contributions(features, p, index) for p in range(4)])
    gain = np.array([[contrib[p, b:b + BLOCK_BEATS].sum() for p in range(4)] for b in chunks])
    ordered = np.sort(gain, axis=1)
    wins = ordered[:, -1] - ordered[:, -2]
    switch = max(SWITCH_COST, SWITCH_SHARE * float(np.median(wins))) if len(wins) else SWITCH_COST
    best = gain[0].copy()
    back = np.zeros((len(chunks), 4), dtype=int)
    for k in range(1, len(chunks)):
        stay = best
        move = best.max() - switch
        from_move = int(best.argmax())
        new = np.empty(4)
        for p in range(4):
            if stay[p] >= move:
                new[p], back[k, p] = stay[p] + gain[k, p], p
            else:
                new[p], back[k, p] = move + gain[k, p], from_move
        best = new
    path = [int(best.argmax())]
    for k in range(len(chunks) - 1, 0, -1):
        path.append(int(back[k, path[-1]]))
    return path[::-1]


def _runs(path: list[int]) -> list[list[int]]:
    """[phase, first_block, stop_block] for each run of equal phases."""
    out: list[list[int]] = []
    for k, phase in enumerate(path):
        if out and out[-1][0] == phase:
            out[-1][2] = k + 1
        else:
            out.append([phase, k, k + 1])
    return out


def _fold_excursions(path: list[int]) -> tuple[list[int], list[tuple[int, int, int]]]:
    """Undo short detours that come back to the same phase.

    A few bars that prefer another phase and then return are a section with
    a different groove, not a short bar followed by a long one. Returns the
    path without them and the detours as (phase, first_block, stop_block).
    """
    path = list(path)
    detours = []
    changed = True
    while changed:
        changed = False
        runs = _runs(path)
        for before, middle, after in zip(runs, runs[1:], runs[2:]):
            if before[0] == after[0] and middle[2] - middle[1] <= MAX_EXCURSION_BLOCKS:
                detours.append((middle[0], middle[1], middle[2]))
                path[middle[1]:middle[2]] = [before[0]] * (middle[2] - middle[1])
                changed = True
                break
    return path, detours


def _phase_changes(features: BeatFeatures, beats: np.ndarray, index: np.ndarray) -> tuple[list[dict], list[dict]]:
    """Lasting changes of phase (inserted bars), and short detours (reported, not acted on)."""
    path, detours = _fold_excursions(_phase_path(features, index))
    contrib = np.stack([_contributions(features, p, index) for p in range(4)])
    changes = []
    for k in range(1, len(path)):
        old, new = path[k - 1], path[k]
        if old == new:
            continue
        lo, hi = (k - 1) * BLOCK_BEATS, min((k + 1) * BLOCK_BEATS, len(index))
        totals = [contrib[old, lo:split].sum() + contrib[new, split:hi].sum() for split in range(lo, hi + 1)]
        split = lo + int(np.argmax(totals))
        at = next((i for i in range(split, len(index)) if (i - new) % 4 == 0), split)
        changes.append({"at_beat": int(at), "time": round(float(beats[min(at, len(beats) - 1)]), 3),
                        "from_phase": int(old), "to_phase": int(new)})
    stretches = [{"from_beat": a * BLOCK_BEATS, "to_beat": min(b * BLOCK_BEATS, len(index)), "phase": int(p),
                  "from_time": round(float(beats[a * BLOCK_BEATS]), 3)} for p, a, b in detours]
    return changes, stretches


def naive_low_band_phase(beats: np.ndarray, drums: Spectra) -> int:
    """The phase with the strongest kicks on its ones: the method that fails on a decoy."""
    kick = np.array([drums.peak("low", t + KICK_WINDOW[0], t + KICK_WINDOW[1]) for t in beats])
    index = np.arange(len(beats))
    return int(np.argmax([kick[index % 4 == p].mean() for p in range(4)]))


def _question(pair: tuple[int, int] | None) -> str:
    if pair is None:
        return ("Where is the one? Make a click on phase 0 over the song (tools/click.py --phase 0), "
                "count along, and try phases 1 to 3 until the loud blip lands where you count one.")
    a, b = pair
    return (f"Is the one on phase {a} or {b}? Cuts on either are already safe. Make a click on phase {a} "
            f"over the song (tools/click.py --phase {a}) and count along: if the loud blip feels like the "
            f"middle of the bar, the one is phase {b}. Write the answer as downbeat_slot in film.json.")


@dataclass(frozen=True)
class _Grounds:
    scores: tuple[float, float, float, float]
    pair: tuple[int, int]
    pair_margin: float
    within: dict
    stretches: list[dict]
    changes: list[dict]
    detours: list[dict]


def _gather(beats: np.ndarray, drums: Spectra, band: Spectra | None, swells: Sequence[dict]) -> _Grounds:
    features = beat_features(beats, drums, band, swells)
    index = np.arange(len(beats))
    scores = tuple(_phase_score(features, p, index) for p in range(4))
    best = int(np.argmax(scores))
    rivals = max(scores[(best + 1) % 4], scores[(best + 3) % 4])
    pair_margin = min(scores[best], scores[(best + 2) % 4]) - rivals
    within = _within_pair(features, index, best)
    pair = (best, (best + 2) % 4)
    if within["total"] < 0:
        pair = (pair[1], pair[0])
        within = _within_pair(features, index, pair[0])
    changes, detours = _phase_changes(features, beats, index)
    return _Grounds(scores, pair, pair_margin, within, _stretches(features, index, pair), changes, detours)


def _detour_notes(ev: _Grounds) -> list[str]:
    return [f"beats {d['from_beat']} to {d['to_beat']} (from {d['from_time']} s) prefer phase {d['phase']}; "
            f"taken as a change of groove, not of bar" for d in ev.detours]


def _confirm(phase: int) -> str:
    return (f"Decided: the one is phase {phase}. Confirm once by ear: tools/click.py --phase {phase} over "
            f"the song, and count along.")


def find_bar_one(beats: np.ndarray, drums: Spectra, band: Spectra | None = None,
                 swells: Sequence[dict] = ()) -> BarMap:
    """Decide the bar's one on a beat grid, or say exactly what is left to decide by ear."""
    ev = _gather(np.asarray(beats, dtype=np.float64), drums, band, swells)
    total = len(ev.stretches)
    pair_agree = sum(r["best_phase"] in ev.pair for r in ev.stretches)
    # A stretch with no clear lean of its own (under 0.3 z) does not count against a song-wide
    # cue such as the eight-bar phrase; only a stretch leaning the other way does.
    lean_agree = sum(r.get("leans_to") in (ev.pair[0], None) for r in ev.stretches)
    notes = _detour_notes(ev)
    common = dict(slot_scores=ev.scores, pair_margin=ev.pair_margin, within_pair=ev.within,
                  stretches=tuple(ev.stretches), phase_changes=tuple(ev.changes))
    if ev.pair_margin < MARGIN_Z or (total and pair_agree < AGREE_SHARE * total):
        notes.append(f"cannot tell the one from the two: margin {ev.pair_margin:.2f} z, "
                     f"{pair_agree}/{total} stretches agree")
        return BarMap("needs_click_check", None, None, clearance=ev.pair_margin, spans_backing=f"{pair_agree}/{total}",
                      notes=tuple(notes), question=_question(None), **common)
    if ev.changes:
        first = ev.changes[0]["from_phase"]
        notes.append("phase changes inside the song (a short or long bar): " + ", ".join(
            f"beat {c['at_beat']} ({c['from_phase']} to {c['to_phase']})" for c in ev.changes))
        agree = sum(r["best_phase"] == first for r in ev.stretches)
        return BarMap("needs_click_check", first, None, clearance=min(ev.pair_margin, abs(ev.within["total"])),
                      spans_backing=f"{agree}/{total}", notes=tuple(notes),
                      question=_question((first, (first + 2) % 4)), **common)
    picked = ev.pair[0]
    if ev.within["total"] >= MARGIN_Z and (not total or lean_agree >= AGREE_SHARE * total):
        return BarMap("decided", picked, None, clearance=min(ev.pair_margin, ev.within["total"]),
                      spans_backing=f"{lean_agree}/{total}", notes=tuple(notes),
                      question=_confirm(picked), **common)
    tie = (min(ev.pair), max(ev.pair))
    notes.append(f"one or three: phases {tie[0]} and {tie[1]} differ by {ev.within['total']:.2f} z, "
                 f"{lean_agree}/{total} stretches lean to {picked}")
    return BarMap("needs_click_check", None, tie, clearance=abs(ev.within["total"]), spans_backing=f"{pair_agree}/{total}",
                  notes=tuple(notes), question=_question(tie), **common)


def apply_heard_slot(result: BarMap, downbeat_slot: int) -> BarMap:
    """Take a person's `downbeat_slot` (from film.json) over the evidence, noting any conflict."""
    phase = int(downbeat_slot) % 4
    notes = list(result.notes)
    against = result.slot_scores[result.slot_scores.index(max(result.slot_scores))] - result.slot_scores[phase]
    snare_side = (phase - int(np.argmax(result.slot_scores))) % 2 == 1
    if snare_side and result.pair_margin > MARGIN_Z:
        notes.append(f"downbeat_slot {phase} puts the one on a snare beat; the evidence is {against:.2f} z against it")
    notes.append(f"downbeat_slot {phase} set by a person")
    return replace(result, status="override", downbeat_slot=phase, one_or_three=None, notes=tuple(notes), question="")
