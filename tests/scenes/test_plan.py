"""Compiling a scene into the flat op list Blender executes, and writing the job."""

import json
import os

import numpy as np
import pytest

from atomic_flix.scenes import plan as planmod
from atomic_flix.scenes import schema

from .conftest import EXAMPLES, FIXTURES, HERE, load_json

GOLDEN = HERE / "golden" / "street.plan.json"
ORDER = ["reset", "settings", "world", "surface", "prim", "rig", "light", "viewpoint", "layers", "renderer", "capture"]


def _kinds(plan):
    return [op["op"] for op in plan["ops"]]


def test_ops_come_in_the_fixed_order(street, library):
    plan = planmod.compile_plan(street, library)
    kinds = _kinds(plan)
    ranks = [ORDER.index(k) for k in kinds]
    assert ranks == sorted(ranks)
    for k in ("reset", "settings", "world", "viewpoint", "layers", "renderer", "capture"):
        assert kinds.count(k) == 1
    assert kinds[0] == "reset" and kinds[-1] == "capture"


def test_street_plan_matches_the_golden_file(street, library):
    plan = planmod.compile_plan(street, library)
    text = json.dumps(plan, indent=1, sort_keys=True)
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(text + "\n", encoding="utf-8")
    assert GOLDEN.exists(), "run once with UPDATE_GOLDEN=1 to create the golden plan"
    assert json.loads(text) == load_json(GOLDEN)


def test_same_seed_same_plan_new_seed_new_plan(street, library):
    a = planmod.compile_plan(street, library)
    b = planmod.compile_plan(json.loads(json.dumps(street)), library)
    assert a == b
    street["seed"] = 12
    c = planmod.compile_plan(street, library)
    assert c != a


def _prims_by_block(plan):
    out = {}
    for op in plan["ops"]:
        if op["op"] == "prim":
            out.setdefault(op["block"], []).append(op)
    return out


def test_adding_a_block_leaves_the_others_unchanged(street, library):
    before = _prims_by_block(planmod.compile_plan(street, library))
    street["pieces"].insert(1, {"use": "chest-of-drawers", "at": [6, -6, 0]})
    street["pieces"].append({"use": "eye-on-stalk", "at": [40, 12, 0]})
    after = _prims_by_block(planmod.compile_plan(street, library))
    for block_id, prims in before.items():
        assert after[block_id] == prims, block_id
    assert len(after) == len(before) + 2


def test_mirror_y_true_makes_an_exact_mirrored_twin(street, library):
    street["pieces"][1]["twin_across"] = True
    prims = _prims_by_block(planmod.compile_plan(street, library))
    left, right = prims["front"], prims["front~m"]
    assert len(left) == len(right)
    for a, b in zip(left, right):
        assert a["pos"][0] == pytest.approx(b["pos"][0])
        assert a["pos"][1] == pytest.approx(-b["pos"][1])
        assert a["scale"] == b["scale"]


def test_mirror_y_redraw_mirrors_the_place_but_draws_again(street, library):
    assert street["pieces"][1]["twin_across"] == "redraw"   # street.py draws each side of the street on its own
    prims = _prims_by_block(planmod.compile_plan(street, library))
    left, right = prims["front"], prims["front~m"]
    assert all(p["pos"][1] == pytest.approx(25) for p in left)
    assert all(p["pos"][1] == pytest.approx(-25) for p in right)
    assert [p["scale"] for p in left] != [p["scale"] for p in right]


def test_mirror_y_bad_value(street, library):
    street["pieces"][1]["twin_across"] = "yes"
    with pytest.raises(schema.SceneError, match=r"pieces\[1\].twin_across"):
        planmod.compile_plan(street, library)


def test_street_towers_follow_street_py(street, library):
    prims = _prims_by_block(planmod.compile_plan(street, library))
    towers = [p for p in prims["front"] if p["shape"] == "box"]
    assert 15 <= len(towers) <= 30
    for t in towers:
        w, d, h = t["scale"]
        assert 11 <= w <= 15 and d == pytest.approx(12) and 18 <= h <= 42
        assert t["pos"][1] == pytest.approx(25) and t["pos"][2] == pytest.approx(h / 2)
        assert t["surface"] == "steel_case"
    xs = sorted(t["pos"][0] - t["scale"][0] / 2 for t in towers)
    assert 3 <= xs[0] <= 7 and xs[-1] < 600
    back = [p for p in prims["back"] if p["shape"] == "box"]
    assert all(35 <= p["scale"][2] <= 65 and p["pos"][1] == pytest.approx(43) for p in back)


def test_open_drawers_stick_out_toward_the_street(street, library):
    prims = _prims_by_block(planmod.compile_plan(street, library))
    left = [p for p in prims["drawers"] if p["surface"] == "drawer"]
    right = [p for p in prims["drawers~m"] if p["surface"] == "drawer"]
    assert len(left) == len(right) == 46
    assert all(p["pos"][1] < 19 for p in left)
    assert all(p["pos"][1] > -19 for p in right)


def test_eyes_scatter_alternates_sides_and_looks_at_the_camera_start(street, library):
    prims = _prims_by_block(planmod.compile_plan(street, library))
    eye_ids = sorted(k for k in prims if k.startswith("eyes/"))
    assert len(eye_ids) == len(range(18, 520, 33))
    sides = [np.sign(next(p for p in prims[k] if p["surface"] == "pole")["pos"][1]) for k in eye_ids]
    assert sides[0] == -1 and all(a == -b for a, b in zip(sides, sides[1:]))
    for k in eye_ids:
        ball = next(p for p in prims[k] if p["surface"] == "eye-white")
        iris = next(p for p in prims[k] if p["surface"] == "iris")
        look = np.array(iris["pos"][:2]) - np.array(ball["pos"][:2])
        to_cam = -np.array(ball["pos"][:2])
        cos = look @ to_cam / np.linalg.norm(look) / np.linalg.norm(to_cam)
        assert cos == pytest.approx(1.0, abs=1e-6)


def test_masks_set_an_index_on_the_masked_blocks(street, library):
    plan = planmod.compile_plan(street, library)
    layers = next(op for op in plan["ops"] if op["op"] == "layers")
    assert layers["masks"] == [{"index": 1, "name": "eye-on-stalk", "aov": "m1"}]
    for op in plan["ops"]:
        if op["op"] == "prim":
            assert op["mask"] == (1 if op["kind"] == "eye-on-stalk" else 0)


def test_only_used_materials_are_emitted(tiny, library):
    plan = planmod.compile_plan(tiny, library)
    names = [op["name"] for op in plan["ops"] if op["op"] == "surface"]
    assert names == ["drawer"]


def test_camera_op_has_one_key_per_frame(street, library):
    plan = planmod.compile_plan(street, library)
    cam = next(op for op in plan["ops"] if op["op"] == "viewpoint")
    assert len(cam["keys"]) == 145
    assert cam["keys"][0]["f"] == 1 and cam["keys"][-1]["f"] == 145
    assert cam["keys"][-1]["pos"] == pytest.approx([17, 0, 1.4])


def test_textures_named_gen_are_listed(street, library):
    plan = planmod.compile_plan(street, library)
    assert set(plan["textures"]) >= {"dusk", "steel_case"}


def test_overrides_for_preview_and_frame_range(street, library):
    s = planmod.apply_overrides(street, quick=True)
    assert s["size"]["w"] == 960 and s["size"]["h"] == 528
    assert s["capture"]["spp"] == 16
    plan = planmod.compile_plan(s, library)
    capture = plan["ops"][-1]
    assert capture["frames"] == list(range(1, 146, 4))
    s = planmod.apply_overrides(street, renderer="pathtrace", frames=(10, 12), samples=8)
    plan = planmod.compile_plan(s, library)
    assert plan["ops"][-1]["frames"] == [10, 11, 12]
    renderer = next(op for op in plan["ops"] if op["op"] == "renderer")
    assert renderer["renderer"] == "pathtrace" and renderer["spp"] == 8
    with pytest.raises(schema.SceneError, match="frames"):
        planmod.compile_plan(planmod.apply_overrides(street, frames=(140, 150)), library)
    assert street["size"]["w"] == 1920  # apply_overrides copies


def test_mannequin_gives_animated_parts_and_a_rig(library):
    scene = load_json(EXAMPLES / "picnic.json")
    plan = planmod.compile_plan(scene, library)
    parts = [op for op in plan["ops"] if op["op"] == "prim" and op["block"] == "performer"]
    assert parts and all(len(p["keys"]) == 97 for p in parts)
    rig = next(op for op in plan["ops"] if op["op"] == "rig")
    assert rig["block"] == "performer" and len(rig["frames"]) == 97
    assert {"neck", "r_wrist", "l_ankle", "nose"} <= set(rig["frames"][0])
    head = rig["frames"][0]["nose"]
    assert 1.4 < head[2] < 1.8


def test_write_job_writes_plan_job_lock_and_camera(tmp_path, tiny):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps(tiny), encoding="utf-8")
    out = tmp_path / "out"
    job_path = planmod.write_job(scene_path, out)
    job = load_json(job_path)
    assert job["format"] == "atomic-flix/scene-job@1"
    assert job["out"] == str(out.resolve())
    assert (out / "plan.json").exists()
    lock = load_json(out / "scene.lock.json")
    assert lock["seed"] == 3 and lock["instances"][0]["id"] == "target"
    cam = load_json(out / "viewpoint.json")
    assert cam["convention"] == "opencv"
    assert len(cam["frames"]) == 3
    assert cam["frames"][0]["K"][0][0] == pytest.approx(32 / 36 * 64)


def test_write_job_for_a_blend_file(tmp_path, tiny):
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps(tiny), encoding="utf-8")
    job = load_json(planmod.write_job(scene_path, tmp_path / "o", blend=tmp_path / "s.blend"))
    assert job["blend"].endswith("s.blend")


def test_tiny_fixture_box_front_face_is_five_metres_out(tiny, library):
    plan = planmod.compile_plan(tiny, library)
    box = next(op for op in plan["ops"] if op["op"] == "prim")
    assert box["pos"][0] - box["scale"][0] / 2 == pytest.approx(5.0)
    assert box["pos"][2] == pytest.approx(0.0)
    assert box["mask"] == 1


def test_fixture_dir_exists():
    assert (FIXTURES / "tiny.json").exists()
