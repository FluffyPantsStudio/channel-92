"""The per-user kit tools folder, outside every repo and every film folder:

    Windows  %LOCALAPPDATA%\\Channel92\\tools
    Linux    ~/.local/share/channel92/tools
    macOS    ~/Library/Application Support/Channel92/tools

CHANNEL92_HOME replaces the base (then the tools live in $CHANNEL92_HOME/tools). A tool lives in
tools/NAME/VERSION; an install is finished only when its marker file is there, written last, after the download
was verified and the program ran. `installed_ntsc_rs` returns the newest finished install's program.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Iterator, Mapping

from .pins import NTSC_RS, NTSC_RS_VERSION, platform_key

HOME_ENV = "CHANNEL92_HOME"
MARKER = "channel92-install.json"


def tools_home(platform: str | None = None, env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get(HOME_ENV):
        return Path(env[HOME_ENV]) / "tools"
    key = platform_key(platform)
    if key == "windows":
        local = env.get("LOCALAPPDATA")
        return (Path(local) if local else Path.home() / "AppData" / "Local") / "Channel92" / "tools"
    if key == "macos":
        return Path.home() / "Library" / "Application Support" / "Channel92" / "tools"
    return Path.home() / ".local" / "share" / "channel92" / "tools"


def ntsc_rs_folder(version: str = NTSC_RS_VERSION) -> Path:
    return tools_home() / NTSC_RS / version


def program_name(platform: str | None = None) -> str:
    return "ntsc-rs-cli.exe" if platform_key(platform) == "windows" else "ntsc-rs-cli"


def find_program_in(folder: Path, name: str | None = None) -> Path | None:
    """The shallowest file called NAME (ntsc-rs-cli by default) under FOLDER, by walking it; links are not followed."""
    wanted = (name or program_name()).lower()
    found = [Path(root) / file for root, _, files in os.walk(folder) for file in files if file.lower() == wanted]
    return min(found, key=lambda path: (len(path.parts), str(path))) if found else None


def marker_path(folder: Path) -> Path:
    return Path(folder) / MARKER


def write_marker(folder: Path, record: Mapping[str, object]) -> Path:
    path = marker_path(folder)
    path.write_text(json.dumps(dict(record), indent=2) + "\n", encoding="utf-8")
    return path


def read_marker(folder: Path) -> dict | None:
    try:
        record = json.loads(marker_path(folder).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def finished_program(folder: Path) -> Path | None:
    """The program a finished install in FOLDER recorded, if its marker is there and the program sits inside FOLDER."""
    record = read_marker(folder)
    relative = record.get("program") if record else None
    if not isinstance(relative, str) or not relative:
        return None
    root = Path(folder).resolve()
    program = (root / relative).resolve()
    return program if program.is_relative_to(root) and program.is_file() else None


def _version_key(name: str) -> tuple[int, ...] | None:
    parts = name.split(".")
    return tuple(int(part) for part in parts) if all(part.isdigit() for part in parts) else None


def _versions(tool_folder: Path) -> Iterator[Path]:
    """TOOL_FOLDER's version folders, newest first (folders not named like 0.9.7 are left out)."""
    try:
        children = [child for child in tool_folder.iterdir() if child.is_dir() and _version_key(child.name)]
    except OSError:
        return iter(())
    return iter(sorted(children, key=lambda child: _version_key(child.name), reverse=True))


def installed_ntsc_rs() -> Path | None:
    """The newest finished ntsc-rs install's program in the kit tools folder, or None."""
    return next((program for folder in _versions(tools_home() / NTSC_RS)
                 if (program := finished_program(folder)) is not None), None)


__all__ = ["HOME_ENV", "MARKER", "find_program_in", "finished_program", "installed_ntsc_rs", "marker_path",
           "ntsc_rs_folder", "program_name", "read_marker", "tools_home", "write_marker"]
