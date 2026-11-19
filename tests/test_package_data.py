"""Every file the package reads at run time is listed as package data, so a built wheel carries it."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "src" / "atomic_flix"


def _package_data() -> list[str]:
    if sys.version_info < (3, 11):
        pytest.skip("tomllib needs Python 3.11")
    import tomllib

    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return config["tool"]["setuptools"]["package-data"]["atomic_flix"]


def test_every_data_file_in_the_package_is_listed():
    listed = {path for pattern in _package_data() for path in PACKAGE.glob(pattern)}
    data = {path for path in PACKAGE.rglob("*") if path.is_file() and path.suffix not in (".py", ".pyc")
            and "__pycache__" not in path.parts}
    assert sorted(p.relative_to(PACKAGE).as_posix() for p in data - listed) == []


def test_the_graph_name_maps_ship_inside_the_package():
    from atomic_flix.runner.names import KIT_MAPS

    assert KIT_MAPS.parent == PACKAGE.resolve() or KIT_MAPS.parent.name == "atomic_flix"
    assert sorted(p.name for p in KIT_MAPS.glob("*.map.json"))
    assert "workflows/*.json" in _package_data()
