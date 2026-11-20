"""One pinned download, with the standard library only. HTTPS only (a test source may allow plain HTTP on
127.0.0.1), from the source's hosts only, redirects included; no credentials in the address and none sent; a
timeout on every read. The bytes go to a partial file that is checked for size, then sha256, against the pin; on any
mismatch or failure the partial file is deleted and FetchError says what was expected and what came.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .pins import Pin, Source

TIMEOUT_S = 60
CHUNK = 1 << 20
USER_AGENT = "channel92-setup"
STEPS = 10


class FetchError(RuntimeError):
    """The download was refused or failed; nothing of it is kept."""


def check_url(url: str, source: Source) -> str:
    """URL if it is HTTPS (or HTTP for a test source), on one of SOURCE's hosts, with no user or password in it."""
    parts = urlsplit(url)
    schemes = ("https",) if source.https_only else ("https", "http")
    if parts.scheme not in schemes:
        raise FetchError(f"refused {url}: only {' or '.join(schemes)} downloads are allowed")
    if parts.username is not None or parts.password is not None:
        raise FetchError("refused an address with a user name or password in it; the kit sends no credentials")
    if (parts.hostname or "").lower() not in source.hosts:
        raise FetchError(f"refused {url}: {parts.hostname} is not one of the pinned hosts "
                         f"({', '.join(sorted(source.hosts))})")
    return url


class _Guarded(HTTPRedirectHandler):
    """Follows a redirect only to an address `check_url` accepts."""

    def __init__(self, source: Source) -> None:
        super().__init__()
        self.source = source

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl, self.source)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _progress(out: Callable[[str], None], size: int) -> Callable[[int], None]:
    shown = {"step": 0}

    def show(done: int) -> None:
        step = done * STEPS // size if size else STEPS
        if step > shown["step"]:
            shown["step"] = step
            out(f"  downloaded {done / 1e6:.1f} of {size / 1e6:.1f} MB ({step * 100 // STEPS}%)")
    return show


def _stream(answer, partial: Path, pin: Pin, out: Callable[[str], None]) -> tuple[int, str]:
    digest, done, show = hashlib.sha256(), 0, _progress(out, pin.size)
    with partial.open("wb") as file:
        while chunk := answer.read(CHUNK):
            done += len(chunk)
            if done > pin.size:
                raise FetchError(f"wrong size for {pin.asset}: expected {pin.size} bytes, got more than that")
            digest.update(chunk)
            file.write(chunk)
            show(done)
    return done, digest.hexdigest()


def _verify(pin: Pin, size: int, sha256: str) -> None:
    if size != pin.size:
        raise FetchError(f"wrong size for {pin.asset}: expected {pin.size} bytes, got {size}")
    if sha256 != pin.sha256:
        raise FetchError(f"sha256 mismatch for {pin.asset}: expected {pin.sha256}, got {sha256}")


def download(source: Source, pin: Pin, partial: Path, *, out: Callable[[str], None] = print,
             timeout_s: float = TIMEOUT_S) -> Path:
    """Fetch PIN's asset from SOURCE into PARTIAL, verified (size, then sha256); FetchError otherwise, PARTIAL gone."""
    url = check_url(source.url(pin.asset), source)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    partial = Path(partial)
    try:
        with build_opener(_Guarded(source)).open(request, timeout=timeout_s) as answer:
            check_url(answer.geturl(), source)
            size, sha256 = _stream(answer, partial, pin, out)
        _verify(pin, size, sha256)
    except HTTPError as problem:
        partial.unlink(missing_ok=True)
        raise FetchError(f"{url}: HTTP {problem.code} {problem.reason}") from None
    except (URLError, OSError) as problem:
        partial.unlink(missing_ok=True)
        raise FetchError(f"{url}: the download failed ({problem})") from None
    except FetchError:
        partial.unlink(missing_ok=True)
        raise
    return partial


__all__ = ["FetchError", "TIMEOUT_S", "check_url", "download"]
