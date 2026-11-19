"""Camera paths: presets or keys, eased, turned into one viewpoint pose per frame, plus the viewpoint.json maths.

World: metres, z up. A heading (yaw) of 0 looks down +x and 90 looks down +y; pitch is up; roll turns the picture
clockwise. Blender's viewpoint looks down its local -z with +y up, so its world rotation has the columns
[right, up, -forward]. viewpoint.json uses the OpenCV viewpoint instead: x right, y down, z forward.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

from . import geom
from .streams import stream


def _smoothstep(t: float) -> float:
    return t * t * (3 - 2 * t)


EASES: dict[str, Callable[[float], float]] = {
    "even": lambda t: t,
    "eased": _smoothstep,
    # the push in lab/blender/street.py: a little ease at both ends, mostly steady
    "eased35": lambda t: _smoothstep(t) * 0.35 + t * 0.65,
    "in": lambda t: t * t,
    "out": lambda t: 1 - (1 - t) * (1 - t),
}
PRESETS = ("still", "push", "pull", "truck", "crane", "orbit", "handheld")


def ease(name: str, t: float) -> float:
    if name not in EASES:
        raise ValueError(f"unknown ease {name!r}; use one of {sorted(EASES)}")
    t = min(1.0, max(0.0, t))
    return EASES[name](t)


def heading(yaw: float, pitch: float) -> list[float]:
    y, p = math.radians(yaw), math.radians(pitch)
    return [math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)]


def look_rotation(forward: Sequence[float], roll: float = 0.0) -> list[list[float]]:
    """Blender viewpoint-to-world rotation for a viewpoint looking along `forward` with world z up."""
    f = geom.normalise(forward)
    side = geom.cross(f, (0, 0, 1))
    if math.sqrt(geom.dot(side, side)) < 1e-9:
        # looking straight up or down: keep the heading's sideways axis
        side = [0.0, -1.0, 0.0]
    right = geom.normalise(side)
    up = geom.cross(right, f)
    r = math.radians(roll)
    right, up = ([math.cos(r) * a + math.sin(r) * b for a, b in zip(right, up)],
                 [math.cos(r) * b - math.sin(r) * a for a, b in zip(right, up)])
    back = [-c for c in f]
    return [[right[i], up[i], back[i]] for i in range(3)]


def yaw_pitch_rotation(yaw: float, pitch: float, roll: float = 0.0) -> list[list[float]]:
    return look_rotation(heading(yaw, pitch), roll)


# ---------------------------------------------------------------- presets

def _lerp(a: Sequence[float], b: Sequence[float], t: float) -> list[float]:
    return [x + (y - x) * t for x, y in zip(a, b)]


def _aim(spec: dict) -> tuple[float, float, float]:
    return float(spec.get("yaw", 0.0)), float(spec.get("pitch", 0.0)), float(spec.get("roll", 0.0))


def _straight_target(spec: dict) -> list[float]:
    start = list(spec["from"])
    if "to" in spec:
        return list(spec["to"])
    dist = float(spec.get("distance", 0.0))
    yaw, _, _ = _aim(spec)
    flat = heading(yaw, 0.0)
    direction = {
        "push": flat,
        "pull": [-c for c in flat],
        "truck": [flat[1], -flat[0], 0.0],   # the camera's right
        "crane": [0.0, 0.0, 1.0],
    }[spec["move"]]
    return [s + d * dist for s, d in zip(start, direction)]


def _preset_pose(spec: dict, t: float) -> tuple[list[float], list[list[float]]]:
    kind = spec["move"]
    yaw, pitch, roll = _aim(spec)
    if kind in ("still", "handheld"):
        return list(spec.get("pos", (0, 0, 1.6))), yaw_pitch_rotation(yaw, pitch, roll)
    if kind in ("push", "pull", "truck", "crane"):
        e = ease(spec.get("ease", "eased"), t)
        pos = _lerp(spec["from"], _straight_target(spec), e)
        return pos, yaw_pitch_rotation(yaw, pitch, roll)
    if kind == "orbit":
        e = ease(spec.get("ease", "eased"), t)
        cx, cy, cz = spec.get("center", (0, 0, 1))
        radius = float(spec.get("radius", 5.0))
        angle = math.radians(float(spec.get("start", 0.0)) + (float(spec.get("end", 90.0)) - float(spec.get("start", 0.0))) * e)
        pos = [cx + radius * math.cos(angle), cy + radius * math.sin(angle), float(spec.get("height", cz))]
        look = spec.get("look", (cx, cy, cz))
        return pos, look_rotation([a - b for a, b in zip(look, pos)], roll)
    raise ValueError(f"unknown viewpoint move {kind!r}; use one of {list(PRESETS)}")


# ---------------------------------------------------------------- keys

def _key_rotation(key: dict) -> list[list[float]] | None:
    if "look" in key:
        return look_rotation([a - b for a, b in zip(key["look"], key["pos"])], float(key.get("roll", 0.0)))
    if any(k in key for k in ("yaw", "pitch", "roll")):
        return yaw_pitch_rotation(float(key.get("yaw", 0.0)), float(key.get("pitch", 0.0)), float(key.get("roll", 0.0)))
    return None


def _slerp(qa: Sequence[float], qb: Sequence[float], t: float) -> tuple[float, ...]:
    d = geom.dot(qa, qb)
    if d < 0:
        qb, d = [-c for c in qb], -d
    if d > 0.9995:
        q = _lerp(qa, qb, t)
    else:
        theta = math.acos(d)
        sa, sb = math.sin((1 - t) * theta), math.sin(t * theta)
        q = [(a * sa + b * sb) / math.sin(theta) for a, b in zip(qa, qb)]
    n = math.sqrt(geom.dot(q, q))
    return tuple(c / n for c in q)


def _keys_pose(keys: list[dict], f: int, default_ease: str, lens: float):
    rots = []
    last = yaw_pitch_rotation(0, 0, 0)
    for k in keys:
        r = _key_rotation(k)
        last = r if r is not None else last
        rots.append(last)
    lenses = [float(k.get("lens", lens)) for k in keys]
    if f <= keys[0]["f"]:
        return list(keys[0]["pos"]), rots[0], lenses[0]
    if f >= keys[-1]["f"]:
        return list(keys[-1]["pos"]), rots[-1], lenses[-1]
    for i in range(len(keys) - 1):
        a, b = keys[i], keys[i + 1]
        if a["f"] <= f <= b["f"]:
            name = b.get("ease", a.get("ease", default_ease))
            e = ease(name, (f - a["f"]) / (b["f"] - a["f"]))
            q = _slerp(geom.quat_from_matrix(rots[i]), geom.quat_from_matrix(rots[i + 1]), e)
            return _lerp(a["pos"], b["pos"], e), geom.matrix_from_quat(q), lenses[i] + (lenses[i + 1] - lenses[i]) * e
    raise AssertionError("unreachable")


# ---------------------------------------------------------------- shake

def _shake(spec: dict, frames: int, fps: float, seed: int):
    """Seeded low-frequency wobble: a few slow sines per axis, bounded by the amplitudes."""
    amp_m = float(spec.get("amp_cm", 1.5)) / 100.0
    amp_deg = float(spec.get("amp_deg", 0.4))
    hz = float(spec.get("hz", 0.35))
    rng = stream(seed, "viewpoint", "shake")
    waves = [[(rng.uniform(0.6, 1.4) * hz, rng.uniform(0, 2 * math.pi), rng.uniform(0.3, 1.0)) for _ in range(3)]
             for _ in range(6)]

    def axis(i: int, t: float) -> float:
        total = sum(w for _, _, w in waves[i])
        return sum(w * math.sin(2 * math.pi * f * t + p) for f, p, w in waves[i]) / total

    out = []
    for n in range(frames):
        t = n / fps
        out.append(([amp_m * axis(i, t) for i in range(3)], [amp_deg * axis(3 + i, t) for i in range(3)]))
    return out


def _apply_shake(pos, rot, offset, angles):
    pos = [p + o for p, o in zip(pos, offset)]
    q = geom.quat_from_matrix(rot)
    for axis, deg in zip(([0, 0, 1], [rot[0][0], rot[1][0], rot[2][0]], [-rot[0][2], -rot[1][2], -rot[2][2]]), angles):
        q = geom.quat_mul(geom.quat_axis_angle(axis, deg), q)
    return pos, geom.matrix_from_quat(q)


# ---------------------------------------------------------------- frames

def viewpoint_frames(viewpoint: dict, frames: int, seed: int, fps: float = 24.0) -> list[dict]:
    """One pose per frame: {"f", "pos", "rot" (Blender viewpoint-to-world 3x3), "lens"}. Frames count from 1."""
    spec = viewpoint["path"]
    lens = float(viewpoint.get("lens", 32.0))
    out = []
    shake_spec = spec.get("shake")
    if spec.get("move") == "handheld":
        shake_spec = {**spec, **(shake_spec or {})}
    wobble = _shake(shake_spec, frames, fps, seed) if shake_spec else None
    for i in range(frames):
        f = i + 1
        t = i / (frames - 1) if frames > 1 else 0.0
        if "keys" in spec:
            pos, rot, flen = _keys_pose(spec["keys"], f, spec.get("ease", "eased"), lens)
        else:
            if "move" not in spec:
                raise ValueError("a viewpoint path needs a move or keys")
            pos, rot = _preset_pose(spec, t)
            flen = lens
        if wobble:
            pos, rot = _apply_shake(pos, rot, *wobble[i])
        out.append({"f": f, "pos": [float(c) for c in pos], "rot": [list(map(float, r)) for r in rot],
                    "lens": float(flen)})
    return out


def intrinsics(lens: float, film_mm: float, w: int, h: int) -> list[list[float]]:
    """Pixel intrinsics with the film_mm fitted to the width; pixels are square and (0, 0) is the top-left corner."""
    fx = lens / film_mm * w
    return [[fx, 0.0, w / 2], [0.0, fx, h / 2], [0.0, 0.0, 1.0]]


def to_view(rot: Sequence[Sequence[float]], pos: Sequence[float]) -> list[list[float]]:
    """4x4 OpenCV world-to-viewpoint matrix from a Blender viewpoint-to-world rotation and a position."""
    right = [rot[i][0] for i in range(3)]
    up = [rot[i][1] for i in range(3)]
    forward = [-rot[i][2] for i in range(3)]
    rows = [right, [-c for c in up], forward]
    t = [-geom.dot(r, pos) for r in rows]
    return [rows[0] + [t[0]], rows[1] + [t[1]], rows[2] + [t[2]], [0.0, 0.0, 0.0, 1.0]]


def camera_record(frame: dict, w: int, h: int, film_mm: float) -> dict:
    lens = frame["lens"]
    return {
        "f": frame["f"],
        "pos": frame["pos"],
        "quat_wxyz": list(geom.quat_from_matrix(frame["rot"])),
        "lens_mm": lens,
        "fov_x_deg": math.degrees(2 * math.atan(film_mm / 2 / lens)),
        "K": intrinsics(lens, film_mm, w, h),
        "to_view": to_view(frame["rot"], frame["pos"]),
    }


def to_screen(record: dict, point: Sequence[float]) -> list[float] | None:
    """World point to pixel (u, v) with a viewpoint.json record; None when it is behind the viewpoint."""
    m = record["to_view"]
    x, y, z = (geom.dot(m[r][:3], point) + m[r][3] for r in range(3))
    if z <= 1e-6:
        return None
    k = record["K"]
    return [k[0][0] * x / z + k[0][2], k[1][1] * y / z + k[1][2]]
