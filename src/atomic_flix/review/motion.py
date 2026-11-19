"""Motion measures that need no model, on grey frames (floats 0 to 1, shaped (n, h, w)).

- camera drift: the background's shift, by phase correlation between frames a quarter second apart, summed over
  the shot, as a share of the frame. The picture is cut into a 4 by 4 grid of tiles; the camera's step is the median
  step of the tiles that show background (the outer ring of tiles, or the tiles a background mask covers), so a big
  subject crossing a locked frame moves its own tiles and not the camera. Tiles moving apart from the camera are
  reported as subject motion;
- still head and tail: how long the shot holds the same picture at its start and at its end;
- jumps: single-frame changes far above the shot's usual change (an inner cut, a reset, a flash);
- the first and last half second: is the picture moving when the shot comes on and when it goes off;
- mouth energy: plain pixel change inside a mouth box (beyond the whole frame's change), while she sings against
  while she does not.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PAIR_SECONDS = 0.25
END_WINDOW_SECONDS = 0.5
STILL_LEVEL = 0.004
STILL_FLAG_SECONDS = 0.5
JUMP_FLOOR = 0.05
JUMP_RATIO = 3.0
LOCKED_DRIFT_LIMIT = 0.02
MOUTH_LAG_SECONDS = 1 / 12
MOUTH_FLOOR = 0.005
MOUTH_RATIO = 1.5
SILENCE_NEEDED_SECONDS = 0.5
TINY = 1e-6
TILES = 4                  # the picture is measured as TILES x TILES tiles
SUBJECT_PX = 1.0           # a tile stepping this far from the camera's step moves on its own
FLAT_TILE = 0.01           # a tile whose grey spread is under this shows no texture to follow
TILE_REACH = 0.4           # past this share of a tile, a step is beyond the tiles' reach: use the whole picture
BACKGROUND_SHARE = 0.5     # a tile counts as background when the mask covers at least this share of it


@dataclass(frozen=True)
class Drift:
    dx: float          # share of the frame width the content moved, right positive
    dy: float          # share of the frame height, down positive
    largest: float     # largest distance from the first frame over the shot, in frame shares
    path: tuple[tuple[float, float, float], ...]   # (seconds, dx, dy) after each step
    foreground: float = 0.0   # largest share of the picture moving apart from the camera in one step

    def to_dict(self) -> dict:
        return {"dx": round(self.dx, 4), "dy": round(self.dy, 4), "largest": round(self.largest, 4),
                "foreground": round(self.foreground, 4)}


def _lag(fps: float, seconds: float) -> int:
    return max(1, int(round(seconds * fps)))


def _shift(first: np.ndarray, second: np.ndarray, span: np.ndarray) -> tuple[float, float]:
    """(dx, dy) in pixels that carries `first` onto `second`, by phase correlation with a sub-pixel peak."""
    a = np.fft.fft2((first - first.mean()) * span)
    b = np.fft.fft2((second - second.mean()) * span)
    cross = b * np.conj(a)
    surface = np.real(np.fft.ifft2(cross / (np.abs(cross) + TINY)))
    peak_y, peak_x = np.unravel_index(int(np.argmax(surface)), surface.shape)
    height, width = surface.shape

    def refine(axis_values: np.ndarray, at: int, size: int) -> float:
        left, centre, right = axis_values[(at - 1) % size], axis_values[at], axis_values[(at + 1) % size]
        bend = left - 2 * centre + right
        offset = 0.0 if abs(bend) < TINY else 0.5 * (left - right) / bend
        value = at + offset
        return value - size if value > size / 2 else value

    return refine(surface[peak_y, :], peak_x, width), refine(surface[:, peak_x], peak_y, height)


@dataclass(frozen=True)
class _Tile:
    rows: slice
    cols: slice
    background: bool
    span: np.ndarray


def _tiles(height: int, width: int, background: np.ndarray | None) -> list[_Tile]:
    edges_y = np.linspace(0, height, TILES + 1).round().astype(int)
    edges_x = np.linspace(0, width, TILES + 1).round().astype(int)
    tiles = []
    for row in range(TILES):
        for col in range(TILES):
            rows, cols = slice(edges_y[row], edges_y[row + 1]), slice(edges_x[col], edges_x[col + 1])
            if background is None:
                is_background = row in (0, TILES - 1) or col in (0, TILES - 1)
            else:
                is_background = float(np.asarray(background, bool)[rows, cols].mean()) >= BACKGROUND_SHARE
            span = np.outer(np.hanning(rows.stop - rows.start), np.hanning(cols.stop - cols.start))
            tiles.append(_Tile(rows, cols, is_background, span))
    return tiles


def _camera_step(first: np.ndarray, second: np.ndarray, tiles: list[_Tile],
                 whole: tuple[float, float]) -> tuple[float, float, float]:
    """(dx, dy) of the camera between two frames, and the share of textured tiles moving apart from it."""
    steps, on_background = [], []
    for tile in tiles:
        patch = first[tile.rows, tile.cols]
        if patch.std() < FLAT_TILE:
            continue
        steps.append(_shift(patch, second[tile.rows, tile.cols], tile.span))
        on_background.append(tile.background)
    tile_h = tiles[0].rows.stop - tiles[0].rows.start
    tile_w = tiles[0].cols.stop - tiles[0].cols.start
    beyond_reach = abs(whole[0]) > TILE_REACH * tile_w or abs(whole[1]) > TILE_REACH * tile_h
    picked = [step for step, keep in zip(steps, on_background) if keep]
    if beyond_reach or not picked:
        cam_move = whole
    else:
        cam_move = (float(np.median([s[0] for s in picked])), float(np.median([s[1] for s in picked])))
    apart = [np.hypot(sx - cam_move[0], sy - cam_move[1]) > SUBJECT_PX for sx, sy in steps]
    share = float(np.mean(apart)) if apart and not beyond_reach else 0.0
    return cam_move[0], cam_move[1], share


def camera_drift(frames: np.ndarray, fps: float, background: np.ndarray | None = None) -> Drift:
    """Sum the camera's shift between frames a quarter second apart over the whole shot.

    `background`, a boolean (h, w) mask of pixels known to be background (for example the inverse of a performer
    mask), picks the tiles the camera is read from; without it the outer ring of tiles is used."""
    count, height, width = frames.shape
    lag = _lag(fps, PAIR_SECONDS)
    stops = list(range(0, count, lag))
    if stops[-1] != count - 1:
        stops.append(count - 1)
    span = np.outer(np.hanning(height), np.hanning(width))
    tiles = _tiles(height, width, background)
    x = y = largest = foreground = 0.0
    path = []
    for before, after in zip(stops, stops[1:]):
        whole = _shift(frames[before], frames[after], span)
        step_x, step_y, share = _camera_step(frames[before], frames[after], tiles, whole)
        x, y = x + step_x, y + step_y
        foreground = max(foreground, share)
        largest = max(largest, float(np.hypot(x / width, y / height)))
        path.append((after / fps, x / width, y / height))
    return Drift(dx=x / width, dy=y / height, largest=largest, path=tuple(path), foreground=foreground)


def _differences_from(frames: np.ndarray, reference: np.ndarray) -> np.ndarray:
    return np.abs(frames - reference[None]).mean(axis=(1, 2))


def still_ends(frames: np.ndarray, fps: float) -> tuple[float, float]:
    """Seconds the shot holds its first picture at the start, and its last picture at the end."""
    count = len(frames)
    from_first = _differences_from(frames, frames[0]) > STILL_LEVEL
    from_last = _differences_from(frames, frames[-1]) > STILL_LEVEL
    head_frames = int(np.argmax(from_first)) if from_first.any() else count
    tail_frames = count - 1 - int(np.nonzero(from_last)[0][-1]) if from_last.any() else count
    return head_frames / fps, tail_frames / fps


def frame_changes(frames: np.ndarray, lag: int = 1) -> np.ndarray:
    """Mean grey change between each frame and the one `lag` before it (first `lag` values are 0)."""
    changes = np.zeros(len(frames))
    if len(frames) > lag:
        changes[lag:] = np.abs(frames[lag:] - frames[:-lag]).mean(axis=(1, 2))
    return changes


def jumps(frames: np.ndarray, fps: float) -> list[float]:
    """Seconds (into the shot) of single-frame changes over the floor and far above the shot's median change."""
    changes = frame_changes(frames)
    if len(changes) < 3:
        return []
    usual = float(np.median(changes[1:]))
    found = np.nonzero((changes > JUMP_FLOOR) & (changes > JUMP_RATIO * max(usual, TINY)))[0]
    return [float(index / fps) for index in found]


def _window_report(frames: np.ndarray, changes: np.ndarray, jump_times: list[float], fps: float, first: int,
                   last: int) -> dict:
    span = float(np.abs(frames[last] - frames[first]).mean())
    movement = float(changes[max(first, 1):last + 1].mean()) if last > first else 0.0
    inside = [t for t in jump_times if first / fps <= t <= last / fps]
    return {"from": round(first / fps, 3), "to": round((last + 1) / fps, 3), "movement": round(movement, 5),
            "change_over_window": round(span, 5), "still": bool(span < STILL_LEVEL and movement < STILL_LEVEL),
            "jumps": [round(t, 3) for t in inside]}


def end_windows(frames: np.ndarray, fps: float) -> dict:
    """The first and the last half second of a shot as shown: motion, change over the window, still, jumps."""
    count = len(frames)
    width = min(count, _lag(fps, END_WINDOW_SECONDS))
    changes = frame_changes(frames)
    jump_times = jumps(frames, fps)
    return {"opening": _window_report(frames, changes, jump_times, fps, 0, width - 1),
            "closing": _window_report(frames, changes, jump_times, fps, count - width, count - 1)}


def _box_pixels(frames: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    height, width = frames.shape[1:]
    x, y, w, h = box
    left, top = int(round(x * width)), int(round(y * height))
    right, bottom = max(left + 1, int(round((x + w) * width))), max(top + 1, int(round((y + h) * height)))
    return frames[:, top:bottom, left:right]


def mouth_energy(frames: np.ndarray, box: tuple[float, float, float, float], vocal_on: np.ndarray,
                 fps: float) -> dict:
    """Pixel change inside the mouth box beyond the whole frame's change, compared while sung and while silent."""
    lag = _lag(fps, MOUTH_LAG_SECONDS)
    inside = frame_changes(_box_pixels(frames, box), lag)
    overall = frame_changes(frames, lag)
    score = np.maximum(0.0, inside - overall)
    if len(score) > lag:
        score[:lag] = score[lag]
    vocal_on = np.asarray(vocal_on, bool)[: len(score)]
    sung, silent = score[vocal_on], score[~vocal_on]
    mean_sung = float(sung.mean()) if sung.size else None
    mean_silent = float(silent.mean()) if silent.size else None
    ratio = None
    if mean_sung is not None and mean_silent is not None:
        ratio = (mean_sung + 1e-4) / (mean_silent + 1e-4)
    correlation = None
    if sung.size and silent.size and score.std() > TINY:
        correlation = float(np.corrcoef(score, vocal_on.astype(float))[0, 1])
    flags = []
    if mean_sung is not None and mean_sung < MOUTH_FLOOR:
        flags.append(f"mouth barely moves while she sings (energy {mean_sung:.4f})")
    if ratio is not None and silent.size >= SILENCE_NEEDED_SECONDS * fps and ratio < MOUTH_RATIO:
        flags.append(f"mouth moves about as much in silence as in song (ratio {ratio:.2f})")
    return {"box": list(box), "sung_energy": None if mean_sung is None else round(mean_sung, 5),
            "silent_energy": None if mean_silent is None else round(mean_silent, 5),
            "ratio": None if ratio is None else round(ratio, 3),
            "correlation": None if correlation is None else round(correlation, 3),
            "sung_seconds": round(sung.size / fps, 3), "silent_seconds": round(silent.size / fps, 3), "flags": flags}
