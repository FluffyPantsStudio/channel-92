"""Test helpers for `channel92 setup`: tiny zip bundles and a local HTTP stub on 127.0.0.1 standing in for the
release host. Nothing here touches the real network."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import threading
import zipfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

from atomic_flix.prereq.pins import Pin, Source

PROGRAM = "ntsc-rs-cli.exe" if os.name == "nt" else "ntsc-rs-cli"
ASSET = "ntsc-rs-test-standalone.zip"


def zip_bytes(entries: dict[str, bytes], *, executable: tuple[str, ...] = (), symlinks: dict[str, str] | None = None
              ) -> bytes:
    """A zip holding ENTRIES (name to bytes); names in EXECUTABLE get mode 0755, SYMLINKS are link entries."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name)
            mode = 0o755 if name in executable else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, data)
        for name, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, target)
    return buffer.getvalue()


def bundle() -> bytes:
    """A stand-in for the standalone bundle: the program sits two folders down, as in the real one."""
    program = f"ntsc-rs-test-standalone/bin/{PROGRAM}"
    return zip_bytes({"ntsc-rs-test-standalone/README.txt": b"stand-in\n", program: b"not a real program\n"},
                     executable=(program,))


def pin_of(data: bytes, asset: str = ASSET) -> Pin:
    return Pin(asset, len(data), hashlib.sha256(data).hexdigest())


class Stub:
    """A local release host: ROUTES maps a path to ("data", bytes) or ("redirect", url); REQUESTS lists paths asked."""

    def __init__(self, routes: dict[str, tuple[str, object]]) -> None:
        self.routes = dict(routes)
        self.requests: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.server: ThreadingHTTPServer | None = None

    @property
    def base(self) -> str:
        assert self.server is not None
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def source(self, hosts: tuple[str, ...] = ("127.0.0.1",)) -> Source:
        return Source(f"{self.base}/download", frozenset(hosts), https_only=False)


def _handler(stub: Stub):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (the standard library's name)
            stub.requests.append(self.path)
            stub.headers.append({key.lower(): value for key, value in self.headers.items()})
            kind, value = stub.routes.get(self.path, ("missing", b""))
            if kind == "redirect":
                self.send_response(302)
                self.send_header("Location", str(value))
                self.end_headers()
                return
            if kind != "data":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(value)))
            self.end_headers()
            self.wfile.write(value)

        def log_message(self, *args):
            pass
    return Handler


@contextmanager
def serving(routes: dict[str, tuple[str, object]]) -> Iterator[Stub]:
    stub = Stub(routes)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(stub))
    stub.server = server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield stub
    finally:
        server.shutdown()
        server.server_close()
