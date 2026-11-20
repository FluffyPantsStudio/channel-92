"""The one program the kit fetches itself, pinned: ntsc-rs v0.9.7's standalone builds, by the size and sha256 this
table holds (never trusted on first use), from the project's own GitHub release over HTTPS. macOS ships only an
installer package, which the kit does not install: `setup --install` prints its address, hash and the manual step.

ntsc-rs's command line is GPL-3.0. The kit installs it as a separate program in a per-user folder and only runs it;
it is never bundled into the kit or a release of it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

NTSC_RS = "ntsc-rs"
NTSC_RS_VERSION = "0.9.7"
NTSC_RS_LICENCE = "GPL-3.0"
GITHUB_HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})


@dataclass(frozen=True)
class Pin:
    """One release asset: its file name, its size in bytes and its sha256 (lower-case hex)."""

    asset: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Source:
    """Where assets come from: BASE_URL/ASSET, from these HOSTS only (redirects included), HTTPS unless a test says
    otherwise."""

    base_url: str
    hosts: frozenset[str]
    https_only: bool = True

    def url(self, asset: str) -> str:
        return f"{self.base_url.rstrip('/')}/{asset}"


NTSC_RS_SOURCE = Source(f"https://github.com/ntsc-rs/ntsc-rs/releases/download/v{NTSC_RS_VERSION}", GITHUB_HOSTS)
NTSC_RS_PINS: Mapping[str, Pin] = MappingProxyType({
    "windows": Pin("ntsc-rs-windows-standalone.zip", 77630964,
                   "4f19c6f424058e8c516687126e5b63fcc44d07daa89e75911adb494c9e8874e6"),
    "linux": Pin("ntsc-rs-linux-standalone.zip", 14568231,
                 "968fdb21d1d34d53004e7f822d941ba6a93b1cce067e492d2095f071d43567d1"),
})
NTSC_RS_MACOS = Pin("ntsc-rs-macos-standalone.pkg", 90556245,
                    "51ca362a9ce8b40cb47804959cbbdc5bb71e79c0f334542dd85fa27faa04c1e0")


def platform_key(name: str | None = None) -> str:
    """"windows", "linux", "macos" or "other" for a sys.platform value (this machine's by default)."""
    name = sys.platform if name is None else name
    if name.startswith("win"):
        return "windows"
    if name.startswith("linux"):
        return "linux"
    return "macos" if name == "darwin" else "other"


__all__ = ["GITHUB_HOSTS", "NTSC_RS", "NTSC_RS_LICENCE", "NTSC_RS_MACOS", "NTSC_RS_PINS", "NTSC_RS_SOURCE",
           "NTSC_RS_VERSION", "Pin", "Source", "platform_key"]
