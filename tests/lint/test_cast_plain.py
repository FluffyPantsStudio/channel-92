"""Measuring a view picture: a tall portrait the figure fills, on a plain studio backdrop. Size and shape are strict; the
background is a coarse screen (a busy place fails; a flat-coloured wall is for the judge). A bad file says so."""

from __future__ import annotations

import json

import numpy as np
import pytest

from atomic_flix import cast
from atomic_flix.cast import Plainness, as_plainness, kind_of, measure_view, plain_of
from atomic_flix.scenes.imageio import write_png
from sheet_samples import picture


def _png(tmp_path, array, name="v.png"):
    write_png(tmp_path / name, array)
    return tmp_path / name


def test_one_figure_filling_a_tall_picture_on_a_flat_backdrop_is_ok(tmp_path):
    found = plain_of(_png(tmp_path, picture()))
    assert found.ok() and found.aspect == pytest.approx(1.5) and found.figure > 0.9 and found.ring > 0.95


def test_a_soft_studio_gradient_backdrop_is_plain(tmp_path):
    ys, xs = np.mgrid[0:144, 0:96]
    shade = (190 - 50 * np.hypot((ys - 72) / 72, (xs - 48) / 48)).clip(0, 255).astype(np.uint8)
    array = np.stack([shade, shade, shade + 8], axis=2)
    array[4:140, 36:60] = (200, 90, 90)
    assert plain_of(_png(tmp_path, array)).environment() is None


def test_a_busy_background_is_an_environment(tmp_path):
    found = plain_of(_png(tmp_path, picture(busy=True)))
    assert "environment behind the figure" in found.environment() and not found.ok()


def test_a_street_of_blocks_around_the_figure_is_an_environment(tmp_path):
    array = picture()
    rng = np.random.default_rng(3)
    for _ in range(160):
        y, x = int(rng.integers(0, 130)), int(rng.integers(0, 80))
        array[y:y + 12, x:x + 14] = rng.integers(0, 255, 3, dtype=np.uint8)
    array[4:140, 36:60] = (200, 90, 90)
    assert plain_of(_png(tmp_path, array)).environment()


def test_a_small_figure_in_a_wide_frame_is_too_small(tmp_path):
    found = plain_of(_png(tmp_path, picture(wide=True)))
    assert found.environment() is None
    assert "tall portrait picture" in found.small() and "1.67 times as wide as it is tall" in found.small()


def test_a_figure_that_fills_half_the_height_of_a_tall_picture_is_too_small(tmp_path):
    array = np.full((144, 96, 3), 128, np.uint8)
    array[40:110, 36:60] = (200, 90, 90)
    found = plain_of(_png(tmp_path, array))
    assert found.aspect > cast.ASPECT_MIN and "covers only" in found.small()


def test_transparency_is_ignored_the_model_sees_the_colours(tmp_path):
    array = np.zeros((144, 96, 4), np.uint8)
    array[..., :3] = picture(busy=True)                       # a street under alpha 0
    assert plain_of(_png(tmp_path, array)).environment()


def test_a_grey_picture_is_measured(tmp_path):
    assert plain_of(_png(tmp_path, picture()[..., 0], "grey.png")).ok()


def test_a_corrupt_or_empty_file_raises_a_value_error_naming_it(tmp_path):
    (tmp_path / "bad.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)
    with pytest.raises(ValueError, match="bad.png"):
        plain_of(tmp_path / "bad.png")
    (tmp_path / "empty.png").write_bytes(b"")
    with pytest.raises(ValueError, match="empty.png"):
        plain_of(tmp_path / "empty.png")


def test_a_measurement_is_remembered_until_the_file_changes(tmp_path):
    _png(tmp_path, picture(), "front.png")
    first = measure_view(tmp_path, "front.png")
    cache = json.loads((tmp_path / "cache" / "plain.json").read_text(encoding="utf-8"))
    assert cache["front.png"]["ring"] == pytest.approx(first.ring)
    cache["front.png"]["ring"] = 0.123                         # a planted entry shows the cache is what is read
    (tmp_path / "cache" / "plain.json").write_text(json.dumps(cache), encoding="utf-8")
    assert measure_view(tmp_path, "front.png").ring == pytest.approx(0.123)
    _png(tmp_path, picture(busy=True), "front.png")
    assert not measure_view(tmp_path, "front.png").ok()        # a changed file is measured again


def test_an_old_cache_entry_without_the_new_fields_is_measured_again(tmp_path):
    _png(tmp_path, picture(), "front.png")
    (tmp_path / "cache").mkdir()
    stat = (tmp_path / "front.png").stat()
    (tmp_path / "cache" / "plain.json").write_text(json.dumps({"front.png": {
        "key": [stat.st_mtime_ns, stat.st_size], "border": 0.5, "room": 0.5}}), encoding="utf-8")
    assert measure_view(tmp_path, "front.png").ok()


def test_a_hand_written_measurement_is_a_number_an_object_or_a_reason():
    assert as_plainness(0.5) == Plainness(ring=0.5)
    assert as_plainness({"ring": 0.9, "aspect": 0.5, "figure": 0.4}) == Plainness(0.9, 0.5, 0.4)
    assert as_plainness("cannot") == "cannot"


def test_a_view_is_a_head_and_shoulders_view_or_a_full_length_one():
    assert [kind_of(v) for v in ("front", "back", "body_front", "body_back")] == ["bust", "bust", "body", "body"]
