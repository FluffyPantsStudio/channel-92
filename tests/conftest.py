"""Shared test helpers: the `tool` fixture loads a script from tools/ (see tool_loader.py).

`load_tool` lives in its own uniquely named module: pytest imports every folder's conftest.py as `conftest`, so a
test that imports from `conftest` gets whichever was loaded last.
"""

import pytest

from tool_loader import load_tool


@pytest.fixture
def tool():
    return load_tool
