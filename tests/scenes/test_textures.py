"""Procedural textures: reproducible, the right size, and they look like what they are named for."""

import numpy as np
import pytest

from atomic_flix.scenes import imageio, textures


@pytest.mark.parametrize("name", sorted(textures.TEXTURES))
def test_every_texture_is_reproducible_rgb(name):
    a = textures.make(name, small=True)
    b = textures.make(name, small=True)
    assert a.dtype == np.uint8 and a.ndim == 3 and a.shape[2] == 3
    assert np.array_equal(a, b)
    assert a.std() > 2, "a flat texture is not a texture"


def test_cabinet_is_a_grid_of_two_by_four_drawers():
    img = textures.make("steel_case").astype(np.float32).mean(axis=2)
    h, w = img.shape
    assert (w, h) == (256, 512)
    # the dark gaps between drawers sit on the cell borders
    col_profile = img.mean(axis=0)
    row_profile = img.mean(axis=1)
    assert col_profile[w // 2 - 2: w // 2 + 2].mean() < col_profile.mean() * 0.8
    for r in range(1, 4):
        y = r * h // 4
        assert row_profile[y - 2: y + 2].mean() < row_profile.mean() * 0.8


def test_dusk_sky_is_warm_at_the_horizon_and_teal_overhead():
    img = textures.make("dusk", small=True).astype(np.float32)
    h = img.shape[0]
    horizon = img[h // 2 - h // 60: h // 2 - 1].mean(axis=(0, 1))
    zenith = img[: h // 8].mean(axis=(0, 1))
    assert horizon[0] > horizon[2]          # red over blue at the horizon
    assert zenith[2] > zenith[0]            # blue over red overhead
    assert np.allclose(img[:, 0], img[:, -1], atol=40)  # wraps sideways without a seam


def test_gingham_has_two_tones_crossing():
    img = textures.make("gingham", small=True).astype(np.float32).mean(axis=2)
    levels = np.unique(np.round(img / 32))
    assert len(levels) >= 3


def test_write_all_to_a_folder(tmp_path):
    written = textures.ensure(["steel_case", "salt"], tmp_path)
    assert set(written) == {"steel_case", "salt"}
    for path in written.values():
        assert imageio.read_png(path).shape[2] == 3
    mtime = written["salt"].stat().st_mtime_ns
    textures.ensure(["salt"], tmp_path)
    assert written["salt"].stat().st_mtime_ns == mtime  # not redrawn


def test_unknown_texture():
    with pytest.raises(ValueError, match="marble"):
        textures.make("marble")


def test_gaussian_blur_keeps_the_mean_and_wraps():
    rng = np.random.default_rng(0)
    a = rng.random((32, 48)).astype(np.float32)
    b = textures.blur(a, 3.0, 1.0)
    assert b.mean() == pytest.approx(a.mean(), abs=1e-5)
    assert b.std() < a.std()
