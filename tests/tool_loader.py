"""Load a script from tools/ by file path under a private module name.

A tool called click.py can then never shadow a third-party package of the same name, and test files import this
helper by its own unique name instead of `conftest` (pytest loads several conftest modules, all called `conftest`).
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"


def load_tool(name: str):
    module_name = f"af_tool_{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, TOOLS / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = loaded
    spec.loader.exec_module(loaded)
    return loaded
