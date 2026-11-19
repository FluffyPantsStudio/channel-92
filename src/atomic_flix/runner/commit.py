"""How much more memory the system can commit before loads start failing.

What has killed our ComfyUI servers is the commit limit (RAM plus page file), not VRAM: each big model load commits
tens of GB of host memory. Headroom here is commit limit minus committed bytes, in GB.

Sources, in order:
1. Windows: `GetPerformanceInfo` from psapi (the same numbers as the `\\Memory\\Committed Bytes` and
   `\\Memory\\Commit Limit` performance counters). A system-managed page file can grow later, so this is the
   headroom right now, which is the cautious reading.
2. Linux: `CommitLimit` and `Committed_AS` from /proc/meminfo. With overcommit on, Linux rarely enforces this
   limit, so the figure is a rough guide there.
3. The environment variable `ATOMIC_FLIX_COMMIT_HEADROOM_GB`, for a machine where neither works or to override.
4. Nothing: headroom unknown. The scheduler then allows one heavy load at a time.
"""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

GB = 2 ** 30
ENV_HEADROOM = "ATOMIC_FLIX_COMMIT_HEADROOM_GB"


@dataclass(frozen=True)
class CommitInfo:
    committed_gb: float
    limit_gb: float
    provenance: str

    @property
    def headroom_gb(self) -> float:
        return self.limit_gb - self.committed_gb


def _windows() -> CommitInfo | None:
    size_t = ctypes.c_size_t

    class PerformanceInformation(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_uint32), ("commit_total", size_t), ("commit_limit", size_t),
                    ("commit_peak", size_t), ("physical_total", size_t), ("physical_available", size_t),
                    ("system_cache", size_t), ("kernel_total", size_t), ("kernel_paged", size_t),
                    ("kernel_nonpaged", size_t), ("page_size", size_t), ("handle_count", ctypes.c_uint32),
                    ("process_count", ctypes.c_uint32), ("thread_count", ctypes.c_uint32)]

    info = PerformanceInformation()
    info.cb = ctypes.sizeof(info)
    try:
        ok = ctypes.WinDLL("psapi").GetPerformanceInfo(ctypes.byref(info), info.cb)
    except (OSError, AttributeError):
        return None
    if not ok:
        return None
    page = info.page_size
    return CommitInfo(info.commit_total * page / GB, info.commit_limit * page / GB, "windows")


def _linux(meminfo: Path = Path("/proc/meminfo")) -> CommitInfo | None:
    try:
        fields = {}
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            name, _, rest = line.partition(":")
            fields[name.strip()] = float(rest.split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    if "CommitLimit" not in fields or "Committed_AS" not in fields:
        return None
    return CommitInfo(fields["Committed_AS"] / GB, fields["CommitLimit"] / GB, "linux")


def read_commit() -> CommitInfo | None:
    """Committed and limit in GB from the operating system, or None when it cannot be read."""
    if sys.platform == "win32":
        return _windows()
    return _linux()


def headroom_gb(reader: Callable[[], CommitInfo | None] = read_commit) -> float | None:
    """Commit headroom in GB: the system's figure, else the environment override, else None (unknown)."""
    info = reader()
    if info is not None:
        return info.headroom_gb
    text = os.environ.get(ENV_HEADROOM, "").strip()
    try:
        return float(text) if text else None
    except ValueError:
        return None
