"""Checking a scene description (`"format": "atomic-flix/scene@1"`) and filling its defaults.

Every problem is a SceneError whose message starts with the dotted path of the field (`pieces[2].settings.height`).
Unknown keys are errors. The input dict is never changed; check_scene returns a new, fully resolved one.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

from .library import MATERIAL_KINDS, PIECE_NAME, Library
from .path import EASES, PRESETS
from ..formats import tag

FORMAT = tag("scene")
LAYERS = ("shaded", "depth", "facing", "mist", "mask")
ENGINES = ("raster", "pathtrace")
DEVICES = ("gpu", "cpu")
VIEWS = ("Standard", "AgX", "Filmic", "Khronos PBR Neutral")
LIGHT_KINDS = ("sun", "point", "area")


class SceneError(ValueError):
    pass


def load_scene(path: str | Path) -> dict:
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise SceneError(f"{path}: cannot read the scene ({err})") from err


# ---------------------------------------------------------------- small checks

def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _keys(where: str, node: Any, allowed: set[str], required: set[str] = frozenset()) -> dict:
    if not isinstance(node, dict):
        raise SceneError(f"{where}: expected an object, got {type(node).__name__}")
    for k in node:
        if k not in allowed:
            label = f"{where}.{k}" if where else k
            raise SceneError(f"{label}: unknown key (allowed: {', '.join(sorted(allowed))})")
    missing = sorted(k for k in required if k not in node)
    if missing:
        prefix = f"{where}." if where else ""
        raise SceneError(", ".join(prefix + k for k in missing) + ": required")
    return node


def _number(where: str, v: Any, lo: float | None = None, hi: float | None = None, above: float | None = None) -> float:
    if not _num(v):
        raise SceneError(f"{where}: expected a number, got {v!r}")
    if lo is not None and v < lo:
        raise SceneError(f"{where}: {v} is below {lo}")
    if hi is not None and v > hi:
        raise SceneError(f"{where}: {v} is above {hi}")
    if above is not None and v <= above:
        raise SceneError(f"{where}: must be above {above}, got {v}")
    return float(v)


def _integer(where: str, v: Any, lo: int) -> int:
    if not (_num(v) and float(v).is_integer()):
        raise SceneError(f"{where}: expected a whole number, got {v!r}")
    if v < lo:
        raise SceneError(f"{where}: {v} is below {lo}")
    return int(v)


def _vec(where: str, v: Any, n: int = 3, lo: float | None = None) -> list[float]:
    if not (isinstance(v, list) and len(v) == n and all(_num(x) for x in v)):
        raise SceneError(f"{where}: expected {n} numbers, got {v!r}")
    if lo is not None and any(x < lo for x in v):
        raise SceneError(f"{where}: values must be at least {lo}")
    return [float(x) for x in v]


def _choice(where: str, v: Any, options) -> str:
    if v not in options:
        raise SceneError(f"{where}: {v!r} is not one of {', '.join(map(str, options))}")
    return v


def _range_or_number(where: str, v: Any, lo: float | None = None) -> list[float]:
    if _num(v):
        return [float(v), float(v)]
    if isinstance(v, list) and len(v) == 2 and all(_num(x) for x in v):
        if v[0] > v[1]:
            raise SceneError(f"{where}: range [{v[0]}, {v[1]}] runs backwards")
        if lo is not None and v[0] < lo:
            raise SceneError(f"{where}: values must be at least {lo}")
        return [float(v[0]), float(v[1])]
    raise SceneError(f"{where}: expected a number or a range [a, b], got {v!r}")


# ---------------------------------------------------------------- sections

def _size(node: Any) -> dict:
    _keys("size", node, {"w", "h", "fps", "frames"}, {"w", "h"})
    return {"w": _integer("size.w", node["w"], 8), "h": _integer("size.h", node["h"], 8),
            "fps": _number("size.fps", node.get("fps", 24), above=0),
            "frames": _integer("size.frames", node.get("frames", 1), 1)}


def _world(node: Any) -> dict:
    _keys("world", node, {"sky", "mist"})
    out: dict = {}
    sky = _keys("world.sky", node.get("sky", {"color": [0.05, 0.05, 0.06]}), {"image", "color", "spin", "brightness"})
    if ("image" in sky) == ("color" in sky):
        raise SceneError("world.sky: give exactly one of image or color")
    spin = _number("world.sky.rotate", sky.get("spin", 0.0))
    if "image" in sky:
        if not isinstance(sky["image"], str) or not sky["image"]:
            raise SceneError("world.sky.image: expected a file path or gen:<name>")
        out["sky"] = {"image": sky["image"], "spin": spin}
    else:
        out["sky"] = {"color": _vec("world.sky.color", sky["color"], lo=0)}
    out["sky"]["brightness"] = _number("world.sky.brightness", sky.get("brightness", 1.0), lo=0)
    if "mist" in node:
        mist = _keys("world.mist", node["mist"], {"start", "depth"})
        out["mist"] = {"start": _number("world.mist.start", mist.get("start", 5.0), lo=0),
                       "depth": _number("world.mist.depth", mist.get("depth", 400.0), above=0)}
    else:
        out["mist"] = {"start": 5.0, "depth": 400.0}
    return out


def _light(i: int, node: Any) -> dict:
    w = f"lamps[{i}]"
    _keys(w, node, {"kind", "name", "color", "power", "pitch", "yaw", "soft", "pos", "radius", "size"}, {"kind"})
    kind = _choice(f"{w}.kind", node["kind"], LIGHT_KINDS)
    out = {"kind": kind, "name": str(node.get("name", f"light{i}")),
           "color": _vec(f"{w}.color", node.get("color", [1.0, 1.0, 1.0]), lo=0),
           "power": _number(f"{w}.power", node.get("power", 3.0 if kind == "sun" else 100.0), lo=0)}
    if kind in ("sun", "area"):
        out["pitch"] = _number(f"{w}.pitch", node.get("pitch", -45.0), -90, 90)
        out["yaw"] = _number(f"{w}.yaw", node.get("yaw", 0.0))
    if kind == "sun":
        out["soft"] = _number(f"{w}.soft", node.get("soft", 3.0), 0, 180)
    else:
        out["pos"] = _vec(f"{w}.pos", node.get("pos", [0.0, 0.0, 3.0]))
        out["radius"] = _number(f"{w}.radius", node.get("radius", 0.1), lo=0)
        if kind == "area":
            out["size"] = _number(f"{w}.size", node.get("size", 1.0), above=0)
    return out


def _surface(name: str, node: Any) -> dict:
    w = f"surfaces.{name}"
    _keys(w, node, {"kind", "color", "srgb", "gain", "rough", "metal", "specular", "emit", "image", "scale", "blend"},
          {"kind"})
    kind = _choice(f"{w}.kind", node["kind"], sorted(MATERIAL_KINDS))
    out = {"kind": kind}
    if kind == "flat":
        if ("color" in node) == ("srgb" in node):
            raise SceneError(f"{w}: give exactly one of color (linear) or srgb")
        key = "color" if "color" in node else "srgb"
        out[key] = _vec(f"{w}.{key}", node[key], lo=0)
    else:
        if not isinstance(node.get("image"), str):
            raise SceneError(f"{w}.image: required for an image surface")
        out["image"] = node["image"]
        out["scale"] = _vec(f"{w}.scale", node.get("scale", [1.0, 1.0, 1.0]))
        out["blend"] = _number(f"{w}.blend", node.get("blend", 0.0), 0, 1)
    for key, fallback, lo, hi in (("gain", 1.0, 0, None), ("rough", 0.5, 0, 1), ("metal", 0.0, 0, 1),
                                 ("specular", 0.5, 0, 1), ("emit", 0.0, 0, None)):
        if key in node:
            out[key] = _number(f"{w}.{key}", node[key], lo, hi)
    return out


def _strew(w: str, node: Any) -> dict:
    _keys(w, node, {"along", "from", "to", "step", "nudge", "across", "flip"}, {"along", "from", "to", "step"})
    out = {"along": _choice(f"{w}.along", node["along"], ("x", "y")),
           "from": _number(f"{w}.from", node["from"]), "to": _number(f"{w}.to", node["to"]),
           "step": _number(f"{w}.step", node["step"], above=0),
           "nudge": _number(f"{w}.nudge", node.get("nudge", 0.0), lo=0),
           "across": _range_or_number(f"{w}.across", node.get("across", 0.0)),
           "flip": _choice(f"{w}.flip", node.get("flip", "none"), ("none", "alternate"))}
    if out["to"] < out["from"]:
        raise SceneError(f"{w}.to: must not be below from")
    return out


def _block(i: int, node: Any, library: Library) -> dict:
    w = f"pieces[{i}]"
    _keys(w, node, {"use", "id", "at", "turn", "twin_across", "settings", "strew"}, {"use"})
    use = node["use"]
    if not isinstance(use, str) or not PIECE_NAME.fullmatch(use):
        raise SceneError(f"{w}.use: {use!r} is not a block name (lower-case letters, digits and hyphens, no paths)")
    if not library.has_block(use):
        raise SceneError(f"{w}.use: unknown block {use!r}; the library has {', '.join(library.block_names())}")
    mirror = node.get("twin_across", False)
    if mirror not in (True, False, "redraw"):
        raise SceneError(f"{w}.twin_across: expected true, false or \"redraw\", got {mirror!r}")
    out = {"use": use, "at": _vec(f"{w}.at", node.get("at", [0.0, 0.0, 0.0])),
           "turn": _number(f"{w}.turn", node.get("turn", 0.0)), "twin_across": mirror,
           "settings": node.get("settings", {})}
    if "id" in node:
        if not isinstance(node["id"], str) or not node["id"] or any(c in node["id"] for c in "/~"):
            raise SceneError(f"{w}.id: expected a name without / or ~")
        out["id"] = node["id"]
    if not isinstance(out["settings"], dict):
        raise SceneError(f"{w}.settings: expected an object")
    if "strew" in node:
        out["strew"] = _strew(f"{w}.strew", node["strew"])
    return out


def _path(node: Any, frames: int) -> dict:
    w = "viewpoint.path"
    keys_allowed = {"move", "keys", "from", "to", "distance", "pos", "pitch", "yaw", "roll", "ease", "center",
                    "radius", "height", "start", "end", "look", "shake", "amp_cm", "amp_deg", "hz"}
    _keys(w, node, keys_allowed)
    if ("move" in node) == ("keys" in node):
        raise SceneError(f"{w}: give exactly one of move or keys")
    out = copy.deepcopy(node)
    if "ease" in node:
        _choice(f"{w}.ease", node["ease"], sorted(EASES))
    for key in ("from", "to", "pos", "center", "look"):
        if key in node:
            _vec(f"{w}.{key}", node[key])
    for key in ("pitch", "yaw", "roll", "distance", "radius", "height", "start", "end"):
        if key in node:
            _number(f"{w}.{key}", node[key])
    if "shake" in node:
        _keys(f"{w}.shake", node["shake"], {"amp_cm", "amp_deg", "hz"})
    if "move" in node:
        move = _choice(f"{w}.move", node["move"], PRESETS)
        if move in ("push", "pull", "truck", "crane"):
            if "from" not in node:
                raise SceneError(f"{w}.from: required for {move}")
            if "to" not in node and "distance" not in node:
                raise SceneError(f"{w}: {move} needs to or distance")
        return out
    keys = node["keys"]
    if not isinstance(keys, list) or not keys:
        raise SceneError(f"{w}.keys: expected a list of keys")
    last = 0
    for i, key in enumerate(keys):
        kw = f"{w}.keys[{i}]"
        _keys(kw, key, {"f", "pos", "look", "pitch", "yaw", "roll", "lens", "ease"}, {"f", "pos"})
        f = _integer(f"{kw}.f", key["f"], 1)
        if f > frames:
            raise SceneError(f"{kw}.f: frame {f} is past the last frame {frames}")
        if f <= last:
            raise SceneError(f"{w}.keys: frames must rise ({f} after {last})")
        last = f
        _vec(f"{kw}.pos", key["pos"])
        if "look" in key:
            _vec(f"{kw}.look", key["look"])
        if "lens" in key:
            _number(f"{kw}.lens", key["lens"], above=0)
        if "ease" in key:
            _choice(f"{kw}.ease", key["ease"], sorted(EASES))
    return out


def _viewpoint(node: Any, frames: int) -> dict:
    _keys("viewpoint", node, {"lens", "film_mm", "near", "far", "path"}, {"path"})
    out = {"lens": _number("viewpoint.lens", node.get("lens", 32.0), above=0),
           "film_mm": _number("viewpoint.film_mm", node.get("film_mm", 36.0), above=0),
           "near": _number("viewpoint.near", node.get("near", 0.1), above=0)}
    out["far"] = _number("viewpoint.far", node.get("far", 1000.0), above=out["near"])
    out["path"] = _path(node["path"], frames)
    return out


def _capture(node: Any, frames: int, mask_names: set[str], far: float) -> dict:
    _keys("capture", node, {"renderer", "spp", "view", "layers", "masks", "device", "frames", "step", "depth_range"})
    renderer = _choice("capture.renderer", node.get("renderer", "raster"), ENGINES)
    out = {"renderer": renderer,
           "spp": _integer("capture.spp", node.get("spp", 64), 1),
           "view": _choice("capture.view", node.get("view", "Standard"), VIEWS),
           "device": _choice("capture.device", node.get("device", "gpu"), DEVICES),
           "step": _integer("capture.step", node.get("step", 1), 1)}
    layers = node.get("layers", list(LAYERS))
    if not isinstance(layers, list) or "shaded" not in layers:
        raise SceneError("capture.layers: a list that includes shaded")
    for p in layers:
        _choice("capture.layers", p, LAYERS)
    out["layers"] = list(layers)
    masks = node.get("masks", [])
    if not isinstance(masks, list):
        raise SceneError("capture.masks: expected a list of block ids or block kinds")
    for m in masks:
        if m not in mask_names:
            raise SceneError(f"capture.masks: {m!r} names no block id or block kind in this scene")
    out["masks"] = list(masks)
    rng = node.get("frames", [1, frames])
    a, b = _range_or_number("capture.frames", rng)
    if not (1 <= a <= b <= frames) or not (float(a).is_integer() and float(b).is_integer()):
        raise SceneError(f"capture.frames: [{a}, {b}] must be whole frames within 1..{frames}")
    out["frames"] = [int(a), int(b)]
    near, far = _range_or_number("capture.depth_range", node.get("depth_range", [0.5, far]))
    if near <= 0 or far <= near:
        raise SceneError("capture.depth_range: needs 0 < near < far")
    out["depth_range"] = [near, far]
    return out


def auto_ids(pieces: list[dict]) -> list[str]:
    """Block ids: the given id, else the block kind, numbered from the second unnamed one of a kind."""
    seen: dict[str, int] = {}
    ids = []
    for b in pieces:
        if "id" in b:
            ids.append(b["id"])
            continue
        n = seen.get(b["use"], 0) + 1
        seen[b["use"]] = n
        ids.append(b["use"] if n == 1 else f"{b['use']}-{n}")
    return ids


def check_scene(scene: Any, library: Library | None = None) -> dict:
    library = library or Library.shipped()
    _keys("", scene, {"format", "name", "seed", "size", "world", "lamps", "pieces", "surfaces", "viewpoint", "capture"},
          {"format", "name", "size", "viewpoint"})
    if scene["format"] != FORMAT:
        raise SceneError(f"format: expected {FORMAT!r}, got {scene['format']!r}")
    if not isinstance(scene["name"], str) or not scene["name"]:
        raise SceneError("name: expected a non-empty name")
    size = _size(scene["size"])
    out = {"format": FORMAT, "name": scene["name"], "seed": _integer("seed", scene.get("seed", 1), 0), "size": size,
           "world": _world(scene.get("world", {}))}
    mats = copy.deepcopy(library.surfaces)
    extra = scene.get("surfaces", {})
    if not isinstance(extra, dict):
        raise SceneError("surfaces: expected an object of name -> surface")
    for name, node in extra.items():
        mats[name] = _surface(name, node)
    out["surfaces"] = mats
    lamps = scene.get("lamps", [])
    if not isinstance(lamps, list):
        raise SceneError("lamps: expected a list")
    out["lamps"] = [_light(i, node) for i, node in enumerate(lamps)]
    pieces = scene.get("pieces", [])
    if not isinstance(pieces, list):
        raise SceneError("pieces: expected a list")
    out["pieces"] = [_block(i, node, library) for i, node in enumerate(pieces)]
    ids = auto_ids(out["pieces"])
    for i, (b, block_id) in enumerate(zip(out["pieces"], ids)):
        if ids.count(block_id) > 1:
            raise SceneError(f"pieces[{i}].id: {block_id!r} is used by more than one block")
        b["id"] = block_id
        try:
            library.resolve_params(b["use"], b["settings"], seed=out["seed"], instance_id=block_id, surfaces=mats)
        except ValueError as err:
            raise SceneError(f"pieces[{i}].settings.{err}") from err
    out["viewpoint"] = _viewpoint(scene["viewpoint"], size["frames"])
    names = set(ids) | {b["use"] for b in out["pieces"]}
    out["capture"] = _capture(scene.get("capture", {}), size["frames"], names, out["viewpoint"]["far"])
    return out
