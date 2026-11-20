"""`channel92 setup --install`: the pinned ntsc-rs standalone build into the kit tools folder (`places.py`).

It says first what it will do (asset, address, size, destination, licence) and goes on only with --yes or a typed
yes at a terminal. Then: download to a partial file, verified by size and sha256 (`fetch.py`); unpack into a staging
folder beside the destination, safely (`unpack.py`); find ntsc-rs-cli by walking what was unpacked; run it with
--help; write the marker; and only then move the staging folder into place. Any failure removes the partial file and
the staging folder, so a refused or broken download leaves nothing behind. A finished install of the same version
makes it a no-op. macOS ships only an installer package, which the kit never runs: it prints the manual step.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Mapping

from . import places
from .fetch import FetchError, download
from .pins import (NTSC_RS, NTSC_RS_LICENCE, NTSC_RS_MACOS, NTSC_RS_PINS, NTSC_RS_SOURCE, NTSC_RS_VERSION, Pin,
                   Source, platform_key)
from .unpack import UnpackError, unpack_zip

HELP_TIMEOUT_S = 60
Probe = Callable[[Path], "tuple[bool, str]"]
Out = Callable[[str], None]


class InstallError(RuntimeError):
    """The install stopped; nothing of it was kept."""


def run_help(program: Path) -> tuple[bool, str]:
    """Whether PROGRAM --help runs and exits 0, and what it said (its last words when it failed)."""
    try:
        done = subprocess.run([str(program), "--help"], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=HELP_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as problem:
        return False, str(problem)
    said = (done.stdout or done.stderr or "").strip()
    return done.returncode == 0, said if done.returncode == 0 else f"exit {done.returncode}: {said[-400:]}"


def plan_lines(pin: Pin, url: str, dest: Path, version: str) -> list[str]:
    return [f"channel92 setup will install {NTSC_RS} {version}:",
            f"  asset        {pin.asset}",
            f"  from         {url}",
            f"  size         {pin.size} bytes ({pin.size / 1e6:.1f} MB), sha256 {pin.sha256}",
            f"  into         {dest}",
            f"  licence      the {NTSC_RS} command line is {NTSC_RS_LICENCE}; it is installed as a separate program "
            "the kit only runs, never bundled into the kit or a release of it"]


def macos_lines(source: Source = NTSC_RS_SOURCE) -> list[str]:
    return [f"{NTSC_RS} {NTSC_RS_VERSION} for macOS ships only as an installer package, which the kit does not run.",
            f"  get it from  {source.url(NTSC_RS_MACOS.asset)}",
            f"  check it     shasum -a 256 {NTSC_RS_MACOS.asset} must print {NTSC_RS_MACOS.sha256} "
            f"({NTSC_RS_MACOS.size} bytes)",
            "  then         open the package, and point the kit at the installed ntsc-rs-cli with "
            "CHANNEL92_NTSC_RS or --ntsc-rs PATH (or put its folder on the PATH)"]


def _agreed(yes: bool, ask: Callable[[str], str] | None, out: Out) -> bool:
    if yes:
        return True
    if ask is None:
        out("Not downloading: run `channel92 setup --install --yes`, or run it at a terminal and type yes.")
        return False
    try:
        answer = ask("Type yes to download and install it: ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip().lower() == "yes":
        return True
    out("\nNot downloading (the answer was not yes).")
    return False


def _discard(*paths: Path) -> None:
    for path in paths:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def _fetch_and_place(source: Source, pin: Pin, dest: Path, version: str, probe: Probe, out: Out) -> Path:
    """Download, unpack, find, run and record; the program's final path. InstallError (or Fetch/UnpackError)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial, staging = dest.parent / f"{pin.asset}.partial", dest.parent / f".{version}.partial"
    _discard(partial, staging)
    try:
        download(source, pin, partial, out=out)
        out(f"  verified: {pin.size} bytes, sha256 {pin.sha256}")
        unpack_zip(partial, staging)
        program = places.find_program_in(staging)
        if program is None:
            raise InstallError(f"the archive holds no {places.program_name()}")
        if os.name != "nt":
            program.chmod(0o755)
        ran, said = probe(program)
        if not ran:
            raise InstallError(f"{program.name} --help did not run: {said}")
        relative = program.relative_to(staging).as_posix()
        places.write_marker(staging, {"tool": NTSC_RS, "version": version, "asset": pin.asset, "size": pin.size,
                                      "sha256": pin.sha256, "program": relative})
        staging.rename(dest)
        return dest / relative
    finally:
        _discard(partial, staging)


def install_ntsc_rs(*, yes: bool, ask: Callable[[str], str] | None, out: Out = print,
                    source: Source = NTSC_RS_SOURCE, pins: Mapping[str, Pin] = NTSC_RS_PINS,
                    platform: str | None = None, probe: Probe = run_help, version: str = NTSC_RS_VERSION) -> int:
    """Install the pinned ntsc-rs (see the module's words); 0 when it is installed, 1 when not."""
    key = platform if platform in ("windows", "linux", "macos", "other") else platform_key(platform)
    if key == "macos":
        for line in macos_lines():                          # always the real, pinned address
            out(line)
        return 1
    pin = pins.get(key)
    if pin is None:
        out(f"There is no pinned {NTSC_RS} build for this system; get it from {source.base_url} and set "
            "CHANNEL92_NTSC_RS to its ntsc-rs-cli.")
        return 1
    dest = places.ntsc_rs_folder(version)
    installed = places.finished_program(dest)
    if installed is not None and (places.read_marker(dest) or {}).get("sha256") == pin.sha256:
        out(f"{NTSC_RS} {version} is already installed and verified at {installed}; nothing to do.")
        return 0
    if dest.exists():
        out(f"{dest} exists but is not a finished install; remove it and run `channel92 setup --install` again.")
        return 1
    for line in plan_lines(pin, source.url(pin.asset), dest, version):
        out(line)
    if not _agreed(yes, ask, out):
        return 1
    try:
        program = _fetch_and_place(source, pin, dest, version, probe, out)
    except (FetchError, UnpackError, InstallError, OSError) as problem:
        out(f"Not installed: {problem}. Nothing was kept.")
        return 1
    out(f"Installed {NTSC_RS} {version}: {program}")
    return 0


__all__ = ["InstallError", "install_ntsc_rs", "macos_lines", "plan_lines", "run_help"]
