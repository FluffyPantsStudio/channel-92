"""External programs are found once on the real PATH, never in the current directory or a film folder, and are
launched by their absolute path (on Windows a bare name runs a program from the current directory first)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from atomic_flix import programs
from atomic_flix.programs import ProgramError, command_of, find_program, guard_film


def _tool(folder: Path, name: str) -> Path:
    """A do-nothing program called NAME in FOLDER (NAME.exe on Windows)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (f"{name}.exe" if os.name == "nt" else name)
    path.write_bytes(b"")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(programs, "_FOUND", {})
    monkeypatch.setattr(programs, "_FILM_ROOTS", set())


def test_the_current_directory_is_never_searched(tmp_path, monkeypatch, fresh):
    here, real = tmp_path / "here", tmp_path / "real"
    _tool(here, "fftool")
    wanted = _tool(real, "fftool")
    monkeypatch.chdir(here)
    monkeypatch.setenv("PATH", os.pathsep.join([str(here), ".", "", str(real)]))
    assert find_program("fftool") == wanted
    assert Path(command_of(["fftool", "-v"])[0]) == wanted and command_of(["fftool", "-v"])[1:] == ["-v"]


def test_a_relative_path_entry_is_skipped(tmp_path, monkeypatch, fresh):
    _tool(tmp_path / "rel", "fftool")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "rel")
    assert find_program("fftool") is None
    with pytest.raises(ProgramError, match="fftool"):
        command_of(["fftool"])


@pytest.mark.skipif(os.name != "nt", reason="PATHEXT is a Windows rule")
def test_pathext_is_honoured_on_windows(tmp_path, monkeypatch, fresh):
    script = tmp_path / "bin" / "fftool.CMD"
    script.parent.mkdir()
    script.write_text("@echo off\r\n", encoding="utf-8")
    monkeypatch.setenv("PATH", str(script.parent))
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    assert find_program("fftool") == script


def test_a_program_inside_a_film_folder_is_refused(tmp_path, monkeypatch, fresh):
    film = tmp_path / "films" / "one"
    planted = _tool(film / "bin", "fftool")
    monkeypatch.setenv("PATH", str(planted.parent))
    guard_film(film)
    with pytest.raises(ProgramError, match="film folder"):
        find_program("fftool")
    with pytest.raises(ProgramError, match="film folder"):
        command_of([str(planted)])


def test_a_named_program_is_found_once(tmp_path, monkeypatch, fresh):
    wanted = _tool(tmp_path / "bin", "fftool")
    monkeypatch.setenv("PATH", str(wanted.parent))
    assert find_program("fftool") == wanted
    wanted.unlink()
    assert find_program("fftool") == wanted          # cached for this PATH


def test_the_kit_launches_ffmpeg_by_its_absolute_path(tmp_path, monkeypatch):
    from atomic_flix.cut import media
    seen = []
    real = media.subprocess.run
    monkeypatch.setattr(media.subprocess, "run", lambda command, **kw: seen.append(command) or real(command, **kw))
    picture = tmp_path / "a.png"
    import numpy as np
    media.write_image(picture, np.zeros((8, 8, 3), np.uint8))
    media.probe(picture)
    assert len(seen) == 2 and all(Path(command[0]).is_absolute() for command in seen)
