"""A stand-in for ntsc-rs-cli in the tests: a tiny program that records its arguments, keeps a copy of what it was
given (the picture as input-N, the preset as preset-N.json), and copies its input to its output (or, with NTSC_STUB_NEGATE set, writes the input's negative, so a test
can tell the stand-in's output from its input)."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

STUB = '''
import json, os, shutil, subprocess, sys
from pathlib import Path
here = Path(__file__).resolve().parent
args = sys.argv[1:]
source, out = Path(args[args.index("-i") + 1]), Path(args[args.index("-o") + 1])
calls = here / "calls.jsonl"
number = len(calls.read_text(encoding="utf-8").splitlines()) if calls.is_file() else 0
with calls.open("a", encoding="utf-8") as log:
    log.write(json.dumps({"args": args, "input_was_there": source.is_file()}) + "\\n")
shutil.copyfile(source, here / f"input-{number}{source.suffix}")
if "-p" in args:
    shutil.copyfile(args[args.index("-p") + 1], here / f"preset-{number}.json")
if os.environ.get("NTSC_STUB_NEGATE"):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vf", "negate", "-c:v", "ffv1", str(out)],
                   check=True)
else:
    shutil.copyfile(source, out)
'''


def write_stub(folder: Path) -> Path:
    """Write the stand-in into FOLDER; returns the program to run (ntsc-rs-cli.cmd on Windows, else ntsc-rs-cli)."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stub.py").write_text(STUB, encoding="utf-8")
    if os.name == "nt":
        program = folder / "ntsc-rs-cli.cmd"
        program.write_text(f'@"{sys.executable}" "%~dp0stub.py" %*\r\n', encoding="utf-8")
    else:
        program = folder / "ntsc-rs-cli"
        program.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/stub.py" "$@"\n', encoding="utf-8")
        program.chmod(program.stat().st_mode | stat.S_IEXEC)
    return program


def calls(folder: Path) -> list[dict]:
    import json
    log = folder / "calls.jsonl"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []


def preset_given(folder: Path, number: int = 0) -> dict:
    """The preset the stand-in was given on its NUMBERth call (the file itself is gone with the work folder)."""
    import json
    return json.loads((folder / f"preset-{number}.json").read_text(encoding="utf-8"))
