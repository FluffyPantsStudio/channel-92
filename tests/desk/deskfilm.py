"""A small synthetic film for the desk tests: a real mix, the analysis files, stills, a shot list with plan tasks,
a budget, a cut and its review sheets, and helpers that walk the gates up to the one under test."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from atomic_flix.cli import main
from atomic_flix.cut.media import write_image, write_video
from atomic_flix.gates import Answer
from atomic_flix.project import answer_gate, ask_gate, review_cut
from atomic_flix.wav import save_wav

AT = "2026-11-20T10:00:00+00:00"
PERSON = "Test Person"
GATES = ("concept", "song", "looks", "board", "spend", "v1")
SONG_S = 6.0
BEATS = [round(0.25 + 0.5 * i, 3) for i in range(11)]
SHOWN = {"concept": ["pitches.md", "plan/structure.md"], "song": ["audio/mix.wav"],
         "looks": ["stills/S01.png", "stills/N01.png"], "board": ["plan/board.html"],
         "spend": ["plan/report.md", "plan/budget.json"], "v1": ["cuts/v01.mp4"]}
PITCHES = "# Pitch A\n\nThe moon rides a bicycle. Is it lonely?\n"
STRUCTURE = {
    "song_s": SONG_S,
    "sections": [
        {"id": "s01", "label": "Intro", "kind": "instrumental", "start": 0.0, "end": 2.0, "lines": []},
        {"id": "s02", "label": "Verse 1", "kind": "sung", "start": 2.0, "end": 4.5, "lines": ["L1"]},
        {"id": "s03", "label": "Outro", "kind": "mixed", "start": 4.5, "end": SONG_S, "lines": ["L2"]},
    ],
    "pacing": {"story_gaps": [{"rank": 1, "id": "s01", "label": "Intro", "start": 0.0, "end": 2.0,
                               "duration_s": 2.0}]},
}
LINES = {"lines": [{"id": "L1", "part": "lead", "text": "Hello there, moon", "start": 2.0, "end": 3.0},
                   {"id": "L2", "part": "lead", "text": "Oh oh", "start": 3.2, "end": 4.4}]}
SHOT_KEYS = ("S01", "N01", "N02", "N03", "N04", "N05", "N06", "N07")


def picture(width: int, height: int, seed: int = 1) -> np.ndarray:
    """A smooth colour picture that JPEG keeps small."""
    y, x = np.mgrid[0:height, 0:width]
    shade = (np.sin(x / (17 + seed)) + np.cos(y / 23)) * 40
    return np.stack([110 + shade, 90 + shade * 0.5, 140 - shade], axis=-1).clip(0, 255).astype(np.uint8)


def _mix(path: Path) -> Path:
    t = np.arange(int(SONG_S * 44100)) / 44100
    tone = 0.2 * np.sin(2 * np.pi * 220 * t)
    return save_wav(path, np.stack([tone, tone], axis=1), 44100)


def _shot_list() -> str:
    rows = ["S01 vocal: L1\n  still: stills/S01.png\n"]
    rows += [f"{key} cutaway\n  at: {4.5 + 0.1 * n:.1f}\n  beat: the moon rises\n"
             for n, key in enumerate(SHOT_KEYS[1:])]
    return "\n".join(rows)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _plan(film: Path) -> None:
    for n, key in enumerate(SHOT_KEYS):
        start = 2.0 if key == "S01" else 4.5 + 0.1 * (n - 1)
        _write_json(film / "plan" / f"{key}.task.json", {"key": key, "shown_at": [start, start + 0.1]})
        (film / "plan" / f"{key}.prompt.txt").write_text("a quiet street at night\n", encoding="utf-8")
        write_image(film / "stills" / f"{key}.png", picture(640, 360, n))
    (film / "plan" / "board.html").write_text("<html></html>", encoding="utf-8")
    (film / "plan" / "report.md").write_text("report\n", encoding="utf-8")
    _write_json(film / "plan" / "budget.json", {"takes": 4, "size": [1280, 704], "busy_s": 3600.0,
                                                "gpu_hours": 1.0, "basis": "the first film's rates"})


def _cut(film: Path) -> None:
    frames = np.stack([picture(1280, 720, n % 5) for n in range(24)])
    write_video(film / "cuts" / "v01.mp4", frames, 24, x264_speed="ultrafast")
    for n in (1, 2):
        write_image(film / "review" / "v01" / f"0{n}-S01-strip.jpg", picture(900, 300, n))


def make_film(tmp_path: Path) -> Path:
    """A film folder with everything every gate's packet reads."""
    mix = _mix(tmp_path / "inputs" / "mix.wav")
    film = tmp_path / "films" / "moon-song"
    assert main(["new", str(film), "--song", str(mix), "--aspect", "16:9", "--by", PERSON, "--words", "wide"]) == 0
    _write_json(film / "analysis" / "structure.json", STRUCTURE)
    _write_json(film / "analysis" / "pulse.json", {"beats": BEATS, "downbeat_slot": 1, "ones": BEATS[1::4]})
    _write_json(film / "analysis" / "voice-lines.json", LINES)
    (film / "pitches.md").write_text(PITCHES, encoding="utf-8")
    (film / "plan").mkdir(exist_ok=True)
    (film / "plan" / "structure.md").write_text("# Structure\n", encoding="utf-8")
    (film / "shots.txt").write_text(_shot_list(), encoding="utf-8")
    _plan(film)
    write_image(film / "stills" / "S01.png", picture(2000, 1125, 0))     # larger than a phone screen
    _cut(film)
    return film


def ask_up_to(film: Path, gate: str, shown: list[str] | None = None) -> None:
    """Pass every gate before GATE with a plain yes, then ask GATE (the eval hook is off in these tests)."""
    for earlier in GATES[:GATES.index(gate)]:
        ask_gate(film, earlier, SHOWN[earlier], at=AT)
        answer_gate(film, earlier, Answer(words="yes", by=PERSON, provenance="person", at=AT))
    if gate == "v1":
        review_cut(film, (shown or SHOWN["v1"])[0], "cold-reader-1", [], at=AT)
    ask_gate(film, gate, shown or SHOWN[gate], at=AT)
