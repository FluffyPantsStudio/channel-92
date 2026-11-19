"""Compile a scene description into the flat op list that the Blender executor runs, and write the job folder.

Op order is fixed: reset, settings, world, surface..., prim..., rig..., light..., viewpoint, layers, renderer, capture.
Every random value is resolved here, so a plan is the whole truth about a capture and is tested without Blender.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Sequence

from . import geom
from . import path as camera_path
from .library import BuildContext, Library
from .schema import check_scene, load_scene
from .streams import stream
from ..formats import tag

PLAN_FORMAT = tag("scene-plan")
JOB_FORMAT = tag("scene-job")
PREVIEW_STEP = 4
PREVIEW_SAMPLES = 16
DIGITS = 6
# Blender's per-frame EXR is read back and deleted: uncompressed measured 0.55 s of pass writing per 1920x1056 frame
# against 0.67 s with ZIP. Kept files (--keep-exr) are always ZIP.
EXR_CODEC = "NONE"


def _round(value: Any) -> Any:
    if isinstance(value, float):
        r = round(value, DIGITS)
        return 0.0 if r == 0 else r
    if isinstance(value, list):
        return [_round(v) for v in value]
    if isinstance(value, tuple):
        return [_round(v) for v in value]
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    return value


def apply_overrides(scene: dict, renderer: str | None = None, frames: Sequence[int] | None = None,
                    quick: bool = False, samples: int | None = None, size: Sequence[int] | None = None) -> dict:
    """A copy of the scene with command-line choices applied. Preview: half size, 16 samples, every 4th frame."""
    s = copy.deepcopy(scene)
    capture = s.setdefault("capture", {})
    if renderer:
        capture["renderer"] = renderer
    if frames:
        capture["frames"] = [int(frames[0]), int(frames[1])]
    if quick:
        w, h = s["size"]["w"], s["size"]["h"]
        s["size"]["w"], s["size"]["h"] = (w // 2) // 2 * 2, (h // 2) // 2 * 2
        capture["spp"] = PREVIEW_SAMPLES
        capture["step"] = PREVIEW_STEP
    if size:
        s["size"]["w"], s["size"]["h"] = int(size[0]), int(size[1])
    if samples:
        capture["spp"] = int(samples)
    return s


# ---------------------------------------------------------------- instances

def expand_instances(resolved: dict) -> list[dict]:
    """Each block entry becomes one or more instances: strew copies first, then a mirrored twin of each."""
    seed = resolved["seed"]
    out = []
    for b in resolved["pieces"]:
        base = b["id"]
        placed = []
        if "strew" in b:
            sc = b["strew"]
            k, v = 0, sc["from"]
            while v < sc["to"] - 1e-9:
                inst_id = f"{base}/{k}"
                rng = stream(seed, inst_id, "strew")
                along = v + (rng.uniform(-sc["nudge"], sc["nudge"]) if sc["nudge"] else 0.0)
                lo, hi = sc["across"]
                across = rng.uniform(lo, hi) if hi > lo else lo
                if sc["flip"] == "alternate" and k % 2 == 0:
                    across = -across
                offset = [along, across, 0.0] if sc["along"] == "x" else [across, along, 0.0]
                placed.append((inst_id, [a + o for a, o in zip(b["at"], offset)]))
                k += 1
                v = sc["from"] + k * sc["step"]
        else:
            placed.append((base, list(b["at"])))
        for inst_id, at in placed:
            common = {"use": b["use"], "parent": base, "settings": b["settings"]}
            out.append({"id": inst_id, "draw": inst_id, "at": at, "turn": b["turn"], "twin_across": False, **common})
            if b["twin_across"]:
                twin = f"{inst_id}~m"
                # true: an exact mirror image (the twin repeats the draws); "redraw": the twin draws its own
                draw = twin if b["twin_across"] == "redraw" else inst_id
                out.append({"id": twin, "draw": draw, "at": [at[0], -at[1], at[2]], "turn": -b["turn"],
                            "twin_across": True, **common})
    return out


def _mask_index(inst: dict, masks: list[str]) -> int:
    for i, name in enumerate(masks):
        if name in (inst["id"], inst["parent"], inst["use"]):
            return i + 1
    return 0


def _gen_names(resolved: dict, used_materials: set[str]) -> list[str]:
    names = set()
    sky = resolved["world"]["sky"]
    if sky.get("image", "").startswith("gen:"):
        names.add(sky["image"][4:])
    for m in used_materials:
        image = resolved["surfaces"][m].get("image", "")
        if image.startswith("gen:"):
            names.add(image[4:])
    return sorted(names)


# ---------------------------------------------------------------- compile

def compile_all(scene: dict, library: Library | None = None) -> tuple[dict, dict, list[dict]]:
    """The plan, the lock record (every resolved instance and param) and one viewpoint.json record per frame."""
    library = library or Library.shipped()
    r = check_scene(scene, library)
    size, cam, capture = r["size"], r["viewpoint"], r["capture"]
    frames = size["frames"]
    instances = expand_instances(r)
    prims, rigs, block_lights, locks = [], [], [], []
    for inst in instances:
        settings = library.resolve_params(inst["use"], inst["settings"], seed=r["seed"], instance_id=inst["draw"],
                                        surfaces=r["surfaces"])
        ctx = BuildContext(library, inst["id"], inst["use"], r["seed"], frames, size["fps"], at=inst["at"],
                           turn=inst["turn"], twin_across=inst["twin_across"], mask=_mask_index(inst, capture["masks"]),
                           surfaces=r["surfaces"], draw_id=inst["draw"])
        library.block(inst["use"]).build(ctx, settings)
        prims += ctx.prims
        rigs += ctx.rigs
        block_lights += ctx.lamps
        locks.append({"id": inst["id"], "use": inst["use"], "at": inst["at"], "turn": inst["turn"],
                      "twin_across": inst["twin_across"], "settings": settings})
    used = sorted({p["surface"] for p in prims})
    ops: list[dict] = [{"op": "reset"},
                       {"op": "settings", "w": size["w"], "h": size["h"], "fps": size["fps"], "frame_start": 1,
                        "frame_end": frames, "view": capture["view"]},
                       {"op": "world", **r["world"]}]
    ops += [{"op": "surface", "name": m, **r["surfaces"][m]} for m in used]
    ops += prims + rigs
    ops += [{"op": "light", "block": None, **light} for light in r["lamps"]] + block_lights
    poses = camera_path.viewpoint_frames(cam, frames, r["seed"], size["fps"])
    ops.append({"op": "viewpoint", "lens": cam["lens"], "film_mm": cam["film_mm"], "near": cam["near"],
                "far": cam["far"],
                "keys": [{"f": p["f"], "pos": p["pos"], "quat": list(geom.quat_from_matrix(p["rot"])),
                          "lens": p["lens"], "rot": p["rot"]} for p in poses]})
    masks = [{"index": i + 1, "name": name, "aov": f"m{i + 1}"} for i, name in enumerate(capture["masks"])]
    ops.append({"op": "layers", "list": capture["layers"], "masks": masks, "far": cam["far"],
                "depth_range": capture["depth_range"]})
    ops.append({"op": "renderer", "renderer": capture["renderer"], "spp": capture["spp"], "device": capture["device"]})
    a, b = capture["frames"]
    ops.append({"op": "capture", "frames": list(range(a, b + 1, capture["step"]))})
    plan = {"format": PLAN_FORMAT, "scene": r["name"], "seed": r["seed"], "size": size,
            "textures": _gen_names(r, set(used)), "ops": ops}
    lock = {"format": tag("scene-lock"), "scene": r["name"], "seed": r["seed"], "instances": locks,
            "viewpoint": cam, "capture": capture}
    cams = [camera_path.camera_record(p, size["w"], size["h"], cam["film_mm"]) for p in poses]
    return _round(plan), _round(lock), _round(cams)


def compile_plan(scene: dict, library: Library | None = None) -> dict:
    """The flat op list for one scene (see the module docstring)."""
    return compile_all(scene, library)[0]


# ---------------------------------------------------------------- job folder

def _dump(path: Path, data: Any, indent: int | None = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=indent) + "\n", encoding="utf-8")


def write_job(scene_path: str | Path, write_to: str | Path, renderer: str | None = None,
              frames: Sequence[int] | None = None, quick: bool = False, samples: int | None = None,
              size: Sequence[int] | None = None, blend: str | Path | None = None, keep_exr: bool = False,
              library: Library | None = None) -> Path:
    """Write plan.json, scene.lock.json, viewpoint.json, the generated textures and job.json into write_to."""
    from . import textures

    scene_path = Path(scene_path).resolve()
    out = Path(write_to).resolve()
    scene = apply_overrides(load_scene(scene_path), renderer=renderer, frames=frames, quick=quick,
                            samples=samples, size=size)
    plan, lock, cams = compile_all(scene, library)
    _dump(out / "plan.json", plan, indent=None)
    _dump(out / "scene.lock.json", lock)
    w, h = plan["size"]["w"], plan["size"]["h"]
    cam_op = next(op for op in plan["ops"] if op["op"] == "viewpoint")
    _dump(out / "viewpoint.json", {"format": tag("viewpoint"), "w": w, "h": h, "fps": plan["size"]["fps"],
                                "sensor_mm": cam_op["film_mm"], "far": cam_op["far"],
                                "convention": "opencv",
                                "note": "K and to_view: x right, y down, z forward; quat_wxyz is the Blender "
                                        "viewpoint's world rotation (it looks down its -z, +y up).",
                                "frames": cams})
    tex_dir = out / "tex"
    textures.ensure(plan["textures"], tex_dir)
    job = {"format": JOB_FORMAT, "plan": str(out / "plan.json"), "out": str(out), "tex_dir": str(tex_dir),
           "scene_dir": str(scene_path.parent), "src": str(Path(__file__).resolve().parents[2]),
           "blend": str(Path(blend).resolve()) if blend else None, "keep_exr": keep_exr,
           "exr_codec": "ZIP" if keep_exr else EXR_CODEC}
    job_path = out / "job.json"
    _dump(job_path, job)
    return job_path
