"""Where a packet's files go: numbered in send order inside the packet folder, each under the cap, never outside the
film folder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..cut.media import MediaError
from . import encode
from .reply import DeskError

IMAGE, AUDIO, VIDEO, TEXT = "image", "audio", "video", "text"


@dataclass(frozen=True)
class PacketFile:
    """One file to send: its place in the order, its name in the packet folder, what it is, and its size."""

    order: int
    file: str
    caption: str
    bytes: int
    kind: str
    group: str

    def to_dict(self) -> dict:
        return {"order": self.order, "file": self.file, "caption": self.caption, "bytes": self.bytes,
                "kind": self.kind, "group": self.group}


def inside(root: Path, relative: str | Path, what: str = "") -> Path:
    """ROOT/RELATIVE, refused (DeskError) when it resolves outside the film folder."""
    base = Path(root).resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base):
        raise DeskError(f"{what or relative} is outside the film folder; a packet only carries the film's own "
                        "files and writes only inside it")
    return path


class Sink:
    """Collects one packet's files in send order (a builder, used by one build only)."""

    def __init__(self, folder: Path, cap: int, work: Path) -> None:
        self.folder = folder
        self.cap = cap
        self.work = work                # a scratch folder of this build's own (tempfile.mkdtemp in the packet folder)
        self.files: list[PacketFile] = []
        self.notes: list[str] = []

    def _path(self, stem: str, suffix: str) -> Path:
        return self.folder / f"{len(self.files) + 1:02d}-{stem}{suffix}"

    def _add(self, path: Path, kind: str, caption: str, group: str) -> None:
        self.files.append(PacketFile(len(self.files) + 1, path.name, caption, path.stat().st_size, kind, group))

    def picture(self, stem: str, picture: np.ndarray, caption: str, group: str, *, png: bool = False) -> None:
        path = self._path(stem, ".png" if png else ".jpg")
        try:
            encode.picture_file(path, picture, self.cap)
        except MediaError as problem:
            raise DeskError(f"{path.name}: {problem}") from None
        self._add(path, IMAGE, caption, group)

    def text(self, stem: str, text: str, caption: str, group: str) -> None:
        path = self._path(stem, ".md")
        encode.text_file(path, text, self.cap)
        self._add(path, TEXT, caption, group)

    def audio(self, stem: str, samples: np.ndarray, rate: int, caption: str, group: str) -> None:
        path = self._path(stem, ".m4a")
        try:
            encode.audio_file(path, samples, rate, self.cap, self.work)
        except MediaError as problem:
            raise DeskError(f"{path.name}: {problem}") from None
        self._add(path, AUDIO, caption, group)

    def video(self, stem: str, source: Path, caption: str, group: str) -> None:
        path = self._path(stem, ".mp4")
        try:
            encode.video_file(path, source, self.cap)
        except MediaError as problem:
            raise DeskError(f"{path.name}: {problem}") from None
        self._add(path, VIDEO, caption, group)
