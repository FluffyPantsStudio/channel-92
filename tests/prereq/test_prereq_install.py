"""`channel92 setup --install`: the pinned ntsc-rs goes into the per-user kit tools folder (CHANNEL92_HOME here),
only after the person's yes, verified before it is kept; a second run does nothing; and `finish` then finds it."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from atomic_flix.finish import ntsc
from atomic_flix.prereq import install, pins, places
from atomic_flix.prereq.install import install_ntsc_rs
from prereq_stub import ASSET, PROGRAM, bundle, pin_of, serving, zip_bytes

PLATFORM = "windows" if os.name == "nt" else "linux"


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    base = tmp_path / "home"
    monkeypatch.setenv(places.HOME_ENV, str(base))
    monkeypatch.delenv(ntsc.ENV, raising=False)
    return base


def _run(stub, data: bytes, *, yes=True, ask=None, probe=None, lines=None):
    said = [] if lines is None else lines
    probed = probe or (lambda program: (True, "usage: ntsc-rs-cli"))
    return install_ntsc_rs(yes=yes, ask=ask, out=said.append, source=stub.source(),
                           pins={PLATFORM: pin_of(data)}, platform=PLATFORM, probe=probed), said


def _only_the_tools_root(home: Path) -> list[str]:
    return sorted(str(path.relative_to(home)).replace("\\", "/") for path in home.rglob("*"))


def test_the_kit_tools_folder_is_per_user_and_outside_the_repo(monkeypatch, tmp_path):
    monkeypatch.delenv(places.HOME_ENV, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert places.tools_home(platform="win32") == tmp_path / "local" / "Channel92" / "tools"
    assert places.tools_home(platform="linux") == Path.home() / ".local" / "share" / "channel92" / "tools"
    assert places.tools_home(platform="darwin") == (Path.home() / "Library" / "Application Support" / "Channel92"
                                                    / "tools")
    monkeypatch.setenv(places.HOME_ENV, str(tmp_path / "base"))
    assert places.tools_home(platform="win32") == tmp_path / "base" / "tools"
    assert places.ntsc_rs_folder() == tmp_path / "base" / "tools" / "ntsc-rs" / "0.9.7"


def test_with_yes_it_installs_verified_and_says_where(home):
    data = bundle()
    probed: list[Path] = []
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        code, said = _run(stub, data, probe=lambda program: (probed.append(program) or True, "usage"))
    assert code == 0
    program = places.installed_ntsc_rs()
    assert program is not None and program.name == PROGRAM
    assert program.is_relative_to(home / "tools" / "ntsc-rs" / "0.9.7")
    assert program.parent.name == "bin"                            # found by walking, not by a fixed path
    assert len(probed) == 1 and probed[0].name == PROGRAM          # it ran --help before it was kept
    text = "\n".join(said)
    assert str(program) in text
    for words in (ASSET, stub.source().url(ASSET), "GPL-3.0", "separate program", str(len(data))):
        assert words in text
    leftovers = [path for path in home.rglob("*") if "partial" in path.name]
    assert leftovers == []


def test_the_plan_is_printed_before_anything_is_downloaded(home):
    data = bundle()
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        code, said = _run(stub, data, yes=False, ask=None)
        assert stub.requests == []
    assert code != 0
    text = "\n".join(said)
    assert ASSET in text and "--yes" in text and str(places.ntsc_rs_folder()) in text
    assert places.installed_ntsc_rs() is None
    assert _only_the_tools_root(home) in ([], ["tools"], ["tools", "tools/ntsc-rs"])


def test_a_typed_yes_at_a_terminal_installs_and_anything_else_does_not(home):
    data = bundle()
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        code, _ = _run(stub, data, yes=False, ask=lambda question: "no")
        assert code != 0 and stub.requests == []
        code, _ = _run(stub, data, yes=False, ask=lambda question: " YES ")
        assert code == 0 and len(stub.requests) == 1
    assert places.installed_ntsc_rs() is not None


def test_an_answer_cut_short_is_not_a_yes(home):
    def closed(question):
        raise EOFError
    data = bundle()
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        code, _ = _run(stub, data, yes=False, ask=closed)
        assert code != 0 and stub.requests == []


def test_a_second_run_is_a_no_op(home):
    data = bundle()
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        assert _run(stub, data)[0] == 0
        code, said = _run(stub, data)
        assert len(stub.requests) == 1                                 # nothing fetched the second time
    assert code == 0 and "already installed" in "\n".join(said)


def test_a_hash_mismatch_installs_nothing_and_leaves_nothing(home):
    data = bundle()
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        lines: list[str] = []
        code = install_ntsc_rs(yes=True, ask=None, out=lines.append, source=stub.source(),
                               pins={PLATFORM: pins.Pin(ASSET, len(data), "f" * 64)}, platform=PLATFORM,
                               probe=lambda program: (True, ""))
    assert code != 0
    assert "f" * 64 in "\n".join(lines) and pin_of(data).sha256 in "\n".join(lines)
    assert places.installed_ntsc_rs() is None
    assert [path for path in home.rglob("*") if path.is_file()] == []


def test_an_archive_escaping_its_folder_installs_nothing_and_leaves_nothing(home):
    data = zip_bytes({f"bin/{PROGRAM}": b"x", "../../evil.txt": b"x"})
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        code, said = _run(stub, data)
    assert code != 0 and places.installed_ntsc_rs() is None
    assert [path for path in home.rglob("*") if path.is_file()] == []
    assert not (home.parent / "evil.txt").exists() and not (home / "tools" / "evil.txt").exists()


def test_an_archive_without_the_program_installs_nothing(home):
    data = zip_bytes({"bundle/README.txt": b"x"})
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        code, said = _run(stub, data)
    assert code != 0 and "ntsc-rs-cli" in "\n".join(said)
    assert [path for path in home.rglob("*") if path.is_file()] == []


def test_a_program_that_does_not_run_is_not_kept(home):
    data = bundle()
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        code, said = _run(stub, data, probe=lambda program: (False, "exit 1: cannot start"))
    assert code != 0 and "cannot start" in "\n".join(said)
    assert places.installed_ntsc_rs() is None
    assert [path for path in home.rglob("*") if path.is_file()] == []


def test_macos_is_told_the_manual_step_and_nothing_is_downloaded(home):
    with serving({}) as stub:
        lines: list[str] = []
        code = install_ntsc_rs(yes=True, ask=None, out=lines.append, source=stub.source(), platform="macos",
                               probe=lambda program: (True, ""))
        assert stub.requests == []
    text = "\n".join(lines)
    assert code != 0
    assert pins.NTSC_RS_MACOS.sha256 in text and pins.NTSC_RS_MACOS.asset in text
    assert pins.NTSC_RS_SOURCE.url(pins.NTSC_RS_MACOS.asset) in text


def test_finish_finds_the_installed_tool(home):
    data = bundle()
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        assert _run(stub, data)[0] == 0
    assert ntsc.find_ntsc_rs() == places.installed_ntsc_rs()


def test_the_newest_installed_version_wins(home):
    newest, older = home / "tools" / "ntsc-rs" / "0.9.10", home / "tools" / "ntsc-rs" / "0.9.9"
    for folder in (older, newest):
        program = folder / "bin" / PROGRAM
        program.parent.mkdir(parents=True)
        program.write_bytes(b"x")
        places.write_marker(folder, {"version": folder.name, "program": f"bin/{PROGRAM}"})
    (home / "tools" / "ntsc-rs" / "1.0.0").mkdir()                 # no marker: not a finished install
    assert places.installed_ntsc_rs() == (newest / "bin" / PROGRAM).resolve()       # 0.9.10 is newer than 0.9.9


def test_find_ntsc_rs_order_given_then_env_then_tools_then_path(home, tmp_path, monkeypatch):
    def program(folder: Path) -> Path:
        path = folder / PROGRAM
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return path.resolve()

    given, named, on_path = program(tmp_path / "given"), program(tmp_path / "env"), program(tmp_path / "path")
    installed = home / "tools" / "ntsc-rs" / "0.9.7"
    program(installed / "bin")
    places.write_marker(installed, {"version": "0.9.7", "program": f"bin/{PROGRAM}"})
    monkeypatch.setattr(ntsc, "_which", lambda name: on_path)
    monkeypatch.setenv(ntsc.ENV, str(named))
    assert ntsc.find_ntsc_rs(given) == given
    assert ntsc.find_ntsc_rs() == named
    monkeypatch.delenv(ntsc.ENV)
    assert ntsc.find_ntsc_rs() == (installed / "bin" / PROGRAM).resolve()
    assert ntsc.locate_ntsc_rs()[1] == "kit tools folder"
    places.marker_path(installed).unlink()
    assert ntsc.find_ntsc_rs() == on_path
    monkeypatch.setattr(ntsc, "_which", lambda name: None)
    assert ntsc.find_ntsc_rs() is None


def test_the_missing_sentence_says_to_run_setup_install():
    line = ntsc.missing_sentence("1980s")
    assert "channel92 setup --install" in line and line.count(". ") == 0


def test_finish_never_downloads(home, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("finish must not download")
    monkeypatch.setattr(install, "install_ntsc_rs", refuse)
    monkeypatch.setattr("atomic_flix.prereq.fetch.download", refuse)
    monkeypatch.setattr(ntsc, "_which", lambda name: None)
    assert ntsc.find_ntsc_rs() is None
