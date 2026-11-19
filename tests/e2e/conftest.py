"""The end-to-end tests drive the runner against the runner tests' fake ComfyUI."""

import sys
from pathlib import Path

RUNNER_TESTS = Path(__file__).resolve().parents[1] / "runner"
if str(RUNNER_TESTS) not in sys.path:
    sys.path.insert(0, str(RUNNER_TESTS))
