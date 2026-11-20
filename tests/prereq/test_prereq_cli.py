"""`channel92 setup --install [--yes]` from the command line: without --yes and without a terminal nothing is
downloaded; with --yes the pinned tool goes into CHANNEL92_HOME; the second run does nothing. One test, marked
`network`, fetches the real pinned asset; it is skipped unless CHANNEL92_NETWORK_TESTS=1."""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import io
import os
import sys
from pathlib import Path

import pytest

from atomic_flix.cli import main
from atomic_flix.finish import ntsc
from atomic_flix.prereq import check, fetch, install, pins, places
from prereq_stub import ASSET, bundle, pin_of, serving

PLATFORM = "windows" if os.name == "nt" else "linux"


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    base = tmp_path / "home"
    monkeypatch.setenv(places.HOME_ENV, str(base))
    monkeypatch.delenv(ntsc.ENV, raising=False)
    present = dataclasses.replace(check.default_context(), which=lambda name: Path(f"/usr/bin/{name}"),
                                  version_of=lambda path, args: "9.9", ping=lambda: [],
                                  find_blender=lambda: Path("/opt/blender"))
    monkeypatch.setattr(check, "default_context", lambda: present)
    return base


@pytest.fixture
def stubbed(home, monkeypatch):
    data = bundle()
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        bound = functools.partial(install.install_ntsc_rs, source=stub.source(), pins={PLATFORM: pin_of(data)},
                                  platform=PLATFORM, probe=lambda program: (True, "usage"))
        monkeypatch.setattr(install, "install_ntsc_rs", bound)
        yield stub


def test_without_yes_and_without_a_terminal_nothing_is_downloaded(stubbed, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("yes\n"))            # not a terminal: never read as an answer
    assert main(["setup", "--install"]) != 0
    assert stubbed.requests == []
    assert "--yes" in capsys.readouterr().out
    assert places.installed_ntsc_rs() is None


def test_the_null_device_is_not_a_terminal(stubbed, monkeypatch, capsys):
    with open(os.devnull, "r", encoding="utf-8") as null:             # on Windows NUL says isatty() is true
        monkeypatch.setattr(sys, "stdin", null)
        assert main(["setup", "--install"]) != 0
    assert stubbed.requests == [] and "--yes" in capsys.readouterr().out


def test_with_yes_it_installs_and_the_check_then_passes(stubbed, home, capsys):
    assert main(["setup", "--install", "--yes"]) == 0
    program = places.installed_ntsc_rs()
    assert program is not None and program.is_relative_to(home)
    out = capsys.readouterr().out
    assert str(program) in out and "GPL-3.0" in out
    assert main(["setup", "--install", "--yes"]) == 0
    assert "already installed" in capsys.readouterr().out
    assert len(stubbed.requests) == 1


def test_install_only_for_a_program_the_kit_cannot_fetch_says_so(stubbed, capsys):
    assert main(["setup", "--install", "--only", "ffmpeg"]) == 0
    assert stubbed.requests == []
    assert "cannot install ffmpeg" in capsys.readouterr().out


def test_yes_without_install_is_refused(home, capsys):
    assert main(["setup", "--yes"]) == 2


@pytest.mark.network
@pytest.mark.skipif(os.environ.get("CHANNEL92_NETWORK_TESTS") != "1",
                    reason="downloads the real pinned ntsc-rs asset; set CHANNEL92_NETWORK_TESTS=1")
def test_the_real_pinned_asset_downloads_and_matches_its_hash(tmp_path):
    pin = pins.NTSC_RS_PINS["linux"]                                   # the smaller of the two zips
    got = fetch.download(pins.NTSC_RS_SOURCE, pin, tmp_path / "real.partial", out=lambda line: None)
    digest = hashlib.sha256(got.read_bytes()).hexdigest()
    assert got.stat().st_size == pin.size and digest == pin.sha256
