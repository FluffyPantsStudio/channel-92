"""The pieces library: block.json (data) plus build.py (a builder) per folder, and surfaces.json.

A builder is plain Python, `def build(ctx, settings)`, and makes everything through the BuildContext below: boxes,
cylinders, spheres, limbs between two points, lamps and rigs. The context places what the builder makes in the
world (the instance's position, turn and mirror), so a builder only thinks in its own local frame, and it records
plain dicts, so a whole set compiles and is tested without Blender. Blender later turns each record into an object.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Sequence

from . import geom
from .streams import stream

PARAM_TYPES = {"float", "int", "bool", "str", "span", "vec3", "vec2", "surface"}
MATERIAL_KINDS = {"flat", "image"}
SHAPES = ("box", "tube", "ball")
PIECE_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
PACKAGED_PIECES = Path(__file__).resolve().parent / "pieces"


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _pair(v: Any) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(_is_num(x) for x in v)


class Block:
    def __init__(self, folder: Path, meta: dict, builder) -> None:
        self.folder = folder
        self.meta = meta
        self._builder = builder

    @property
    def name(self) -> str:
        return self.meta["name"]

    def build(self, ctx: "BuildContext", settings: dict) -> None:
        self._builder(ctx, settings)


class Library:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        mats = self.root / "surfaces.json"
        self.surfaces: dict[str, dict] = json.loads(mats.read_text(encoding="utf-8")) if mats.exists() else {}
        self._pieces: dict[str, Block] = {}

    @classmethod
    def shipped(cls) -> "Library":
        """The pieces packaged with the kit. A person's own block folder is a separate Library, made only when they
        name it (`--blocks DIR` on the scenes command line); nothing in a scene or the environment can add one."""
        return cls(PACKAGED_PIECES)

    def block_names(self) -> list[str]:
        return sorted(p.parent.name for p in self.root.glob("*/block.json") if PIECE_NAME.fullmatch(p.parent.name))

    def _piece_folder(self, name: Any) -> Path | None:
        """The block's folder when NAME is a plain block name whose folder (and builder) lie inside the library."""
        if not isinstance(name, str) or not PIECE_NAME.fullmatch(name):
            return None
        root = self.root.resolve()
        folder = (root / name).resolve()
        if folder.parent != root:
            return None
        builder = (folder / "build.py").resolve()
        if builder.exists() and builder.parent != folder:
            return None
        return folder

    def has_block(self, name: str) -> bool:
        folder = self._piece_folder(name)
        return folder is not None and (folder / "block.json").exists()

    def block(self, name: str) -> Block:
        if name in self._pieces:
            return self._pieces[name]
        folder = self._piece_folder(name)
        if folder is None:
            raise ValueError(f"{name!r} is not a block name (lower-case letters, digits and hyphens, a folder directly "
                             f"inside {self.root})")
        if not (folder / "block.json").exists():
            raise ValueError(f"no block named {name!r} in {self.root}")
        meta = json.loads((folder / "block.json").read_text(encoding="utf-8"))
        if meta.get("name") != name:
            raise ValueError(f"{folder / 'block.json'}: its name {meta.get('name')!r} must match the folder {name!r}")
        for pname, spec in meta.get("settings", {}).items():
            if spec.get("type") not in PARAM_TYPES:
                raise ValueError(f"{name}: param {pname} has unknown type {spec.get('type')!r}")
        module_name = f"_flix_block_{name.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, folder / "build.py")
        builder_mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = builder_mod
        spec.loader.exec_module(builder_mod)
        block = Block(folder, meta, builder_mod.build)
        self._pieces[name] = block
        return block

    # ------------------------------------------------------------ params

    def resolve_params(self, name: str, given: dict, seed: int, instance_id: str,
                       surfaces: Sequence[str] | None = None) -> dict:
        """Check the given settings against block.json, fill defaults and make every draw for this instance.

        A float or int given as [a, b] is drawn once per instance from the instance's own stream; a "span" stays a
        pair and the builder draws from it per part. Errors are ValueErrors that start with the param's name.
        """
        spec = self.block(name).meta.get("settings", {})
        known = set(surfaces) if surfaces is not None else set(self.surfaces)
        for key in given:
            if key not in spec:
                raise ValueError(f"{key}: unknown param for block {name!r}; it takes {sorted(spec)}")
        out = {}
        for key, ps in spec.items():
            value = given.get(key, ps.get("fallback"))
            out[key] = self._one(key, ps, value, known, seed, instance_id)
        return out

    @staticmethod
    def _bounds(key: str, ps: dict, values: Sequence[float]) -> None:
        for v in values:
            if "min" in ps and v < ps["min"]:
                raise ValueError(f"{key}: {v} is below the minimum {ps['min']}")
            if "max" in ps and v > ps["max"]:
                raise ValueError(f"{key}: {v} is above the maximum {ps['max']}")

    def _one(self, key: str, ps: dict, value: Any, known: set, seed: int, instance_id: str) -> Any:
        kind = ps["type"]
        if kind in ("float", "int", "span"):
            if _is_num(value):
                lo = hi = value
            elif _pair(value):
                lo, hi = value
                if lo > hi:
                    raise ValueError(f"{key}: range [{lo}, {hi}] runs backwards")
            else:
                raise ValueError(f"{key}: expected a number or a range [a, b], got {value!r}")
            if kind == "int" and not (float(lo).is_integer() and float(hi).is_integer()):
                raise ValueError(f"{key}: expected whole numbers, got {value!r}")
            self._bounds(key, ps, (lo, hi))
            if kind == "span":
                return [float(lo), float(hi)]
            rng = stream(seed, instance_id, "param", key)
            if kind == "int":
                return int(lo) if lo == hi else rng.randint(int(lo), int(hi))
            return float(lo) if lo == hi else rng.uniform(lo, hi)
        if kind == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{key}: expected true or false, got {value!r}")
            return value
        if kind in ("str", "surface"):
            if not isinstance(value, str):
                raise ValueError(f"{key}: expected a name, got {value!r}")
            if kind == "surface" and value not in known:
                raise ValueError(f"{key}: unknown surface {value!r}")
            if "choices" in ps and value not in ps["choices"]:
                raise ValueError(f"{key}: {value!r} is not one of {ps['choices']}")
            return value
        size = 3 if kind == "vec3" else 2
        if not (isinstance(value, list) and len(value) == size and all(_is_num(v) for v in value)):
            raise ValueError(f"{key}: expected {size} numbers, got {value!r}")
        self._bounds(key, ps, value)
        return [float(v) for v in value]


class BuildContext:
    """What a builder draws with. Positions and rotations are local to the instance; records come out in world."""

    def __init__(self, library: Library, instance_id: str, kind: str, seed: int, frames: int, fps: float,
                 at: Sequence[float] = (0.0, 0.0, 0.0), turn: float = 0.0, twin_across: bool = False,
                 mask: int = 0, surfaces: Sequence[str] | None = None, draw_id: str | None = None) -> None:
        self.library = library
        self.known_materials = set(surfaces) if surfaces is not None else set(library.surfaces)
        self.instance_id = instance_id
        self.kind = kind
        self.seed = seed
        self.frames = frames
        self.fps = fps
        # an exact mirrored twin draws from its original's stream, so it repeats the original's layout
        self.rng = stream(seed, draw_id or instance_id, "build")
        self._at = [float(c) for c in at]
        self._turn = float(turn)
        self._mirror = bool(twin_across)
        self._q_turn = geom.quat_yaw(self._turn)
        self.mask = mask
        self.prims: list[dict] = []
        self.lamps: list[dict] = []
        self.rigs: list[dict] = []

    # ------------------------------------------------------------ placement

    def to_world(self, p: Sequence[float]) -> list[float]:
        local = [p[0], -p[1] if self._mirror else p[1], p[2]]
        r = geom.spin(self._q_turn, local)
        return [a + b for a, b in zip(r, self._at)]

    def to_local(self, p: Sequence[float]) -> list[float]:
        d = [a - b for a, b in zip(p, self._at)]
        w, x, y, z = self._q_turn
        r = geom.spin((w, -x, -y, -z), d)
        return [r[0], -r[1] if self._mirror else r[1], r[2]]

    def _world_quat(self, q: Sequence[float]) -> list[float]:
        q = geom.quat_mirror_y(q) if self._mirror else tuple(q)
        return list(geom.quat_mul(self._q_turn, q))

    # ------------------------------------------------------------ shapes

    def _prim(self, shape: str, pos, scale, surface: str, name: str | None, quat, keys, extra: dict) -> dict:
        if surface not in self.known_materials:
            raise ValueError(f"block {self.kind!r} uses unknown surface {surface!r}")
        q = list(quat) if quat is not None else list(geom.IDENTITY)
        rec = {"op": "prim", "shape": shape, "name": name or shape, "block": self.instance_id, "kind": self.kind,
               "mask": self.mask, "pos": self.to_world(pos), "scale": [float(s) for s in scale],
               "quat": self._world_quat(q), "surface": surface, **extra}
        if keys is not None:
            if len(keys) != self.frames:
                raise ValueError(f"{self.kind}: {len(keys)} animation keys for {self.frames} frames")
            rec["keys"] = [[self.to_world(p), self._world_quat(kq)] for p, kq in keys]
            rec["pos"], rec["quat"] = rec["keys"][0]
        self.prims.append(rec)
        return rec

    def box(self, pos, size, surface: str, name: str | None = None, yaw: float = 0.0, quat=None, keys=None) -> dict:
        q = quat if quat is not None else geom.quat_yaw(yaw)
        return self._prim("box", pos, size, surface, name, q, keys, {})

    def tube(self, pos, radius: float, height: float, surface: str, name: str | None = None, quat=None,
                 sides: int = 24, keys=None) -> dict:
        return self._prim("tube", pos, (2 * radius, 2 * radius, height), surface, name, quat, keys,
                          {"sides": sides})

    def ball(self, pos, size, surface: str, name: str | None = None, quat=None, sides: int = 32,
               rings: int = 16, keys=None) -> dict:
        extents = (2 * size,) * 3 if _is_num(size) else size
        return self._prim("ball", pos, extents, surface, name, quat, keys, {"sides": sides, "rings": rings})

    def limb(self, a, b, radius: float, surface: str, name: str | None = None, sides: int = 16,
             keys=None) -> dict:
        """A cylinder from point a to point b. With keys (per frame (a, b) pairs) it follows them; its length is
        the first frame's."""
        d = [y - x for x, y in zip(a, b)]
        extent = math.sqrt(geom.dot(d, d))
        centre = [(x + y) / 2 for x, y in zip(a, b)]
        limb_keys = None
        if keys is not None:
            limb_keys = [([(x + y) / 2 for x, y in zip(ka, kb)], geom.quat_z_to([y - x for x, y in zip(ka, kb)]))
                         for ka, kb in keys]
        return self._prim("tube", centre, (2 * radius, 2 * radius, extent), surface, name,
                          geom.quat_z_to(d), limb_keys, {"sides": sides})

    def light(self, kind: str, pos, power: float, color=(1.0, 1.0, 1.0), radius: float = 0.1,
              name: str | None = None) -> dict:
        rec = {"op": "light", "kind": kind, "name": name or f"{self.instance_id}-light{len(self.lamps)}",
               "block": self.instance_id, "pos": self.to_world(pos), "power": float(power),
               "color": [float(c) for c in color], "radius": float(radius)}
        self.lamps.append(rec)
        return rec

    def rig(self, frames: list[dict]) -> dict:
        """Named body points per frame (local), kept for pose guides."""
        rec = {"op": "rig", "block": self.instance_id, "kind": self.kind,
               "frames": [{k: self.to_world(v) for k, v in fr.items()} for fr in frames]}
        self.rigs.append(rec)
        return rec
