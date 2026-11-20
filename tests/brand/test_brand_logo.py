"""The Channel 92 logos: the modern mark and the era marks in the package, found by one function, placed in the top
right of every frame."""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

from atomic_flix.aspects import ASPECTS, aspect
from atomic_flix.brand import LOGO_NATIVE, logo_box, logo_file, png_size
from atomic_flix.eras import ERAS
from atomic_flix.scenes.imageio import read_png

REPO = Path(__file__).resolve().parents[2]
MARGIN, WIDTH_SHARE = 0.03, 0.14


def test_the_logo_ships_in_the_package_and_is_found_with_or_without_an_era():
    found = logo_file()
    assert found.is_file() and found.parent.parent.name == "atomic_flix"
    assert png_size(found) == LOGO_NATIVE == (1832, 754)
    assert logo_file(None) == found and logo_file("2000s") == found
    with pytest.raises(TypeError):
        logo_file(1987)


def _colour_type(path: Path) -> int:
    return path.read_bytes()[25]


@pytest.mark.parametrize("era_id", ["1950s", "1960s", "1970s", "1980s", "1990s"])
def test_each_older_era_has_its_own_mark_with_alpha(era_id):
    found = logo_file(era_id)
    assert found != logo_file() and found.name == f"logo-{era_id}.png" and found.parent.name == "eras"
    assert _colour_type(found) == 6                     # RGBA
    width, height = png_size(found)
    assert 600 <= width <= 1200 and height >= 200 and found.stat().st_size < 200_000


LUMA_MARGIN, NEUTRAL_CHROMA, COLOUR_CHROMA, STRIP_GAP_SHARE = 150, 40, 80, 0.05


def test_the_1960s_logo_is_read_by_luma_and_its_colour_sits_below_the_letters():
    """The 1960s look delays colour about 12 px at 480 lines, which slid the old red block off its cream 92 ("922").
    The mark is cream on a near-neutral dark plate, so there is no colour under the letters to move; the colour
    blocks sit in rows of their own below them, so a horizontal smear never crosses a letter."""
    rgba = read_png(logo_file("1960s")).astype(float)
    rgb, alpha = rgba[..., :3], rgba[..., 3]
    luma = rgb @ [0.299, 0.587, 0.114]
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    letters = (alpha > 0) & (luma > 128) & (chroma <= NEUTRAL_CHROMA)
    colour = (alpha > 0) & (chroma > COLOUR_CHROMA)
    rows = np.flatnonzero(letters.any(axis=1))
    top, bottom = rows[0], rows[-1]
    assert colour.any() and np.flatnonzero(colour.any(axis=1))[0] > bottom + STRIP_GAP_SHARE * len(luma)
    band = (slice(top, bottom + 1), slice(None))
    assert chroma[band][alpha[band] > 0].max() <= NEUTRAL_CHROMA          # every letter row is colourless
    plate = (alpha[band] > 0) & (luma[band] < 64)
    assert np.median(luma[band][letters[band]]) - np.median(luma[band][plate]) >= LUMA_MARGIN


def test_the_package_copy_is_the_repo_logo():
    assert logo_file().read_bytes() == (REPO / "assets" / "channel92-logo.png").read_bytes()


@pytest.mark.parametrize("name", ["16:9", "4:3", "2.39:1", "9:16"])
@pytest.mark.parametrize("tier", ["standard", "draft", "delivery"])
def test_the_logo_sits_inside_the_safe_margin_top_right(name, tier):
    row = aspect(name)
    width, height = row.delivery if tier == "delivery" else row.frame(tier)
    x, y, w, h = logo_box(width, height)
    margin = round(MARGIN * width)
    assert w == round(WIDTH_SHARE * width)
    assert abs(h - w * LOGO_NATIVE[1] / LOGO_NATIVE[0]) <= 1
    assert x + w == width - margin and y == margin
    assert x >= width / 2 and y + h <= height / 2


def test_the_logo_is_never_scaled_up_past_its_own_size():
    x, y, w, h = logo_box(16000, 9000)
    assert (w, h) == LOGO_NATIVE
    assert x + w == 16000 - 480 and y == 480


def _python_with_setuptools() -> str | None:
    for candidate in (sys.executable, shutil.which("python"), shutil.which("python3")):
        if candidate and subprocess.run([candidate, "-c", "import setuptools"], capture_output=True).returncode == 0:
            return candidate
    return None


def test_a_built_wheel_carries_the_logo(tmp_path):
    python = _python_with_setuptools()
    if python is None:
        pytest.skip("no Python with setuptools on this machine to build a wheel offline")
    tree = tmp_path / "tree"
    tree.mkdir()
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy(REPO / name, tree / name)
    shutil.copytree(REPO / "src" / "atomic_flix", tree / "src" / "atomic_flix",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    out = tmp_path / "dist"
    done = subprocess.run([python, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--no-index",
                           "-w", str(out), str(tree)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-2000:]
    wheel = next(out.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        entry = archive.read(next(n for n in names if n.endswith("entry_points.txt"))).decode()
    assert "atomic_flix/brand/channel92-logo.png" in names
    for row in ERAS:
        assert f"atomic_flix/looks/{row.id}.json" in names
        if row.id != "2000s":
            assert f"atomic_flix/brand/eras/logo-{row.id}.png" in names
    assert "channel92 = atomic_flix.cli:main" in entry and "atomic-flix = atomic_flix.cli:main" in entry
