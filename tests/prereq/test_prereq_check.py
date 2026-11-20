"""`channel92 setup` with no flags only checks: one row per prerequisite (found or missing, version, where, what it
is for, how to get it), exit 0 when every required one is there."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

from atomic_flix.cli import main
from atomic_flix.prereq import check, places
from atomic_flix.prereq.check import NAMES, all_required_present, check_rows, default_context, table


def _context(*, programs=("ffmpeg", "ffprobe"), ntsc=True, blender=True, comfy=True, platform="linux"):
    def which(name):
        return Path(f"/usr/bin/{name}") if name in programs else None

    def find_ntsc():
        return (Path("/kit/tools/ntsc-rs/0.9.7/bin/ntsc-rs-cli"), "kit tools folder") if ntsc else (None, "")

    def find_blender():
        if not blender:
            raise FileNotFoundError("Blender not found")
        return Path("/opt/blender/blender")

    return dataclasses.replace(
        default_context(), which=which, find_ntsc=find_ntsc, find_blender=find_blender, platform=platform,
        version_of=lambda path, args: f"{Path(path).name} version 9.9",
        ping=lambda: ["127.0.0.1:8188 (Test GPU, 24 GB)"] if comfy else [])


def test_every_prerequisite_has_a_row():
    rows = check_rows(context=_context())
    assert tuple(row.name for row in rows) == NAMES
    assert NAMES == ("python", "numpy", "ffmpeg", "ffprobe", "ntsc-rs", "blender", "comfyui", "pillow")
    required = {row.name for row in rows if row.required}
    assert required == {"python", "numpy", "ffmpeg", "ffprobe", "ntsc-rs"}
    for row in rows:
        assert row.purpose and row.get


def test_everything_present_is_ok_and_the_table_says_where_and_what_for():
    rows = check_rows(context=_context())
    assert all_required_present(rows)
    text = table(rows)
    for words in ("python", "ffmpeg version 9.9", "/usr/bin/ffprobe", "kit tools folder", "scenes", "shoot",
                  "127.0.0.1:8188", "found", "optional", "required"):
        assert words.replace("/", "\\") in text or words in text, words


@pytest.mark.parametrize("platform,command", [("linux", "apt install ffmpeg"), ("win32", "winget install Gyan.FFmpeg"),
                                              ("darwin", "brew install ffmpeg")])
def test_a_missing_ffmpeg_says_the_exact_command_for_the_system(platform, command):
    rows = check_rows(context=_context(programs=("ffprobe",), platform=platform))
    ffmpeg = next(row for row in rows if row.name == "ffmpeg")
    assert not ffmpeg.found and command in ffmpeg.get
    assert not all_required_present(rows)
    assert command in table(rows)


def test_a_missing_ntsc_rs_points_at_setup_install():
    rows = check_rows(context=_context(ntsc=False))
    row = next(row for row in rows if row.name == "ntsc-rs")
    assert not row.found and "channel92 setup --install" in row.get
    assert not all_required_present(rows)


def test_blender_comfyui_and_pillow_are_optional_and_never_installed_by_the_kit():
    rows = check_rows(context=_context(blender=False, comfy=False))
    assert all_required_present(rows)
    blender = next(row for row in rows if row.name == "blender")
    comfy = next(row for row in rows if row.name == "comfyui")
    assert not blender.found and "blender.org" in blender.get and "never" in blender.get
    assert not comfy.found and "ComfyUI" in comfy.get and "never" in comfy.get


def test_only_narrows_the_rows():
    rows = check_rows(only="ffmpeg", context=_context())
    assert [row.name for row in rows] == ["ffmpeg"]


def test_python_and_numpy_are_read_from_this_interpreter():
    rows = {row.name: row for row in check_rows(context=_context())}
    assert rows["python"].found and rows["python"].version.startswith(f"{sys.version_info[0]}.")
    assert rows["numpy"].found and rows["numpy"].version


@pytest.mark.parametrize("line,version", [
    ("ffmpeg version 8.0.1-full_build-www.gyan.dev Copyright (c) 2000-2025", "8.0.1-full_build-www.gyan.dev"),
    ("Blender 5.2.3 LTS", "Blender 5.2.3 LTS"), ("ntsc-rs-cli 0.9.7", "ntsc-rs-cli 0.9.7")])
def test_the_version_column_keeps_the_version_only(line, version):
    assert check.short_version(line) == version


def test_the_ping_never_reaches_off_this_machine(monkeypatch):
    monkeypatch.setenv("ATOMIC_FLIX_HOSTS", "example.com:8188")
    assert check.ping_comfyui(timeout_s=0.2) == []


def test_setup_exit_codes(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv(places.HOME_ENV, str(tmp_path / "home"))
    monkeypatch.setattr(check, "default_context", lambda: _context())
    assert main(["setup"]) == 0
    out = capsys.readouterr().out
    assert all(name in out for name in NAMES)
    monkeypatch.setattr(check, "default_context", lambda: _context(programs=("ffprobe",)))
    assert main(["setup"]) != 0
    monkeypatch.setattr(check, "default_context", lambda: _context(blender=False, comfy=False))
    assert main(["setup"]) == 0
    assert main(["setup", "--only", "blender"]) == 0                   # optional: missing is not a failure
    assert main(["setup", "--only", "nonsense"]) == 2
