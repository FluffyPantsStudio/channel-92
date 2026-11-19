"""Procedural textures with numpy only, so a set rebuilds from this repository alone with no downloads.

Each generator is seeded and returns an HxWx3 uint8 image. Materials name them as "gen:<name>"; the capture step
writes the ones a plan needs into OUT/tex/ before Blender starts. The cabinet face and the dusk sky follow our own
lab/unreal/scripts/texgen.py, redrawn with numpy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from .imageio import write_png


def blur(a: np.ndarray, sx: float, sy: float) -> np.ndarray:
    """Gaussian blur with wrap-around edges, through the FFT (sigmas in pixels)."""
    h, w = a.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.rfftfreq(w)[None, :]
    gain = np.exp(-2 * (np.pi ** 2) * ((fx * sx) ** 2 + (fy * sy) ** 2))
    return np.fft.irfft2(np.fft.rfft2(a) * gain, s=(h, w)).astype(np.float32)


def _fractal(rng: np.random.Generator, h: int, w: int, sx: float, sy: float, octaves: int = 4) -> np.ndarray:
    acc = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        n = blur(rng.random((h, w)).astype(np.float32), sx / 2 ** o, max(1.0, sy / 2 ** o))
        n = (n - n.mean()) / (n.std() + 1e-6)
        acc += n * amp
        total += amp
        amp *= 0.55
    return acc / total


def _to_u8(img: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(img), 0, 255).astype(np.uint8)


def _ramp(values: np.ndarray, stops: list[tuple[float, tuple[int, int, int]]]) -> np.ndarray:
    xs = [a for a, _ in stops]
    return np.stack([np.interp(values, xs, [c[k] for _, c in stops]) for k in range(3)], axis=-1)


# ---------------------------------------------------------------- generators

def steel_case(small: bool = False) -> np.ndarray:
    """Filing-cabinet face, 2 drawers across and 4 down: pink-mauve fronts that darken downward, a dark gap, a lit top
    lip, a shaded lower edge, a handle slot with a chrome grip and a pale label card. Tiles seamlessly."""
    cols, rows, cell = 2, 4, 128
    w, h = cols * cell, rows * cell
    rng = np.random.default_rng(7)
    img = np.empty((h, w, 3), np.float32)
    img[:] = (24, 20, 34)
    gap = 5

    def fill(x0: float, y0: float, x1: float, y1: float, colour) -> None:
        img[int(round(y0)):int(round(y1)) + 1, int(round(x0)):int(round(x1)) + 1] = colour

    for r in range(rows):
        for c in range(cols):
            x0, y0 = c * cell + gap, r * cell + gap
            x1, y1 = (c + 1) * cell - gap, (r + 1) * cell - gap
            tint = rng.uniform(-10, 10)
            top = np.array([212 + tint, 156 + tint * 0.5, 170 + tint * 0.5], np.float32)
            shade = 1.0 - 0.22 * (np.arange(y0, y1 + 1) - y0) / max(1, y1 - y0)
            img[y0:y1 + 1, x0:x1 + 1] = (shade[:, None, None] * top[None, None, :]).astype(np.float32)
            fill(x0, y0, x1, y0 + 3, (226, 170, 190))
            fill(x0, y1 - 3, x1, y1, (96, 56, 82))
            hx0, hx1 = x0 + (x1 - x0) * 0.30, x0 + (x1 - x0) * 0.70
            hy0, hy1 = y0 + (y1 - y0) * 0.34, y0 + (y1 - y0) * 0.56
            fill(hx0, hy0, hx1, hy1, (30, 22, 40))
            fill(hx0 + 3, hy1 - 6, hx1 - 3, hy1 - 2, (196, 204, 214))
            lx0, ly0, lx1 = x0 + (x1 - x0) * 0.38, y0 + (y1 - y0) * 0.72, x0 + (x1 - x0) * 0.62
            fill(lx0, ly0, lx1, ly0 + 12, (230, 226, 214))
    img += rng.normal(0, 3.0, img.shape).astype(np.float32)
    img = np.stack([blur(img[..., k], 0.6, 0.6) for k in range(3)], axis=-1)
    return _to_u8(img)


def dusk(small: bool = False) -> np.ndarray:
    """Equirectangular dusk: peach at the horizon, hot pink, a violet turn, teal overhead, with long cloud streaks
    that lift the colour bands. Row 0 is straight up, the middle row the horizon. Wraps sideways."""
    w, h = (512, 256) if small else (2048, 1024)
    k = w / 4096
    rng = np.random.default_rng(5)
    elev = (0.5 - (np.arange(h, dtype=np.float32) + 0.5) / h) * 180.0
    streak = np.clip(0.5 + 0.38 * _fractal(rng, h, w, 260 * k, 22 * k), 0, 1)
    puff = np.clip(0.5 + 0.5 * _fractal(rng, h, w, 90 * k, 14 * k, 5), 0, 1)
    band = np.clip((elev[:, None] - 5) / 10, 0, 1) * np.clip(1 - np.abs(elev[:, None] - 22) / 40, 0, 1)
    e = elev[:, None] + (streak - 0.5) * 26.0 * band
    stops = [(-90, (58, 22, 58)), (-1, (92, 34, 80)), (1.5, (250, 150, 112)), (5, (240, 108, 128)),
             (9, (226, 92, 148)), (13, (170, 110, 168)), (19, (60, 160, 172)), (36, (26, 146, 160)), (90, (14, 88, 118))]
    img = _ramp(e, stops)
    glow = (np.clip((puff - 0.6) / 0.25, 0, 1) * np.clip(1 - np.abs(elev[:, None] - 12) / 22, 0, 1))[..., None]
    img = img * (1 - 0.55 * glow) + np.array([255, 178, 160], np.float32) * 0.55 * glow
    return _to_u8(img)


def day(small: bool = False) -> np.ndarray:
    """Equirectangular clear day: pale haze at the horizon, blue overhead, a few soft clouds, a dim ground."""
    w, h = (512, 256) if small else (2048, 1024)
    k = w / 2048
    rng = np.random.default_rng(9)
    elev = (0.5 - (np.arange(h, dtype=np.float32) + 0.5) / h) * 180.0
    img = _ramp(np.broadcast_to(elev[:, None], (h, w)),
                [(-90, (60, 66, 58)), (-1, (120, 126, 112)), (0.5, (224, 232, 236)), (8, (176, 206, 232)),
                 (30, (104, 160, 222)), (90, (52, 104, 190))])
    cloud = np.clip((_fractal(rng, h, w, 60 * k, 12 * k, 5) - 0.4) / 0.9, 0, 1)
    cloud *= np.clip((elev[:, None] - 2) / 8, 0, 1) * np.clip(1 - (elev[:, None] - 10) / 50, 0, 1)
    img = img * (1 - 0.7 * cloud[..., None]) + 246 * 0.7 * cloud[..., None]
    return _to_u8(img)


def grass(small: bool = False) -> np.ndarray:
    n = 128 if small else 512
    rng = np.random.default_rng(21)
    blades = _fractal(rng, n, n, 0.8, 6.0, 3)
    patches = _fractal(rng, n, n, 40, 40, 3)
    v = 0.5 + 0.22 * blades + 0.12 * patches
    base = np.array([62, 112, 40], np.float32)
    tip = np.array([128, 170, 72], np.float32)
    img = base + (tip - base) * np.clip(v, 0, 1)[..., None]
    return _to_u8(img)


def gingham(small: bool = False) -> np.ndarray:
    """Red and white picnic check: stripes crossing make three tones, with a faint weave."""
    n = 128 if small else 512
    period = n // 8
    rng = np.random.default_rng(3)
    stripe = (np.arange(n) % period) < period // 2
    both = stripe[:, None] & stripe[None, :]
    one = stripe[:, None] ^ stripe[None, :]
    img = np.empty((n, n, 3), np.float32)
    img[:] = (238, 232, 224)
    img[one] = (214, 112, 112)
    img[both] = (176, 32, 40)
    weave = (np.add.outer(np.arange(n), np.arange(n)) % 2) * 6.0
    img += (weave + rng.normal(0, 2.0, (n, n)))[..., None]
    return _to_u8(img)


def salt(small: bool = False) -> np.ndarray:
    """Salt-flat crust: pale plates with darker raised ridges between them (a wrapped cell pattern)."""
    n = 128 if small else 512
    rng = np.random.default_rng(13)
    cells = 24 if small else 90
    pts = rng.random((cells, 2)) * n
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    best = np.full((n, n), np.inf, np.float32)
    second = np.full((n, n), np.inf, np.float32)
    for px, py in pts:
        dx = np.abs(xx - px)
        dy = np.abs(yy - py)
        d = np.hypot(np.minimum(dx, n - dx), np.minimum(dy, n - dy))
        second = np.where(d < best, best, np.minimum(second, d))
        best = np.minimum(best, d)
    ridge = np.clip(1 - (second - best) / (2.5 * n / 512 + 1.0), 0, 1)
    grain = _fractal(rng, n, n, 3, 3, 3)
    v = 236 - 34 * ridge + 6 * grain
    img = np.stack([v, v - 2, v - 8], axis=-1)
    return _to_u8(img)


def wood(small: bool = False) -> np.ndarray:
    n = 128 if small else 512
    rng = np.random.default_rng(17)
    wobble = _fractal(rng, n, n, 30, 120, 3)
    y = np.arange(n, dtype=np.float32)[None, :] / n
    rings = 0.5 + 0.5 * np.sin(2 * np.pi * (y * 9 + 0.35 * wobble))
    fibre = _fractal(rng, n, n, 0.7, 25, 2)
    v = np.clip(0.55 * rings + 0.15 * fibre + 0.3, 0, 1)[..., None]
    dark, light = np.array([92, 56, 32], np.float32), np.array([176, 120, 74], np.float32)
    return _to_u8(dark + (light - dark) * v)


def tile(small: bool = False) -> np.ndarray:
    """White square tiles with grey grout, four by four per image, each tile a slightly different white."""
    n = 128 if small else 512
    rng = np.random.default_rng(29)
    cell = n // 4
    grout = max(1, cell // 24)
    img = np.empty((n, n, 3), np.float32)
    for r in range(4):
        for c in range(4):
            img[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell] = 232 + rng.uniform(-6, 6)
    lines = (np.arange(n) % cell) < grout
    img[lines, :] = (150, 146, 140)
    img[:, lines] = (150, 146, 140)
    img += rng.normal(0, 1.5, img.shape)
    return _to_u8(img)


def plaster(small: bool = False) -> np.ndarray:
    n = 128 if small else 512
    rng = np.random.default_rng(31)
    v = 0.6 * _fractal(rng, n, n, 18, 18, 4) + 0.4 * _fractal(rng, n, n, 1.5, 1.5, 2)
    base = np.array([218, 206, 188], np.float32)
    return _to_u8(base + 9 * v[..., None])


TEXTURES: dict[str, Callable[..., np.ndarray]] = {
    "steel_case": steel_case, "dusk": dusk, "day": day, "grass": grass, "gingham": gingham,
    "salt": salt, "wood": wood, "tile": tile, "plaster": plaster,
}


def make(name: str, small: bool = False) -> np.ndarray:
    if name not in TEXTURES:
        raise ValueError(f"unknown texture {name!r}; generated textures are {sorted(TEXTURES)}")
    return TEXTURES[name](small=small)


def ensure(names: Iterable[str], folder: str | Path) -> dict[str, Path]:
    """Write each named texture to folder/<name>.png unless it is there already."""
    folder = Path(folder)
    out = {}
    for name in names:
        aim = folder / f"{name}.png"
        if not aim.exists():
            write_png(aim, make(name))
        out[name] = aim
    return out
