"""`fit`: place a render on the song by comparing its soundtrack with the audio it was sent.

Per phrase of the sent audio (plus 50 ms each side), the phrase is found inside the render from 1.3 s before to
0.9 s after by subsequence DTW on cosine distance between sound features, with a 0.06 penalty for every hold. The
phrase's cost is the path's mean cost per step: near 0 is the same sound; over 0.45 the phrase is not used. The path
is smoothed over 0.25 s and read every 0.1 s, with the local rate kept between 0.7 and 1.4. Only points where the
sent audio is voiced (within 28 dB of its peak for 80 ms each side) go into the map, which takes a 0.5 s running
median of the offsets, stays monotonic and runs at 1x outside its points.

Times: phrases and points are in the sent audio's own time (the slice) and the render's time; the map and pauses are
in song time (`slice_start` plus slice time).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dtw import subsequence_path
from .features import FEATURE_RATE, HOP_S, levels_db, mono, resample, sound_features

CONTEXT_S = 0.05
SEARCH_BEFORE_S = 1.3
SEARCH_AFTER_S = 0.9
HOLD_PENALTY = 0.06
SMOOTH_S = 0.25
POINT_STEP_S = 0.1
RATE_RANGE = (0.7, 1.4)
VOICED_DB = 28.0
VOICED_GUARD_S = 0.08
MEDIAN_S = 0.5
UNUSED_COST = 0.45
REST_S = 0.15
JOIN_GAP_S = 0.45
MIN_PHRASE_S = 0.2


@dataclass(frozen=True)
class _Sound:
    features: np.ndarray
    levels: np.ndarray


def _prepare(samples: np.ndarray, rate: int) -> _Sound:
    x = resample(samples, rate, FEATURE_RATE) if rate != FEATURE_RATE else mono(samples)
    return _Sound(sound_features(x, FEATURE_RATE), levels_db(x, FEATURE_RATE, HOP_S))


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """(start, end) frame ranges where `mask` is true, end exclusive."""
    padded = np.concatenate([[False], mask, [False]]).astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


def _vocal_mask(levels: np.ndarray) -> np.ndarray:
    """Frames within 28 dB of the peak for 80 ms on each side."""
    if len(levels) == 0:
        return np.zeros(0, dtype=bool)
    loud = levels >= levels.max() - VOICED_DB
    if levels.max() <= -100:
        return np.zeros(len(levels), dtype=bool)
    guard = int(round(VOICED_GUARD_S / HOP_S))
    padded = np.concatenate([np.zeros(guard, bool), loud, np.zeros(guard, bool)])
    windows = np.lib.stride_tricks.sliding_window_view(padded, 2 * guard + 1)
    return windows.all(axis=1)


def voiced_phrases(samples: np.ndarray, rate: int) -> list[tuple[float, float]]:
    """(start, end) seconds of sound no more than VOICED_DB below the loudest frame; holes shorter than JOIN_GAP_S
    are bridged and pieces under MIN_PHRASE_S dropped."""
    return _vocal_spans(levels_db(resample(samples, rate, FEATURE_RATE), FEATURE_RATE, HOP_S))


def _vocal_spans(levels: np.ndarray) -> list[tuple[float, float]]:
    if len(levels) == 0 or levels.max() <= -100:
        return []
    runs = _runs(levels >= levels.max() - VOICED_DB)
    joined: list[list[int]] = []
    for start, end in runs:
        if joined and (start - joined[-1][1]) * HOP_S < JOIN_GAP_S:
            joined[-1][1] = end
        else:
            joined.append([start, end])
    return [(round(s * HOP_S, 3), round(e * HOP_S, 3)) for s, e in joined if (e - s) * HOP_S >= MIN_PHRASE_S]


def _moving_mean(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 1 or len(values) < 2:
        return values.copy()
    half = width // 2
    padded = np.concatenate([np.full(half, values[0]), values, np.full(half, values[-1])])
    kernel = np.ones(2 * half + 1) / (2 * half + 1)
    return np.convolve(padded, kernel, mode="valid")


def _fill_silent(render_at: np.ndarray, silent: np.ndarray) -> np.ndarray:
    """Silence matches silence anywhere, so it says nothing about timing: give silent frames the timing of their
    sounding neighbours, between them by a straight line and past them at 1x."""
    sounding = np.flatnonzero(~silent)
    if len(sounding) == 0 or len(sounding) == len(render_at):
        return render_at
    frames = np.arange(len(render_at))
    filled = np.interp(frames, sounding, render_at[sounding])
    before = frames < sounding[0]
    after = frames > sounding[-1]
    filled[before] = render_at[sounding[0]] - (sounding[0] - frames[before])
    filled[after] = render_at[sounding[-1]] + (frames[after] - sounding[-1])
    return filled


def _inserted(path: np.ndarray, first_query: int, last_query: int, min_frames: int) -> list[tuple[int, int, int]]:
    """Pauses the render adds: (query frame, render frame, extra frames) where the render spends at least
    `min_frames` more than the sent audio over a short stretch. The sent audio may have a short gap there (a breath
    between syllables); the render's extra time is counted beyond it."""
    _, first_steps = np.unique(path[:, 0], return_index=True)
    first_render = path[first_steps, 1]
    extra = np.clip(np.diff(first_render) - 1, 0, None)
    busy = np.flatnonzero(extra >= 2)
    if len(busy) == 0:
        return []
    clusters = np.split(busy, np.flatnonzero(np.diff(busy) > 3) + 1)
    events = []
    for group in clusters:
        stretch = extra[group[0]:group[-1] + 1]
        peak = int(group[0] + np.argmax(stretch))
        q = first_query + peak
        if stretch.sum() >= min_frames and first_query + 5 <= q <= last_query - 5:
            events.append((q, int(first_render[peak]), int(stretch.sum())))
    return events


def _place_vocal_span(sent: _Sound, clip: _Sound, vocal_on: np.ndarray, start_s: float, stop_s: float) -> dict:
    q0 = max(0, int(round((start_s - CONTEXT_S) / HOP_S)))
    q1 = min(len(sent.features), int(round((stop_s + CONTEXT_S) / HOP_S)) + 1)
    r0 = max(0, int(round((start_s - SEARCH_BEFORE_S) / HOP_S)))
    r1 = min(len(clip.features), int(round((stop_s + SEARCH_AFTER_S) / HOP_S)) + 1)
    result = {"from": round(start_s, 3), "to": round(stop_s, 3), "cost": 1.0, "rate": None, "ties": []}
    if q1 - q0 < 3 or r1 - r0 < 3:
        return {**result, "_held": [], "_raw": []}
    cost = np.clip(1.0 - sent.features[q0:q1] @ clip.features[r0:r1].T, 0.0, 2.0)
    path, total = subsequence_path(cost, HOLD_PENALTY)
    path = path + np.array([q0, r0])
    mean_cost = total / len(path)
    queries = np.arange(q0, q1)
    sums = np.bincount(path[:, 0] - q0, weights=path[:, 1], minlength=q1 - q0)
    counts = np.bincount(path[:, 0] - q0, minlength=q1 - q0)
    raw = _fill_silent(sums / np.maximum(counts, 1), sent.features[q0:q1, -1] > 0.5)
    render_at = _moving_mean(raw, int(round(SMOOTH_S / HOP_S)))
    step = int(round(POINT_STEP_S / HOP_S))
    picks = np.arange(0, len(queries), step)
    times = queries[picks] * HOP_S
    rendered = render_at[picks] * HOP_S
    for k in range(1, len(rendered)):
        gap = times[k] - times[k - 1]
        rendered[k] = np.clip(rendered[k], rendered[k - 1] + RATE_RANGE[0] * gap, rendered[k - 1] + RATE_RANGE[1] * gap)
    rate = float(np.polyfit(times, rendered, 1)[0]) if len(times) >= 2 else 1.0
    keep = vocal_on[np.minimum(queries[picks], len(vocal_on) - 1)] if len(vocal_on) else np.zeros(len(picks), bool)
    used = mean_cost <= UNUSED_COST
    ties = [[round(float(t), 3), round(float(r), 3)] for t, r, k in zip(times, rendered, keep) if k] if used else []
    held = _inserted(path, q0, q1 - 1, int(round(REST_S / HOP_S))) if used else []
    return {**result, "cost": round(float(mean_cost), 4), "rate": round(rate, 3), "ties": ties, "_held": held}


def _median_offsets(times: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    half = MEDIAN_S / 2
    return np.array([np.median(offsets[np.abs(times - t) <= half + 1e-9]) for t in times])


def fit_by_sound(sent: np.ndarray, sent_rate: int, clip: np.ndarray, render_rate: int, *,
                 vocal_spans: list[tuple[float, float]] | None = None, slice_start: float = 0.0) -> dict:
    """Place `render` (its soundtrack) against `sent` (the audio the render was given).

    `phrases` are (start, end) seconds in the sent audio; found from its voiced stretches when not given.
    `slice_start` is where the sent audio starts in the song.
    """
    sent_sound = _prepare(sent, sent_rate)
    render_sound = _prepare(clip, render_rate)
    vocal_on = _vocal_mask(sent_sound.levels)
    spans = vocal_spans if vocal_spans is not None else _vocal_spans(sent_sound.levels)
    placed = [_place_vocal_span(sent_sound, render_sound, vocal_on, float(a), float(b)) for a, b in spans]

    pairs = sorted((t, r) for phrase in placed for t, r in phrase["ties"])
    song_map: list[list[float]] = []
    if pairs:
        times = np.array([t for t, _ in pairs])
        offsets = _median_offsets(times, np.array([r - t for t, r in pairs]))
        rendered = np.maximum.accumulate(times + offsets)
        song_map = [[round(slice_start + float(t), 3), round(float(r), 3)] for t, r in zip(times, rendered)]
    rests = [{"at": round(slice_start + q * HOP_S, 3), "render_at": round(r * HOP_S, 3), "seconds": round(n * HOP_S, 3)}
              for phrase in placed for q, r, n in phrase["_held"]]
    offset = float(np.median([r - t for t, r in pairs])) if pairs else None
    return {
        "how": "sound",
        "slice_start": slice_start,
        "vocal_spans": [{k: v for k, v in phrase.items() if not k.startswith("_")} for phrase in placed],
        "map": song_map,
        "added_rests": rests,
        "offset": round(offset, 3) if offset is not None else None,
    }


def render_time_at(fit: dict, song_time: float) -> float:
    """Render time shown at `song_time`: the map between its points, 1x before and after them."""
    song_map = fit.get("map") or []
    if not song_map:
        return song_time - fit.get("slice_start", 0.0)
    times = np.array([t for t, _ in song_map])
    rendered = np.array([r for _, r in song_map])
    if song_time <= times[0]:
        return float(rendered[0] + song_time - times[0])
    if song_time >= times[-1]:
        return float(rendered[-1] + song_time - times[-1])
    return float(np.interp(song_time, times, rendered))
