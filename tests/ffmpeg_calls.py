"""Watching the kit's ffmpeg and ffprobe calls: every program by its absolute path, every input file behind
`-protocol_whitelist` (cut/media.py)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def ffmpeg_calls(monkeypatch) -> list[list[str]]:
    """Record every ffmpeg and ffprobe command run through subprocess from now on (the test's monkeypatch undoes it)."""
    seen: list[list[str]] = []
    run, popen = subprocess.run, subprocess.Popen

    def record(command):
        if Path(str(command[0])).stem.lower() in ("ffmpeg", "ffprobe"):
            seen.append([str(part) for part in command])

    def run_(command, *args, **kwargs):
        record(command)
        return run(command, *args, **kwargs)

    class Popen_(popen):
        def __init__(self, command, *args, **kwargs):
            record(command)
            super().__init__(command, *args, **kwargs)
    monkeypatch.setattr(subprocess, "run", run_)
    monkeypatch.setattr(subprocess, "Popen", Popen_)
    return seen


def assert_whitelisted(calls: list[list[str]]) -> None:
    """Every call is by absolute path, and every input (each -i, or ffprobe's one) has a protocol whitelist."""
    assert calls
    for command in calls:
        assert Path(command[0]).is_absolute(), command
        if Path(command[0]).stem.lower() == "ffprobe":
            assert "-protocol_whitelist" in command, command
            continue
        start = 0
        for at, part in enumerate(command):
            if part == "-i":
                assert "-protocol_whitelist" in command[start:at], command
                start = at + 1
