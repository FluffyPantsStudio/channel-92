"""Unpacking a verified zip into an empty folder, safely. Every entry is checked before anything is written; the
whole archive is refused when one entry is an absolute path, carries a drive letter or any colon, climbs with `..`,
is a link, or would resolve outside the folder, or when the archive is larger than a tool bundle can be. On POSIX an
entry stored as executable keeps its executable bit (and nothing more: no setuid, no world-writable files).
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import zipfile
from pathlib import Path

MAX_ENTRIES = 20_000
MAX_BYTES = 2 * 2 ** 30
DRIVE = re.compile(r"^[A-Za-z]:")


class UnpackError(RuntimeError):
    """The archive was refused; nothing of it was written."""


def _mode(info: zipfile.ZipInfo) -> int:
    return (info.external_attr >> 16) & 0xFFFF


def _target(info: zipfile.ZipInfo, root: Path) -> Path:
    name = info.filename
    parts = re.split(r"[\\/]", name)
    if not name or "\x00" in name or name[0] in "/\\" or DRIVE.match(name) or ":" in name:
        raise UnpackError(f"refused the archive: the entry {name!r} is an absolute path or names a drive")
    if ".." in parts:
        raise UnpackError(f"refused the archive: the entry {name!r} climbs out with '..'")
    if stat.S_ISLNK(_mode(info)):
        raise UnpackError(f"refused the archive: the entry {name!r} is a link")
    target = root.joinpath(*[part for part in parts if part not in ("", ".")]).resolve()
    if not target.is_relative_to(root) or target == root and not info.is_dir():
        raise UnpackError(f"refused the archive: the entry {name!r} would land outside {root}")
    return target


def check_entries(archive: zipfile.ZipFile, root: Path) -> list[tuple[zipfile.ZipInfo, Path]]:
    """Each entry with where it goes under ROOT; UnpackError for the first entry that may not be written."""
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES or sum(info.file_size for info in infos) > MAX_BYTES:
        raise UnpackError(f"refused the archive: over {MAX_ENTRIES} entries or {MAX_BYTES} bytes unpacked")
    return [(info, _target(info, root)) for info in infos]


def _write(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> Path:
    if info.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(info) as source, target.open("wb") as file:
        shutil.copyfileobj(source, file)
    if os.name != "nt" and _mode(info) & 0o111:
        target.chmod(0o755)
    return target


def unpack_zip(archive_path: Path, dest: Path) -> list[Path]:
    """Unpack ARCHIVE_PATH into DEST (missing or empty); the paths written. UnpackError, with nothing written,
    when the archive is unreadable or any entry may not be written."""
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise UnpackError(f"refused to unpack into {dest}: it already holds files")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            planned = check_entries(archive, dest.resolve())
            dest.mkdir(parents=True, exist_ok=True)
            return [_write(archive, info, target) for info, target in planned]
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as problem:
        raise UnpackError(f"refused the archive: it is not a readable zip ({problem})") from None


__all__ = ["UnpackError", "check_entries", "unpack_zip"]
