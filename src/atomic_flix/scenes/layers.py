"""Turn one frame's multi-layer EXR from Blender into the pass files. Pure numpy; Blender calls it after each frame.

Written per frame N (4 digits):
- depth/N.exr  raw depth in metres, float32, channel "Z"; the sky is far.
- depth/N.png  16-bit inverse depth over the scene's fixed depth_range: near = 65535, far and sky = 0.
- normal/N.png 8-bit viewpoint-space normals mapped from [-1, 1]: x right, y up, z toward the viewer.
- mist/N.png   8-bit mist (0 at the viewpoint, 255 at the mist's full depth).
- mask/<name>/N.png  8-bit, 255 where the named pieces cover at least half the pixel, else 0.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from .imageio import read_exr, write_exr, write_png


def _find(chans: dict[str, np.ndarray], pass_name: str, channel: str) -> np.ndarray:
    for key, plane in chans.items():
        parts = key.split(".")
        if len(parts) >= 2 and parts[-2] == pass_name and parts[-1] == channel:
            return plane
    raise ValueError(f"the capture has no {pass_name}.{channel} channel (has {sorted(chans)})")


def inverse_depth(z: np.ndarray, near: float, far: float) -> np.ndarray:
    """1 at `near` or closer, 0 at `far` or beyond, linear in 1/z between."""
    z = np.maximum(np.asarray(z, np.float64), 1e-9)
    v = (1.0 / z - 1.0 / far) / (1.0 / near - 1.0 / far)
    return np.clip(v, 0.0, 1.0)


def camera_normals(n_world: np.ndarray, cam_rot: Sequence[Sequence[float]]) -> np.ndarray:
    """World normals (HxWx3) into the viewpoint's frame: x right, y up, z toward the viewer.

    cam_rot is the Blender viewpoint-to-world rotation (columns right, up, back), so its transpose maps world to viewpoint.
    """
    r = np.asarray(cam_rot, np.float64)
    return np.einsum("ij,hwi->hwj", r, np.asarray(n_world, np.float64))


def _u8(v: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(v * 255.0), 0, 255).astype(np.uint8)


def split_frame(exr_path: str | Path, write_to: str | Path, frame: int, meta: dict) -> dict[str, Path]:
    """Write the requested layers for one frame; returns {pass key: file}. See the module docstring for files.

    meta: far, depth_range [near, far], cam_rot (3x3), layers (list), masks [{index, name, aov}].
    """
    out = Path(write_to)
    wanted = set(meta["layers"])
    chans = read_exr(exr_path, want=lambda name: not name.split(".")[-2:-1] == ["Combined"])
    tag = f"{frame:04d}"
    written: dict[str, Path] = {}
    if "depth" in wanted:
        z = _find(chans, "Depth", "Z")
        z = np.where(np.isfinite(z) & (z < meta["far"]), z, meta["far"]).astype(np.float32)
        written["depth"] = write_exr(out / "depth" / f"{tag}.exr", {"Z": z})
        near, far = meta["depth_range"]
        written["depth16"] = write_png(out / "depth" / f"{tag}.png",
                                       np.rint(inverse_depth(z, near, far) * 65535).astype(np.uint16))
    if "facing" in wanted:
        n = np.stack([_find(chans, "Normal", c) for c in "XYZ"], axis=-1)
        c = camera_normals(n, meta["cam_rot"])
        written["facing"] = write_png(out / "facing" / f"{tag}.png", _u8((c + 1.0) / 2.0))
    if "mist" in wanted:
        written["mist"] = write_png(out / "mist" / f"{tag}.png", _u8(_find(chans, "Mist", "Z")))
    if "mask" in wanted:
        for m in meta.get("masks", []):
            cover = _find(chans, m["aov"], "X")
            key = f"mask/{m['name']}"
            written[key] = write_png(out / "mask" / m["name"] / f"{tag}.png",
                                     np.where(cover >= 0.5, 255, 0).astype(np.uint8))
    return written
