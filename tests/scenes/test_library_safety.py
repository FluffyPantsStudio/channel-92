"""A scene names its blocks; the names may never reach a builder outside the library it was given."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atomic_flix.scenes import __main__ as scenes_cli
from atomic_flix.scenes.library import Library
from atomic_flix.scenes.schema import SceneError, check_scene

from .conftest import FIXTURES, load_json


def _write_block(root: Path, name: str, marker: Path) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "block.json").write_text(
        '{"name": "%s", "version": 1, "ground_box": [0, 0, 1, 1], "settings": {}}' % name, encoding="utf-8")
    (folder / "build.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
        "def build(ctx, settings):\n    ctx.box((0, 0, 0), (1, 1, 1), 'm')\n", encoding="utf-8")


@pytest.mark.parametrize("name", ["../outside", "..", "a/b", "a\\b", "Box", "-box", "box.", "", "/abs", "C:x"])
def test_a_block_name_outside_the_plain_pattern_is_refused(tmp_path, name):
    lib = Library(tmp_path / "lib")
    (tmp_path / "lib").mkdir()
    assert lib.has_block(name) is False
    with pytest.raises(ValueError):
        lib.block(name)


def test_a_dotted_name_never_runs_a_builder_beside_the_library(tmp_path):
    marker = tmp_path / "ran.txt"
    root = tmp_path / "lib"
    root.mkdir()
    (root / "surfaces.json").write_text("{}", encoding="utf-8")
    _write_block(tmp_path, "outside", marker)
    lib = Library(root)
    assert not lib.has_block("../outside")
    with pytest.raises(ValueError):
        lib.block("../outside")
    assert not marker.exists()


def test_a_scene_with_a_path_in_use_is_refused_before_any_builder_runs(tiny, tmp_path, library):
    marker = tmp_path / "ran.txt"
    _write_block(tmp_path, "evil", marker)
    escape = Path("..") / ".." / ".." / ".." / ".." / ".." / ".." / ".." / ".." / (tmp_path / "evil").as_posix()
    tiny["pieces"][0]["use"] = escape.as_posix()
    with pytest.raises(SceneError, match="use"):
        check_scene(tiny, library)
    assert not marker.exists()


def test_the_shipped_library_ignores_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("FLIX_BLOCKS", str(tmp_path))
    root = Library.shipped().root.resolve()
    assert root != tmp_path.resolve()
    assert root.name == "pieces"


def test_user_blocks_come_only_through_the_blocks_flag(tmp_path, capsys):
    marker = tmp_path / "ran.txt"
    user = tmp_path / "mine"
    user.mkdir()
    (user / "surfaces.json").write_text('{"m": {"kind": "flat", "color": [1, 0, 0]}}', encoding="utf-8")
    _write_block(user, "cube", marker)
    scene = tmp_path / "scene.json"
    data = load_json(FIXTURES / "tiny.json")
    data["pieces"] = [{"use": "cube", "id": "target", "at": [5.5, 0, 0]}]
    scene.write_text(json.dumps(data), encoding="utf-8")
    assert scenes_cli.main(["plan", str(scene)]) == 2, "the packaged library has no cube"
    assert not marker.exists()
    assert scenes_cli.main(["plan", str(scene), "--blocks", str(user)]) == 0
    assert marker.exists(), "the person named the folder, so its builder runs"
