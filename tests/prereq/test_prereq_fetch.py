"""The download and the unpacking behind `channel92 setup --install`: the shipped table is HTTPS from GitHub only,
every download is checked for size and then sha256 against the kit's own table, and an archive entry that would
land outside the destination is refused before anything is written."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from atomic_flix.prereq import fetch, pins, unpack
from atomic_flix.prereq.fetch import FetchError, check_url, download
from atomic_flix.prereq.unpack import UnpackError, unpack_zip
from prereq_stub import ASSET, bundle, pin_of, serving, zip_bytes


def test_the_shipped_table_is_pinned_https_github_only():
    source = pins.NTSC_RS_SOURCE
    assert source.https_only
    assert source.base_url == "https://github.com/ntsc-rs/ntsc-rs/releases/download/v0.9.7"
    assert source.hosts == {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
    assert pins.NTSC_RS_VERSION == "0.9.7"
    windows, linux = pins.NTSC_RS_PINS["windows"], pins.NTSC_RS_PINS["linux"]
    assert (windows.asset, windows.size, windows.sha256) == (
        "ntsc-rs-windows-standalone.zip", 77630964,
        "4f19c6f424058e8c516687126e5b63fcc44d07daa89e75911adb494c9e8874e6")
    assert (linux.asset, linux.size, linux.sha256) == (
        "ntsc-rs-linux-standalone.zip", 14568231,
        "968fdb21d1d34d53004e7f822d941ba6a93b1cce067e492d2095f071d43567d1")
    assert set(pins.NTSC_RS_PINS) == {"windows", "linux"}           # macOS ships a .pkg the kit never installs
    assert pins.NTSC_RS_MACOS.asset.endswith(".pkg") and pins.NTSC_RS_MACOS.size == 90556245
    assert pins.NTSC_RS_MACOS.sha256 == "51ca362a9ce8b40cb47804959cbbdc5bb71e79c0f334542dd85fa27faa04c1e0"
    for pin in (windows, linux, pins.NTSC_RS_MACOS):
        url = source.url(pin.asset)
        assert urlsplit(url).scheme == "https" and urlsplit(url).hostname == "github.com"
        assert check_url(url, source) == url


@pytest.mark.parametrize("url", ["http://github.com/ntsc-rs/x.zip", "https://example.com/x.zip",
                                 "https://user:secret@github.com/x.zip", "file:///etc/passwd",
                                 "ftp://github.com/x.zip", "https://github.com.evil.example/x.zip"])
def test_urls_off_the_pinned_hosts_or_not_https_are_refused(url):
    with pytest.raises(FetchError):
        check_url(url, pins.NTSC_RS_SOURCE)


def test_a_download_matching_the_table_is_kept(tmp_path):
    data = bundle()
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        lines: list[str] = []
        got = download(stub.source(), pin_of(data), tmp_path / "a.partial", out=lines.append)
    assert got.read_bytes() == data
    assert any("100%" in line for line in lines)
    assert "authorization" not in stub.headers[0] and "cookie" not in stub.headers[0]


def test_a_hash_mismatch_is_refused_and_the_partial_file_deleted(tmp_path):
    data = bundle()
    wrong = pins.Pin(ASSET, len(data), "0" * 64)
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        with pytest.raises(FetchError) as refused:
            download(stub.source(), wrong, tmp_path / "a.partial", out=lambda line: None)
    said = str(refused.value)
    assert "0" * 64 in said and pin_of(data).sha256 in said                    # expected and got
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("size_change", [-1, 1])
def test_a_wrong_size_is_refused_and_the_partial_file_deleted(tmp_path, size_change):
    data = bundle()
    pin = pins.Pin(ASSET, len(data) + size_change, pin_of(data).sha256)
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        with pytest.raises(FetchError) as refused:
            download(stub.source(), pin, tmp_path / "a.partial", out=lambda line: None)
    assert str(pin.size) in str(refused.value)
    assert list(tmp_path.iterdir()) == []


def test_a_redirect_to_a_host_off_the_list_is_refused(tmp_path):
    data = bundle()
    with serving({"/download/" + ASSET: ("data", data)}) as stub:
        stub.routes["/download/" + ASSET] = ("redirect", f"http://localhost:{stub.server.server_address[1]}/x")
        with pytest.raises(FetchError, match="localhost"):
            download(stub.source(), pin_of(data), tmp_path / "a.partial", out=lambda line: None)
    assert "/x" not in stub.requests
    assert list(tmp_path.iterdir()) == []


def test_a_redirect_to_a_listed_host_is_followed(tmp_path):
    data = bundle()
    with serving({"/download/" + ASSET: ("redirect", "/assets/blob"), "/assets/blob": ("data", data)}) as stub:
        got = download(stub.source(), pin_of(data), tmp_path / "a.partial", out=lambda line: None)
    assert got.read_bytes() == data and stub.requests == ["/download/" + ASSET, "/assets/blob"]


def test_a_missing_asset_is_refused_plainly(tmp_path):
    data = bundle()
    with serving({}) as stub:
        with pytest.raises(FetchError, match="404"):
            download(stub.source(), pin_of(data), tmp_path / "a.partial", out=lambda line: None)
    assert list(tmp_path.iterdir()) == []


def test_the_download_has_a_timeout():
    assert 0 < fetch.TIMEOUT_S <= 120


def _archive(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "archive.zip"
    path.write_bytes(data)
    return path


def test_a_clean_archive_unpacks_and_keeps_the_executable_bit(tmp_path):
    archive = _archive(tmp_path, bundle())
    dest = tmp_path / "dest"
    written = unpack_zip(archive, dest)
    program = next(path for path in written if path.name.startswith("ntsc-rs-cli"))
    assert program.read_bytes() == b"not a real program\n"
    if os.name != "nt":
        assert os.access(program, os.X_OK)


@pytest.mark.parametrize("entries,links", [
    ({"../escape.txt": b"x"}, None),
    ({"inside/../../escape.txt": b"x"}, None),
    ({"/abs/escape.txt": b"x"}, None),
    ({"C:" + "/escape.txt": b"x"}, None),                         # split: no drive path in the public tree
    ({"C:escape.txt": b"x"}, None),
    ({"..\\escape.txt": b"x"}, None),
    ({"ok.txt": b"x"}, {"link": "/etc/passwd"}),
])
def test_an_archive_with_an_entry_outside_the_destination_or_a_link_is_refused_whole(tmp_path, entries, links):
    archive = _archive(tmp_path, zip_bytes({"first.txt": b"x", **entries}, symlinks=links))
    dest = tmp_path / "dest"
    with pytest.raises(UnpackError):
        unpack_zip(archive, dest)
    assert not dest.exists() or list(dest.rglob("*")) == []                     # nothing was written
    assert sorted(path.name for path in tmp_path.iterdir()) in (["archive.zip"], ["archive.zip", "dest"])


def test_an_archive_into_a_folder_that_holds_files_is_refused(tmp_path):
    archive = _archive(tmp_path, bundle())
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "keep.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(UnpackError):
        unpack.unpack_zip(archive, dest)
    assert [path.name for path in dest.iterdir()] == ["keep.txt"]
