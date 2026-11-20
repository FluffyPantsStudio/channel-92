"""`setup`: the kit's prerequisites. With no flags it only checks and prints the table (`prereq/check.py`); exit 0
when everything required is there. `--install` fetches what the kit can fetch itself, today ntsc-rs only, pinned
and verified (`prereq/install.py`), after saying what it will do and getting --yes or a typed yes at a terminal.
`--only NAME` narrows both to one prerequisite.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, Sequence

from ..prereq import check, install
from .common import parser

FETCHABLE = ("ntsc-rs",)
ABOUT = """Check the kit's prerequisites, and install the one it can fetch itself.

  channel92 setup                    check only: a table of every prerequisite, how to get what is missing
  channel92 setup --install          install ntsc-rs (pinned v0.9.7, verified by size and sha256) into the
                                     per-user kit tools folder; asks first (type yes, or pass --yes)
  channel92 setup --only ffmpeg      just that one

Exit 0 when everything required is present. Blender and ComfyUI are optional and never installed by the kit."""


def _is_console(stream) -> bool:
    """Whether STREAM is a terminal a person types at. On Windows isatty() is also true for the NUL device, so a
    console is told apart by asking for its console mode."""
    try:
        if stream is None or not stream.isatty():
            return False
        if os.name != "nt":
            return True
        import ctypes
        import msvcrt
        mode = ctypes.c_uint32()
        handle = msvcrt.get_osfhandle(stream.fileno())
        return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))
    except (AttributeError, ValueError, OSError):
        return False


def _terminal_question() -> Callable[[str], str] | None:
    """`input` when stdin is a terminal a person can answer at; None otherwise (never read a pipe as a yes)."""
    return input if _is_console(sys.stdin) else None


def _install(only: str | None, yes: bool) -> int:
    if only is not None and only not in FETCHABLE:
        print(f"The kit cannot install {only}; how to get it is in the table below.")
        return 0
    code = install.install_ntsc_rs(yes=yes, ask=_terminal_question(), out=print)
    print()
    return code


def _setup(argv: Sequence[str]) -> int:
    p = parser("setup", ABOUT)
    p.add_argument("--install", action="store_true", help="install what the kit can fetch itself (ntsc-rs)")
    p.add_argument("--yes", action="store_true", help="with --install: agree to the download without being asked")
    p.add_argument("--only", choices=check.NAMES, metavar="NAME", help=f"one of: {', '.join(check.NAMES)}")
    try:
        args = p.parse_args(list(argv))
        if args.yes and not args.install:
            p.error("--yes goes with --install")
    except SystemExit as stop:
        return int(stop.code or 0)
    code = _install(args.only, args.yes) if args.install else 0
    rows = check.check_rows(only=args.only, context=check.default_context())
    print(check.table(rows))
    return code or (0 if check.all_required_present(rows) else 1)


COMMANDS = {
    "setup": ("check the kit's prerequisites; --install fetches the pinned ntsc-rs (asks first)", _setup),
}

__all__ = ["COMMANDS"]
