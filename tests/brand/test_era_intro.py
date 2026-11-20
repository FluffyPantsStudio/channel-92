"""The era intros: a silent clip of a few seconds per era, made by ffmpeg alone at the film's own frame size, that
reveals the era's logo over the era's own background; made once per size and kept in the film's brand/ folder."""

from __future__ import annotations

import json
import subprocess

import numpy as np
import pytest

from atomic_flix.brand.era_intro import INTRO_SECONDS, build_era_intro, era_intro
from atomic_flix.cut.media import probe, read_frames
from atomic_flix.eras import ERAS

FPS = 24
ASPECT_SIZES = {"16:9": (320, 180), "4:3": (240, 180), "9:16": (180, 320)}


def _has_audio(path) -> bool:
    done = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
                          capture_output=True, text=True, check=True)
    return any(s["codec_type"] == "audio" for s in json.loads(done.stdout)["streams"])


def test_an_intro_runs_four_to_six_seconds():
    assert 4.0 <= INTRO_SECONDS <= 6.0


@pytest.mark.parametrize("aspect", list(ASPECT_SIZES))
@pytest.mark.parametrize("row", ERAS, ids=[row.id for row in ERAS])
def test_each_era_intro_has_the_films_frame_and_length_and_no_sound(tmp_path, row, aspect):
    width, height = ASPECT_SIZES[aspect]
    out = build_era_intro(row, (width, height), FPS, tmp_path / "intro.mp4")
    clip = probe(out)
    assert (clip.width, clip.height) == (width, height)
    assert clip.frames == round(INTRO_SECONDS * FPS)
    assert clip.fps == pytest.approx(FPS)
    assert not _has_audio(out)


@pytest.mark.parametrize("row", ERAS, ids=[row.id for row in ERAS])
def test_the_logo_is_revealed_not_there_from_the_first_frame(tmp_path, row):
    out = build_era_intro(row, (320, 180), FPS, tmp_path / "intro.mp4")
    frames = read_frames(out).astype(float)
    centre = frames[:, 60:120, 110:210]
    early, held = centre[2], centre[round(3.0 * FPS)]
    assert np.abs(held - early).mean() > 8


def test_the_1950s_intro_is_monochrome(tmp_path):
    out = build_era_intro(ERAS[0], (320, 180), FPS, tmp_path / "intro.mp4")
    frames = read_frames(out).astype(int)
    assert np.abs(frames[..., 0] - frames[..., 2]).mean() < 3


def test_the_intro_is_made_once_per_size_in_the_films_brand_folder(tmp_path):
    film = tmp_path / "film"
    first = era_intro(film, ERAS[3], (320, 180), FPS)
    assert first.parent == film / "brand" and "1980s" in first.name and "320x180" in first.name
    stamp = first.stat().st_mtime_ns
    assert era_intro(film, ERAS[3], (320, 180), FPS) == first and first.stat().st_mtime_ns == stamp
    other = era_intro(film, ERAS[3], (240, 180), FPS)
    assert other != first and probe(other).width == 240


def test_the_kept_intro_is_named_for_the_logo_bytes_and_the_intro_version(tmp_path, monkeypatch):
    import hashlib
    from atomic_flix.brand import era_intro as module
    film = tmp_path / "film"
    row = ERAS[3]
    kept = era_intro(film, row, (320, 180), FPS)
    digest = hashlib.sha256(row.logo.read_bytes()).hexdigest()[:module.LOGO_HASH_CHARS]
    assert digest in kept.name and f"v{module.INTRO_VERSION}" in kept.name
    monkeypatch.setattr(module, "INTRO_VERSION", module.INTRO_VERSION + 1)
    assert era_intro(film, row, (320, 180), FPS) != kept                # a new intro design is made again


def test_an_intro_folder_that_leads_outside_the_film_is_refused(tmp_path):
    from atomic_flix.brand.intro import IntroError
    film, elsewhere = tmp_path / "film", tmp_path / "elsewhere"
    film.mkdir()
    elsewhere.mkdir()
    try:
        (film / "brand").symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("this machine cannot make symbolic links")
    with pytest.raises(IntroError, match="outside the film folder"):
        era_intro(film, ERAS[3], (320, 180), FPS)
    assert list(elsewhere.iterdir()) == []
