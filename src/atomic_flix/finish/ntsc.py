"""Running ntsc-rs, the analog-video emulator, from its own command line. We only run it: it is never bundled or
linked into the kit. `channel92 setup --install` fetches the pinned build into the kit tools folder with the
person's yes (`prereq/`, docs/third-party.md); `finish` itself never downloads anything.

Where it is found, in order: the path given (`finish --ntsc-rs PATH`), the environment variable CHANNEL92_NTSC_RS,
the kit tools folder (the newest finished install, `prereq/places.py`), then `ntsc-rs-cli` on the real PATH (never
the current directory, `programs.py`). A path given either way that is not a file, or one inside a film folder,
stops `finish` (the person asked for that program); only the last two may find nothing, and then the film is
finished without the look. The command, as ntsc-rs v0.9.7's CLI reads it
(crates/gui/src/bin/ntsc-rs-cli.rs):

    ntsc-rs-cli -i IN -o OUT.mkv -p PRESET.json -y -c ffv1 --scale LINES

`-y` overwrites without the interactive question; `-c ffv1` writes lossless FFV1 in Matroska, so the one lossy
encode stays ours; `--scale LINES` resizes the picture to that many lines before the effect, as ntsc-rs advises
for results that look right (the final encode scales back to the film's size). `scale_lines` picks LINES so the
frame's short side gets the era's lines: a portrait frame keeps 480 across instead of being cut to 270.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..prereq.places import installed_ntsc_rs
from ..programs import ProgramError, checked, command_of, find_program

ENV = "CHANNEL92_NTSC_RS"
PROGRAM = "ntsc-rs-cli"
RELEASES = "https://github.com/ntsc-rs/ntsc-rs/releases"
LOSSLESS = "ffv1"
ERROR_TAIL = 600
_which = find_program


class NtscError(RuntimeError):
    """ntsc-rs cannot run as asked, or ran and failed; the message says which."""


def _named(path: Path | str, how: str) -> Path:
    if not Path(path).is_file():
        raise NtscError(f"{how} names {path}, and there is no file there: fix the path, or leave it out to look for "
                        f"{PROGRAM} on the PATH")
    try:
        return checked(path, PROGRAM)
    except ProgramError as problem:
        raise NtscError(str(problem)) from None


def locate_ntsc_rs(given: Path | str | None = None) -> tuple[Path | None, str]:
    """The ntsc-rs-cli to run and how it was found: GIVEN ("--ntsc-rs"), else CHANNEL92_NTSC_RS, else the kit tools
    folder's newest finished install ("kit tools folder"), else the PATH's ("PATH"); (None, "") when none is found.
    NtscError when GIVEN or CHANNEL92_NTSC_RS names no file, or one inside a film folder. Never downloads."""
    if given:
        return _named(given, "--ntsc-rs"), "--ntsc-rs"
    named = os.environ.get(ENV)
    if named:
        return _named(named, ENV), ENV
    installed = installed_ntsc_rs()
    if installed is not None:
        return _named(installed, "the kit tools folder"), "kit tools folder"
    try:
        found = _which(PROGRAM)
    except ProgramError as problem:
        raise NtscError(str(problem)) from None
    return (found, "PATH") if found is not None else (None, "")


def find_ntsc_rs(given: Path | str | None = None) -> Path | None:
    """The ntsc-rs-cli to run (`locate_ntsc_rs`), or None when there is none anywhere."""
    return locate_ntsc_rs(given)[0]


def missing_sentence(era_id: str) -> str:
    """The one plain sentence `finish` says when no ntsc-rs is found."""
    return (f"ntsc-rs-cli was not found (no --ntsc-rs, no {ENV}, none in the kit tools folder or on the PATH), so "
            f"the film is finished without the {era_id} look; run `channel92 setup --install` to fetch the pinned "
            f"build ({RELEASES}), or pass --ntsc-rs PATH or set {ENV}, to run it next time")


def scale_lines(lines: int, width: int, height: int) -> int:
    """The --scale (the picture's height in lines) that gives a WIDTHxHEIGHT frame's short side LINES."""
    return int(round(lines * height / min(width, height)))


def ntsc_command(program: Path, source: Path, out: Path, preset: Path, lines: int) -> list[str]:
    return [str(program), "-i", str(source), "-o", str(out), "-p", str(preset), "-y", "-c", LOSSLESS,
            "--scale", str(int(lines))]


def run_ntsc_rs(program: Path, source: Path, out: Path, preset: Path, lines: int) -> Path:
    """Run ntsc-rs on SOURCE into OUT (lossless) with --scale LINES; NtscError when it fails or writes nothing."""
    try:
        command = command_of(ntsc_command(program, source, out, preset, lines))
    except ProgramError as problem:
        raise NtscError(str(problem)) from None
    done = subprocess.run(command, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0 or not Path(out).is_file():
        said = (done.stderr or done.stdout or "").strip()[-ERROR_TAIL:]
        raise NtscError(f"ntsc-rs failed (exit {done.returncode}): {said or 'it wrote no output'}")
    return Path(out)


__all__ = ["ENV", "NtscError", "PROGRAM", "RELEASES", "find_ntsc_rs", "locate_ntsc_rs", "missing_sentence",
           "ntsc_command", "run_ntsc_rs", "scale_lines"]
