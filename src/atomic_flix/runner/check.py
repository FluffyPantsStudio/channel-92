"""`ping`: confirm every ComfyUI host answers with its GPU, ffmpeg and ffprobe are on PATH, and Python reads and
writes UTF-8 (on Windows the default code page garbles lyrics). Only reads; never queues anything."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Callable

from ..programs import find_program
from .comfy import ComfyClient, ComfyError
from .commit import headroom_gb


@dataclass(frozen=True)
class CheckReport:
    ok: bool
    lines: tuple[str, ...]


def check_hosts(hosts: list[str], *, which: Callable[[str], object] = find_program,
                utf8_mode: bool | None = None, windows: bool | None = None, timeout_s: float = 10.0,
                headroom: Callable[[], float | None] = headroom_gb, allow_remote: bool = False) -> CheckReport:
    lines: list[str] = []
    ok = True
    for host in hosts:
        try:
            name, vram = ComfyClient(host, timeout_s, allow_remote=allow_remote).gpu(timeout_s)
            lines.append(f"ok   {host}: {name}, {vram:.0f} GB")
        except (ComfyError, ValueError) as err:
            ok = False
            lines.append(f"FAIL {host}: {err}")
    for tool in ("ffmpeg", "ffprobe"):
        found = which(tool)
        if found:
            lines.append(f"ok   {tool}: {found}")
        else:
            ok = False
            lines.append(f"FAIL {tool} is not on PATH")
    utf8 = bool(sys.flags.utf8_mode) if utf8_mode is None else utf8_mode
    on_windows = (os.name == "nt") if windows is None else windows
    if on_windows and not utf8:
        ok = False
        lines.append("FAIL Python is not in UTF-8 mode: set PYTHONUTF8=1 (setx PYTHONUTF8 1, then a new terminal)")
    else:
        lines.append("ok   Python text is UTF-8")
    room = headroom()
    lines.append(f"info commit headroom: {room:.0f} GB" if room is not None
                 else "info commit headroom: unknown (one heavy load at a time)")
    return CheckReport(ok, tuple(lines))
