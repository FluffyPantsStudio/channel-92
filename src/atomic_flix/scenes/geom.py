"""Small rotation helpers in plain Python: quaternions are (w, x, y, z) tuples, matrices are 3x3 nested lists.

Blender runs these too (through the plan), so nothing here needs numpy.
"""

from __future__ import annotations

import math
from typing import Sequence

Vec = Sequence[float]
Quat = tuple[float, float, float, float]
IDENTITY: Quat = (1.0, 0.0, 0.0, 0.0)


def normalise(v: Vec) -> list[float]:
    n = math.sqrt(sum(c * c for c in v))
    if n == 0:
        raise ValueError("cannot normalise a zero vector")
    return [c / n for c in v]


def cross(a: Vec, b: Vec) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def dot(a: Vec, b: Vec) -> float:
    return sum(x * y for x, y in zip(a, b))


def quat_mul(a: Sequence[float], b: Sequence[float]) -> Quat:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def quat_axis_angle(axis: Vec, degrees: float) -> Quat:
    ax = normalise(axis)
    half = math.radians(degrees) / 2
    s = math.sin(half)
    return (math.cos(half), ax[0] * s, ax[1] * s, ax[2] * s)


def quat_yaw(degrees: float) -> Quat:
    """A turn about world +z, counter-clockwise seen from above."""
    return quat_axis_angle((0, 0, 1), degrees)


def spin(q: Sequence[float], v: Vec) -> list[float]:
    m = matrix_from_quat(q)
    return [dot(m[r], v) for r in range(3)]


def matrix_from_quat(q: Sequence[float]) -> list[list[float]]:
    w, x, y, z = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]]


def quat_from_matrix(m: Sequence[Sequence[float]]) -> Quat:
    """Shepperd's method; the result has w >= 0."""
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = (0.25 * s, (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s)
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        q = ((m[2][1] - m[1][2]) / s, 0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s)
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        q = ((m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s)
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
        q = ((m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s)
    n = math.sqrt(sum(c * c for c in q))
    q = tuple(c / n for c in q)
    return q if q[0] >= 0 else tuple(-c for c in q)


def quat_z_to(direction: Vec) -> Quat:
    """The rotation that carries local +z onto `direction` (used to lay a cylinder between two points)."""
    d = normalise(direction)
    c = d[2]
    if c > 1 - 1e-12:
        return IDENTITY
    if c < -1 + 1e-12:
        return (0.0, 1.0, 0.0, 0.0)
    axis = cross((0, 0, 1), d)
    return quat_axis_angle(axis, math.degrees(math.acos(max(-1.0, min(1.0, c)))))


def quat_mirror_y(q: Sequence[float]) -> Quat:
    """Conjugate a rotation by the reflection y -> -y (shapes here are symmetric, so this mirrors the object)."""
    w, x, y, z = q
    return (w, -x, y, -z)
