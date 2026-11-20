"""The optional intro: a clip joined in front of the cut, scaled and padded to its frame, its sound laid out like
the film's (silence when the intro has none), so the joined file's sound is as long as both pictures."""

from __future__ import annotations

import subprocess

import pytest

from atomic_flix.brand import join_intro
from atomic_flix.cut.media import probe

FPS = 24


def _clip(path, size: str, seconds: float, sound: bool, pattern: str = "testsrc2") -> object:
    source = f"{pattern}=size={size}:rate={FPS}:duration={seconds}"
    command = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", source]
    if sound:
        command += ["-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=44100:duration={seconds}",
                    "-c:a", "aac", "-ac", "1"]
    command += ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-shortest", str(path)]
    subprocess.run(command, check=True)
    return path


def _audio_seconds(path) -> float:
    done = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration",
                           "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(done.stdout.strip())


def _audio_layout(path) -> str:
    done = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                           "stream=sample_rate,channels", "-of", "csv=p=0", str(path)], capture_output=True,
                          text=True, check=True)
    return done.stdout.strip()


@pytest.fixture
def cut(tmp_path):
    film = tmp_path / "v01.mp4"
    command = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"smptebars=size=320x180:rate={FPS}:duration=3",
               "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3", "-ac", "2",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(film)]
    subprocess.run(command, check=True)
    return film


@pytest.mark.parametrize("sound", [False, True], ids=["silent-intro", "intro-with-sound"])
def test_the_intro_join_keeps_the_audio_as_long_as_both_pictures(tmp_path, cut, sound):
    intro = _clip(tmp_path / "intro.mp4", "200x200", 1.5, sound)
    out = join_intro(intro, cut, tmp_path / "v01-intro.mp4")
    joined = probe(out)
    assert (joined.width, joined.height) == (320, 180)
    assert joined.frames == 36 + 72
    assert _audio_seconds(out) == pytest.approx(4.5, abs=0.05)
    assert _audio_layout(out) == _audio_layout(cut)


def test_the_cut_is_left_as_it_was(tmp_path, cut):
    before = cut.read_bytes()
    join_intro(_clip(tmp_path / "intro.mp4", "640x360", 1.0, False), cut, tmp_path / "joined.mp4")
    assert cut.read_bytes() == before
