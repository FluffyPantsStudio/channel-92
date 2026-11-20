"""`channel92 setup`: one row per prerequisite, found or missing, its version, where it is, what the kit needs it
for, and how to get it. Checking only reads: it runs `-version`/`--version` on what it finds and asks the local
ComfyUI hosts for their GPU (never a host off this machine), and changes nothing.

Required: Python 3.10+, numpy, ffmpeg and ffprobe (the real PATH only, `programs.py`), ntsc-rs-cli (found as
`finish` finds it, `finish/ntsc.py`). Optional: Blender 5.2 (`scenes` only), a ComfyUI host (`shoot` only), Pillow
(the [brand] extra, for drawing the era logos). The kit installs only ntsc-rs (`setup --install`); never Blender or
ComfyUI.
"""

from __future__ import annotations

import os
import platform as platform_module
import subprocess
import sys
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Callable, Sequence

from ..programs import ProgramError, command_of, find_program
from .pins import platform_key

NAMES = ("python", "numpy", "ffmpeg", "ffprobe", "ntsc-rs", "blender", "comfyui", "pillow")
MIN_PYTHON = (3, 10)
VERSION_TIMEOUT_S = 20
PING_TIMEOUT_S = 2.0
FFMPEG_GET = {"windows": "winget install Gyan.FFmpeg", "linux": "sudo apt install ffmpeg",
              "macos": "brew install ffmpeg"}


@dataclass(frozen=True)
class Row:
    name: str
    required: bool
    found: bool
    version: str
    where: str
    purpose: str
    get: str


def run_version(path: Path, args: Sequence[str]) -> str:
    """The first line PATH ARGS prints (its version line), or "" when it does not run."""
    try:
        done = subprocess.run(command_of([str(path), *args]), stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=VERSION_TIMEOUT_S)
    except (OSError, ProgramError, subprocess.TimeoutExpired):
        return ""
    lines = [line.strip() for line in (done.stdout or done.stderr or "").splitlines() if line.strip()]
    return short_version(lines[0]) if lines and done.returncode == 0 else ""


def short_version(line: str) -> str:
    """The version out of a version line: the word after "version" when there is one ("ffmpeg version 8.0.1 ..."),
    else the line itself, at most 40 characters."""
    words = line.split()
    lowered = [word.lower() for word in words]
    if "version" in lowered[:-1]:
        return words[lowered.index("version") + 1][:40]
    return line[:40]


def _comfy_hosts() -> list[str]:
    from ..runner.__main__ import DEFAULT_HOSTS
    text = os.environ.get("ATOMIC_FLIX_HOSTS", DEFAULT_HOSTS)
    return [host.strip() for host in text.split(",") if host.strip()]


def ping_comfyui(timeout_s: float = PING_TIMEOUT_S) -> list[str]:
    """The local ComfyUI hosts that answer, each with its GPU; hosts off this machine are never asked."""
    from ..runner.comfy import ComfyClient, ComfyError
    answered = []
    for host in _comfy_hosts():
        try:
            name, vram = ComfyClient(host, timeout_s).gpu(timeout_s)
        except (ComfyError, ValueError):
            continue
        answered.append(f"{host} ({name}, {vram:.0f} GB)")
    return answered


def _find_ntsc() -> tuple[Path | None, str]:
    from ..finish.ntsc import NtscError, locate_ntsc_rs
    try:
        return locate_ntsc_rs()
    except NtscError as problem:
        return None, str(problem)


def _find_blender() -> Path:
    from ..scenes.capture import find_blender
    return find_blender()


def _which(name: str) -> Path | None:
    try:
        return find_program(name)
    except ProgramError:
        return None


@dataclass(frozen=True)
class Context:
    """How each prerequisite is looked up; the tests swap these."""

    which: Callable[[str], Path | None] = _which
    version_of: Callable[[Path, Sequence[str]], str] = run_version
    ping: Callable[[], list[str]] = ping_comfyui
    find_ntsc: Callable[[], tuple[Path | None, str]] = _find_ntsc
    find_blender: Callable[[], Path] = _find_blender
    platform: str = field(default_factory=lambda: sys.platform)


def default_context() -> Context:
    return Context()


def _python(ctx: Context) -> Row:
    ok = sys.version_info[:2] >= MIN_PYTHON
    return Row("python", True, ok, platform_module.python_version(), sys.executable, "runs the kit",
               "Python 3.10 or newer from https://www.python.org/downloads/")


def _package(name: str, dist: str, required: bool, purpose: str, get: str) -> Row:
    try:
        version = metadata.version(dist)
    except metadata.PackageNotFoundError:
        return Row(name, required, False, "", "", purpose, get)
    return Row(name, required, True, version, f"Python package {dist}", purpose, get)


def _program(ctx: Context, name: str, purpose: str) -> Row:
    get = FFMPEG_GET.get(platform_key(ctx.platform), " or ".join(FFMPEG_GET.values()))
    found = ctx.which(name)
    if found is None:
        return Row(name, True, False, "", "not on the PATH (the current directory is never searched)", purpose, get)
    return Row(name, True, True, ctx.version_of(found, ["-version"]), str(found), purpose, get)


def _ntsc(ctx: Context) -> Row:
    purpose, get = "the eras' analog looks in `finish`", "channel92 setup --install"
    found, how = ctx.find_ntsc()
    if found is None:
        return Row("ntsc-rs", True, False, "", how or "not found", purpose, get)
    return Row("ntsc-rs", True, True, ctx.version_of(found, ["--version"]), f"{found} ({how})", purpose, get)


def _blender(ctx: Context) -> Row:
    purpose = "the `scenes` verbs only (capture, blend)"
    get = ("Blender 5.2 from https://www.blender.org/download/ (set FLIX_BLENDER if it is not in the usual place); "
           "the kit never installs it")
    try:
        found = ctx.find_blender()
    except FileNotFoundError as problem:
        return Row("blender", False, False, "", str(problem), purpose, get)
    return Row("blender", False, True, ctx.version_of(found, ["--version"]), str(found), purpose, get)


def _comfyui(ctx: Context) -> Row:
    purpose = "`shoot` only (the renders)"
    get = ("ComfyUI from https://github.com/comfyanonymous/ComfyUI, one instance per GPU on 127.0.0.1:8188 and "
           ":8189 (or ATOMIC_FLIX_HOSTS); the kit never installs it")
    answered = ctx.ping()
    where = ", ".join(answered) if answered else "no local host answered"
    return Row("comfyui", False, bool(answered), "", where, purpose, get)


ROWS: dict[str, Callable[[Context], Row]] = {
    "python": _python,
    "numpy": lambda ctx: _package("numpy", "numpy", True, "every stage", 'pip install -e . (or pip install numpy)'),
    "ffmpeg": lambda ctx: _program(ctx, "ffmpeg", "reads and writes all audio and video"),
    "ffprobe": lambda ctx: _program(ctx, "ffprobe", "reads clip lengths, sizes and rates"),
    "ntsc-rs": _ntsc,
    "blender": _blender,
    "comfyui": _comfyui,
    "pillow": lambda ctx: _package("pillow", "Pillow", False, "tools/make_era_logos.py only",
                                   'pip install -e ".[brand]"'),
}


def check_rows(only: str | None = None, context: Context | None = None) -> tuple[Row, ...]:
    """The rows for every prerequisite (or ONLY that one), in NAMES order."""
    ctx = context or default_context()
    return tuple(ROWS[name](ctx) for name in NAMES if only in (None, name))


def all_required_present(rows: Sequence[Row]) -> bool:
    return all(row.found for row in rows if row.required)


def table(rows: Sequence[Row]) -> str:
    """A plain table: name, required or optional, found or missing, version, where, what for; then how to get each
    missing one."""
    head = ("NAME", "NEEDED", "STATUS", "VERSION", "FOR", "WHERE")
    body = [(row.name, "required" if row.required else "optional", "found" if row.found else "MISSING",
             row.version or "-", row.purpose, row.where or "-") for row in rows]
    widths = [max(len(line[i]) for line in (head, *body)) for i in range(len(head) - 1)]
    lines = ["  ".join(cell.ljust(width) for cell, width in zip(line, widths)) + "  " + line[-1]
             for line in (head, *body)]
    missing = [f"  {row.name}: {row.get}" for row in rows if not row.found]
    if missing:
        lines += ["", "To get what is missing:", *missing]
    verdict = ("Everything required is here." if all_required_present(rows)
               else "Something required is missing: get it as shown above, then run `channel92 setup` again.")
    return "\n".join([*lines, "", verdict])


__all__ = ["Context", "NAMES", "Row", "all_required_present", "check_rows", "default_context", "ping_comfyui",
           "run_version", "table"]
