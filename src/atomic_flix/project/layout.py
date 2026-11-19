"""Where everything of one film lives on disk.

    <film-slug>/
      film.json      the film: stems, lyric, singer, shot list, picks (the core spec's shape)
      lyric.txt      the lyric as sung, repeats written out
      notes.md       the person's words at every gate, word for word
      standing.json  where the film stands: the gates, review rounds, the song's fingerprint, the record
      job-log.jsonl   one line per GPU job, written by the runner (docs/job-log.md)
      audio/ refs/ stills/ analysis/ plan/ renders/ cuts/ review/ deliver/ cache/
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

FILM_FILE = "film.json"
LYRIC_FILE = "lyric.txt"
NOTES_FILE = "notes.md"
STANDING_FILE = "standing.json"
JOB_LOG_FILE = "job-log.jsonl"

FOLDERS: tuple[tuple[str, str], ...] = (
    ("audio", "the song and its stems: mix, voice, band, drums, choir"),
    ("refs", "portraits and outfit references the person approved"),
    ("stills", "one first frame per shot, with <key>.json saying how it was made"),
    ("analysis", "line times, beats and swells; made again from audio and the lyric"),
    ("plan", "cuts and one task per shot with its gated voice; made again from analysis"),
    ("renders", "renders/<key>/r001.mp4 with its job and fit files"),
    ("cuts", "assembled films v01.mp4, v02.mp4 ... and their tone and flash reports"),
    ("review", "review/v01/: sheets and each cold reviewer's list"),
    ("final_size", "parts that leave the machine, with a list of times"),
    ("cache", "decoded frames and measurements; safe to delete"),
)

FOLDER_NAMES: tuple[str, ...] = tuple(name for name, _ in FOLDERS)


@dataclass(frozen=True)
class FilmFolder:
    """Paths inside one film's folder. Nothing here touches the disk."""

    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root))

    @property
    def film(self) -> Path:
        return self.root / FILM_FILE

    @property
    def lyric(self) -> Path:
        return self.root / LYRIC_FILE

    @property
    def notes(self) -> Path:
        return self.root / NOTES_FILE

    @property
    def standing(self) -> Path:
        return self.root / STANDING_FILE

    @property
    def job_log(self) -> Path:
        return self.root / JOB_LOG_FILE

    def folder(self, name: str) -> Path:
        if name not in FOLDER_NAMES:
            raise KeyError(f"no folder {name!r} in a film; the folders are {', '.join(FOLDER_NAMES)}")
        return self.root / name

    def still(self, key: str) -> Path:
        return self.root / "stills" / f"{key}.png"

    def take_file(self, key: str, number: int) -> Path:
        return self.root / "renders" / key / f"r{number:03d}.mp4"

    def cut(self, version: int) -> Path:
        return self.root / "cuts" / f"v{version:02d}.mp4"

    def relative(self, path: Path) -> str:
        """PATH as written inside the film, with forward slashes."""
        try:
            return Path(path).relative_to(self.root).as_posix()
        except ValueError:
            return Path(path).as_posix()
