"""Hooks after the grade: every file in a hooks folder (`hooks/tone.d/` in a film) runs once, in name order, with two
arguments: the graded film and its measurement JSON. A `.py` hook runs with this Python; any other file runs as a
program. A hook that fails is reported; the graded film stays.

Hooks are programs from the film folder, so the `grade` step runs them only when the person passes `--hooks`, and
names each one before it runs."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

HOOK_TIMEOUT_S = 600
ERROR_TAIL = 300


def _command(hook: Path) -> list[str]:
    return [sys.executable, str(hook)] if hook.suffix == ".py" else [str(hook)]


def listed_hooks(folder: Path | str) -> list[Path]:
    """The hooks in FOLDER in the order they run (none when the folder is missing)."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))


def run_hooks(folder: Path | str, film: Path | str, account: Path | str,
              announce: Callable[[str], None] | None = None) -> list[str]:
    """Run each hook; return one line per hook that failed. ANNOUNCE hears each command line before it runs."""
    problems = []
    for hook in listed_hooks(folder):
        command = _command(hook) + [str(film), str(account)]
        if announce is not None:
            announce(f"hook: running {' '.join(command)}")
        try:
            done = subprocess.run(command, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=HOOK_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired) as problem:
            problems.append(f"hook {hook.name} did not run: {problem}")
            continue
        if done.returncode != 0:
            problems.append(f"hook {hook.name} exited {done.returncode}: {done.stderr.strip()[-ERROR_TAIL:]}")
    return problems
