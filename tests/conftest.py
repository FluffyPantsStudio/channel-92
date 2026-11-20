"""Shared test helpers: the `tool` fixture loads a script from tools/ (see tool_loader.py).

`load_tool` lives in its own uniquely named module: pytest imports every folder's conftest.py as `conftest`, so a
test that imports from `conftest` gets whichever was loaded last.
"""

import pytest

from tool_loader import load_tool


@pytest.fixture
def tool():
    return load_tool


@pytest.fixture
def no_eval_hook(monkeypatch):
    """For tests of gate bookkeeping on folders too bare to evaluate: gates 5 and 6 and `shoot` skip the eval hook
    here. The hook itself, and a real film passing it, are tested in tests/eval/ and tests/e2e/."""
    monkeypatch.setattr("atomic_flix.project.actions.require_eval", lambda *args, **kwargs: None)
    monkeypatch.setattr("atomic_flix.cli.shoot_steps.eval_refusal", lambda *args, **kwargs: None)
