"""Scene description checks: examples validate, every bad field is named."""

import json

import pytest

from atomic_flix.scenes import schema
from atomic_flix.scenes.schema import SceneError

from .conftest import EXAMPLES, FIXTURES, load_json


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.json")) + [FIXTURES / "tiny.json"], ids=lambda p: p.name)
def test_every_example_validates(path, library):
    resolved = schema.check_scene(load_json(path), library)
    assert resolved["format"] == "atomic-flix/scene@1"
    assert resolved["size"]["fps"] > 0


def test_there_are_at_least_two_examples():
    assert len(list(EXAMPLES.glob("*.json"))) >= 2


def test_defaults_are_filled(tiny, library):
    del tiny["seed"]
    del tiny["capture"]
    r = schema.check_scene(tiny, library)
    assert r["seed"] == 1
    assert r["capture"]["renderer"] == "raster"
    assert r["capture"]["spp"] == 64
    assert r["capture"]["view"] == "Standard"
    assert r["capture"]["layers"] == ["shaded", "depth", "facing", "mist", "mask"]
    assert r["viewpoint"]["near"] == pytest.approx(0.1)
    assert r["pieces"][0]["turn"] == 0 and r["pieces"][0]["twin_across"] is False


def test_the_input_is_not_changed(tiny, library):
    before = json.dumps(tiny, sort_keys=True)
    schema.check_scene(tiny, library)
    assert json.dumps(tiny, sort_keys=True) == before


def _mutate(scene, dotted, value):
    node = scene
    keys = dotted.split(".")
    for k in keys[:-1]:
        node = node[int(k)] if k.isdigit() else node[k]
    last = keys[-1]
    if value is KeyError:
        del node[last]
    elif last.isdigit():
        node[int(last)] = value
    else:
        node[last] = value


BAD = [
    ("colour", "unknown key", "colour", 1),
    ("size.fps", "size.fps", "size.fps", 0),
    ("size.w", "size.w", "size.w", 63.5),
    ("size.frames", "size.frames", "size.frames", -2),
    ("size.depth", "size.depth", "size.depth", 3),
    ("format", "format", "format", "atomic-flix/scene@9"),
    ("name", "name", "name", KeyError),
    ("world.sky.rotate", "world.sky.rotate", "world.sky.rotate", "ninety"),
    ("world.sky", "world.sky", "world.sky.image", "x.png"),  # image and colour at once
    ("world.mist.depth", "world.mist.depth", "world.mist.depth", 0),
    ("lamps.0.kind", "lamps[0].kind", "lamps.0.kind", "laser"),
    ("lamps.0.power", "lamps[0].power", "lamps.0.power", -1),
    ("lamps.0.colour", "lamps[0].colour", "lamps.0.colour", [1, 1, 1]),
    ("lamps.0.color", "lamps[0].color", "lamps.0.color", [1, 1]),
    ("pieces.0.use", "pieces[0].use", "pieces.0.use", "spaceship"),
    ("pieces.0.at", "pieces[0].at", "pieces.0.at", [1, 2]),
    ("pieces.0.settings.size", "pieces[0].settings.size", "pieces.0.settings.size", [1, 1]),
    ("pieces.0.settings.lift", "pieces[0].settings.lift", "pieces.0.settings.lift", [3, 1]),
    ("pieces.0.settings.surface", "pieces[0].settings.surface", "pieces.0.settings.surface", "unobtainium"),
    ("pieces.0.settings.heigth", "pieces[0].settings.heigth", "pieces.0.settings.heigth", 3),
    ("pieces.0.strew", "pieces[0].strew.along", "pieces.0.strew", {"along": "w", "from": 0, "to": 4, "step": 1}),
    ("pieces.0.strew.step", "pieces[0].strew.step", "pieces.0.strew", {"along": "x", "from": 0, "to": 4, "step": 0}),
    ("viewpoint.lens", "viewpoint.lens", "viewpoint.lens", 0),
    ("viewpoint.path.move", "viewpoint.path.move", "viewpoint.path.move", "zoom"),
    ("viewpoint.path.ease", "viewpoint.path.ease", "viewpoint.path.ease", "bounce"),
    ("viewpoint.path.pos", "viewpoint.path.pos", "viewpoint.path.pos", [0, 0]),
    ("viewpoint.far", "viewpoint.far", "viewpoint.far", 0.05),
    ("capture.renderer", "capture.renderer", "capture.renderer", "unreal"),
    ("capture.layers", "capture.layers", "capture.layers", ["shaded", "xray"]),
    ("capture.masks", "capture.masks", "capture.masks", ["ghost"]),
    ("capture.samples", "capture.samples", "capture.samples", 0),
    ("capture.device", "capture.device", "capture.device", "tpu"),
]


@pytest.mark.parametrize("dotted,named,where,value", BAD, ids=[b[0] for b in BAD])
def test_bad_fields_fail_with_the_field_named(tiny, library, dotted, named, where, value):
    _mutate(tiny, where, value)
    with pytest.raises(SceneError) as err:
        schema.check_scene(tiny, library)
    assert named in str(err.value)


def test_duplicate_block_ids_fail(tiny, library):
    tiny["pieces"].append(dict(tiny["pieces"][0]))
    with pytest.raises(SceneError, match="target"):
        schema.check_scene(tiny, library)


def test_path_keys_need_frames_in_range(tiny, library):
    tiny["viewpoint"]["path"] = {"keys": [{"f": 1, "pos": [0, 0, 0]}, {"f": 9, "pos": [1, 0, 0]}]}
    with pytest.raises(SceneError, match=r"viewpoint.path.keys\[1\].f"):
        schema.check_scene(tiny, library)


def test_path_keys_must_rise(tiny, library):
    tiny["viewpoint"]["path"] = {"keys": [{"f": 2, "pos": [0, 0, 0]}, {"f": 2, "pos": [1, 0, 0]}]}
    with pytest.raises(SceneError, match="keys"):
        schema.check_scene(tiny, library)


def test_path_cannot_mix_preset_and_keys(tiny, library):
    tiny["viewpoint"]["path"]["keys"] = [{"f": 1, "pos": [0, 0, 0]}]
    with pytest.raises(SceneError, match="viewpoint.path"):
        schema.check_scene(tiny, library)


def test_scene_materials_extend_the_library(tiny, library):
    tiny["surfaces"] = {"tin": {"kind": "flat", "srgb": [0.5, 0.5, 0.55], "metal": 1.0}}
    tiny["pieces"][0]["settings"]["surface"] = "tin"
    r = schema.check_scene(tiny, library)
    assert r["surfaces"]["tin"]["kind"] == "flat"


def test_scene_material_with_bad_kind_fails(tiny, library):
    tiny["surfaces"] = {"tin": {"kind": "plasma"}}
    with pytest.raises(SceneError, match="surfaces.tin.kind"):
        schema.check_scene(tiny, library)


def test_load_scene_reports_bad_json(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(SceneError, match="s.json"):
        schema.load_scene(p)


def test_masks_may_name_a_block_id_or_a_block_kind(street, library):
    street["capture"]["masks"] = ["eyes", "tower-row"]
    schema.check_scene(street, library)
