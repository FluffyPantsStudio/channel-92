"""Helpers for the scene toolkit tests.

Tests marked `blender` start Blender 5.2 headless; they are skipped when it is not installed.
"""

import copy
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
REPO = HERE.parents[1]
EXAMPLES = REPO / "src" / "atomic_flix" / "scenes" / "pieces" / "examples"


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@pytest.fixture
def tiny() -> dict:
    return copy.deepcopy(load_json(FIXTURES / "tiny.json"))


@pytest.fixture
def street() -> dict:
    return copy.deepcopy(load_json(EXAMPLES / "street.json"))


@pytest.fixture
def library():
    from atomic_flix.scenes.library import Library

    return Library.shipped()
