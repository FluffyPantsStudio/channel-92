"""The cut stays clean: no logo, no look and no intro go into it (they are `finish`'s, tests/finish/), so the grade
never sees them. The cut is exactly the edit's own render, whatever film.json `brand` says."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from atomic_flix.cli import main
from atomic_flix.cut import load_edit, render_cut
from atomic_flix.cut.media import read_frames, write_video
from atomic_flix.cut.render import ffmpeg_command_for_test
from cutclips import make_tone

FPS, WIDTH, HEIGHT = 24, 320, 176
SHOTS = "A1 cutaway\n  beat: a red field\n\nB1 cutaway\n  beat: a blue field\n"


def _field(path: Path, colour) -> Path:
    frames = np.empty((96, HEIGHT, WIDTH, 3), np.uint8)
    frames[:] = np.array(colour, np.uint8)
    return write_video(path, frames, FPS, crf=10)


@pytest.fixture
def film(tmp_path) -> Path:
    folder = tmp_path / "films" / "clean-cut"
    assert main(["new", str(folder), "--aspect", "16:9", "--by", "Test", "--words", "wide", "--year", "1987"]) == 0
    data = json.loads((folder / "film.json").read_text(encoding="utf-8"))
    data.update({"frame": [WIDTH, HEIGHT], "final_size": [WIDTH, HEIGHT], "brand": {"logo": True, "intro": "era"}})
    (folder / "film.json").write_text(json.dumps(data), encoding="utf-8")
    (folder / "shots.txt").write_text(SHOTS, encoding="utf-8")
    make_tone(folder / "audio" / "mix.wav", seconds=4.0)
    cuts = [{"key": "A1", "at": 0.0, "grid": "one"}, {"key": "B1", "at": 1.5, "grid": "one"}]
    (folder / "plan" / "cuts.json").write_text(json.dumps({"cuts": cuts}), encoding="utf-8")
    for key, at, colour in (("A1", 0.0, (200, 40, 40)), ("B1", 1.5, (40, 40, 200))):
        task = {"key": key, "slice_start": at - 0.5, "shown_at": [at, at + 1.5]}
        (folder / "plan" / f"{key}.task.json").write_text(json.dumps(task), encoding="utf-8")
        (folder / "renders" / key).mkdir(parents=True)
        _field(folder / "renders" / key / "r001.mp4", colour)
        fit = {"how": "sound", "map": [[at, 0.5]]}
        (folder / "renders" / key / "r001.fit.json").write_text(json.dumps(fit), encoding="utf-8")
    return folder


def test_the_cut_is_the_edits_own_render_with_no_logo_and_no_intro(film, tmp_path):
    assert main(["cut", str(film), "--speed", "ultrafast"]) == 0
    spec = json.loads((film / "cuts" / "v01.edit.json").read_text(encoding="utf-8"))
    assert "logo" not in spec
    reference = tmp_path / "reference.mp4"
    edit = load_edit(film / "cuts" / "v01.edit.json")
    render_cut(edit, reference, x264_speed="ultrafast")
    assert np.array_equal(read_frames(film / "cuts" / "v01.mp4"), read_frames(reference))
    _decode, encode = ffmpeg_command_for_test(edit, tmp_path / "x.mp4")
    assert "-filter_complex" not in encode
    assert sorted(p.name for p in (film / "cuts").glob("*.mp4")) == ["v01.mp4"]
    assert not (film / "brand").exists()


def test_the_cut_no_longer_takes_a_logo_flag(film, capsys):
    with pytest.raises(SystemExit):
        main(["cut", str(film), "--no-logo"])
    assert "--no-logo" in capsys.readouterr().err
