"""The pieces and surfaces library under src/atomic_flix/scenes/pieces/."""

import pytest

from atomic_flix.scenes import geom
from atomic_flix.scenes.library import BuildContext, Library

REQUIRED_BLOCKS = {"box", "road", "tower-row", "drawers", "eye-on-stalk", "chest-of-drawers", "kitchen-counter",
                   "lawn-picnic", "salt-flat", "room-wall-light", "figure"}


def test_library_has_the_first_blocks(library):
    assert REQUIRED_BLOCKS <= set(library.block_names())


@pytest.mark.parametrize("name", sorted(REQUIRED_BLOCKS))
def test_block_metadata(library, name):
    meta = library.block(name).meta
    assert meta["name"] == name
    assert meta["rights"] == "ours"
    assert isinstance(meta["version"], int)
    assert len(meta["ground_box"]) == 4
    for pname, spec in meta["settings"].items():
        assert spec["type"] in {"float", "int", "bool", "str", "span", "vec3", "vec2", "surface"}, pname
        assert "fallback" in spec, pname


@pytest.mark.parametrize("name", sorted(REQUIRED_BLOCKS))
def test_block_builds_with_defaults_and_uses_known_materials(library, name):
    block = library.block(name)
    settings = library.resolve_params(name, {}, seed=1, instance_id=name)
    ctx = BuildContext(library, instance_id=name, kind=name, seed=1, frames=5, fps=24)
    block.build(ctx, settings)
    assert ctx.prims, name
    for prim in ctx.prims:
        assert prim["surface"] in library.surfaces, (name, prim["surface"])
        assert prim["shape"] in {"box", "tube", "ball"}
        assert all(s > 0 for s in prim["scale"]), (name, prim)
        assert abs(sum(c * c for c in prim["quat"]) - 1) < 1e-9


def test_room_wall_light_brings_a_light(library):
    settings = library.resolve_params("room-wall-light", {}, seed=1, instance_id="room")
    ctx = BuildContext(library, instance_id="room", kind="room-wall-light", seed=1, frames=1, fps=24)
    library.block("room-wall-light").build(ctx, settings)
    assert any(light["kind"] == "point" for light in ctx.lamps)


def test_chest_of_drawers_opens_some_drawers(library):
    settings = library.resolve_params("chest-of-drawers", {"rows": 4, "open": 2}, seed=3, instance_id="c")
    ctx = BuildContext(library, instance_id="c", kind="chest-of-drawers", seed=3, frames=1, fps=24)
    library.block("chest-of-drawers").build(ctx, settings)
    fronts = [p for p in ctx.prims if p["name"].startswith("front")]
    assert len(fronts) == 4
    closed_x = min(p["pos"][0] for p in fronts)
    opened = [p for p in fronts if p["pos"][0] > closed_x + 0.05]
    assert len(opened) == 2


def test_ranges_are_drawn_per_instance_and_spans_are_passed_through(library):
    a = library.resolve_params("eye-on-stalk", {"height": [9, 15]}, seed=1, instance_id="e/0")
    b = library.resolve_params("eye-on-stalk", {"height": [9, 15]}, seed=1, instance_id="e/1")
    again = library.resolve_params("eye-on-stalk", {"height": [9, 15]}, seed=1, instance_id="e/0")
    assert 9 <= a["height"] <= 15 and a["height"] != b["height"] and a == again
    t = library.resolve_params("tower-row", {}, seed=1, instance_id="t")
    assert t["height"] == [18.0, 42.0]


def test_unknown_param_and_bad_type_raise(library):
    with pytest.raises(ValueError, match="nope"):
        library.resolve_params("box", {"nope": 1}, seed=1, instance_id="b")
    with pytest.raises(ValueError, match="size"):
        library.resolve_params("box", {"size": "big"}, seed=1, instance_id="b")


def test_context_transform_turns_and_mirrors(library):
    ctx = BuildContext(library, instance_id="b", kind="box", seed=1, frames=1, fps=24,
                       at=(10, 0, 0), turn=90, twin_across=True)
    ctx.box((1, 2, 0), (1, 1, 1), "drawer", yaw=30)
    p = ctx.prims[0]
    # mirror first: (1, -2, 0); then turn 90: (2, 1, 0); then move: (12, 1, 0)
    assert p["pos"] == pytest.approx([12, 1, 0])
    expected = geom.quat_mul(geom.quat_yaw(90), geom.quat_yaw(-30))
    assert p["quat"] == pytest.approx(list(expected))
    assert ctx.to_local((12, 1, 0)) == pytest.approx([1, 2, 0])


def test_limb_runs_between_two_points(library):
    ctx = BuildContext(library, instance_id="m", kind="figure", seed=1, frames=1, fps=24)
    ctx.limb((0, 0, 0), (0, 0, 2), 0.1, "figure")
    p = ctx.prims[0]
    assert p["pos"] == pytest.approx([0, 0, 1])
    assert p["scale"] == pytest.approx([0.2, 0.2, 2])


def test_materials_library(library):
    mats = library.surfaces
    for name in ("steel_case", "road", "drawer", "eye-white", "pole", "grass", "salt", "figure"):
        assert name in mats
    assert mats["steel_case"]["kind"] == "image"
    assert mats["steel_case"]["image"] == "gen:steel_case"
    assert mats["steel_case"]["scale"] == pytest.approx([1 / 3.6, 1 / 3.6, -1 / 6])


def test_library_from_another_folder(tmp_path):
    (tmp_path / "surfaces.json").write_text('{"m": {"kind": "flat", "color": [1, 0, 0]}}', encoding="utf-8")
    d = tmp_path / "cube"
    d.mkdir()
    (d / "block.json").write_text('{"name": "cube", "version": 1, "ground_box": [0, 0, 1, 1], "tags": [], '
                                  '"surfaces": ["m"], "source": "test", "licence": "ours", '
                                  '"settings": {"s": {"type": "float", "default": 1, "min": 0.1}}}', encoding="utf-8")
    (d / "build.py").write_text("def build(ctx, settings):\n    ctx.box((0, 0, 0), (settings['s'],) * 3, 'm')\n",
                                encoding="utf-8")
    lib = Library(tmp_path)
    assert lib.block_names() == ["cube"]
    ctx = BuildContext(lib, instance_id="c", kind="cube", seed=1, frames=1, fps=24)
    lib.block("cube").build(ctx, lib.resolve_params("cube", {"s": 2}, seed=1, instance_id="c"))
    assert ctx.prims[0]["scale"] == [2, 2, 2]


def test_block_with_wrong_name_in_json_is_refused(tmp_path):
    (tmp_path / "surfaces.json").write_text("{}", encoding="utf-8")
    d = tmp_path / "cube"
    d.mkdir()
    (d / "block.json").write_text('{"name": "box", "version": 1, "ground_box": [0,0,1,1], "settings": {}, '
                                  '"licence": "ours"}', encoding="utf-8")
    (d / "build.py").write_text("def build(ctx, settings):\n    pass\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cube"):
        Library(tmp_path).block("cube")


def test_blocks_ship_inside_the_package():
    import fnmatch
    import tomllib
    from pathlib import Path

    import atomic_flix
    from atomic_flix.scenes.library import Library

    package = Path(atomic_flix.__file__).resolve().parent
    root = Library.shipped().root.resolve()
    assert package in root.parents, "the default library must live inside the package so a wheel carries it"
    config = tomllib.loads((package.parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    globs = config["tool"]["setuptools"]["package-data"]["atomic_flix"]
    files = [p.relative_to(package).as_posix() for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    assert files
    missing = [f for f in files if not any(fnmatch.fnmatch(f, g) for g in globs)]
    assert missing == []
