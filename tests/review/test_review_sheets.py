import json

import numpy as np
import pytest

from atomic_flix.cut.edit import Cut, Edit, Placed
from atomic_flix.cut.media import probe, read_frames
from atomic_flix.cut.render import render_cut
from atomic_flix.review.canvas import text_image
from atomic_flix.review.sheets import extract_full_frames, make_review
from reviewclips import FPS, HEIGHT, WIDTH, busy_box, panning, save

MOUTH = (0.4, 0.55, 0.2, 0.15)


@pytest.fixture(scope="module")
def film(tmp_path_factory):
    folder = tmp_path_factory.mktemp("film")
    pan = save(folder / "pan.mp4", panning(4.0, 2.0, still_after=2.5))
    sing = save(folder / "sing.mp4", busy_box(4.0, MOUTH, busy=[(1.0, 2.5)]))
    edit = Edit(fps=FPS, size=(WIDTH, HEIGHT), song=None, start=10.0, end=14.0,
                cuts=(Cut("N01", 10.0, "one"), Cut("S02", 12.0, "one")),
                takes={"N01": Placed("N01", pan, ((10.0, 1.0),), cam_move="locked on a tripod"),
                       "S02": Placed("S02", sing, ((12.0, 0.25),), kind="vocal", mouth=MOUTH, moments=(0.5,))},
                pulse={"beats": [10.0 + 0.5 * i for i in range(8)], "downbeat_slot": 0},
                sung=((12.75, 14.0),))
    cut = render_cut(edit, folder / "v01.mp4", crf=12, x264_speed="ultrafast").out
    return edit, cut, folder


def test_text_image_draws_ink():
    picture = text_image("S02 12.25 S", scale=2)
    assert picture.ndim == 2 and picture.shape[0] == 10
    assert picture.max() == 255 and picture.min() == 0


def test_review_writes_strips_motion_ends_bars_and_a_manifest(film, tmp_path):
    edit, cut, _ = film
    result = make_review(edit, cut, tmp_path / "review")
    names = {path.name for path in result.files}
    for stem in ("01-N01", "02-S02"):
        assert f"{stem}-strip.jpg" in names
        assert f"{stem}-motion.jpg" in names
        assert f"{stem}-ends.jpg" in names
    assert any(name.startswith("02-S02-burst") for name in names)
    assert any(name.startswith("bars-") for name in names)
    assert any(name.startswith("cuts-") for name in names)
    manifest = (tmp_path / "review" / "MANIFEST.txt").read_text(encoding="utf-8")
    for name in names - {"MANIFEST.txt", "review.json"}:
        assert name in manifest
    assert "camera drift" in manifest and "still at the end" in manifest and "mouth" in manifest
    data = json.loads((tmp_path / "review" / "review.json").read_text(encoding="utf-8"))
    assert [shot["key"] for shot in data["shots"]] == ["N01", "S02"]


def test_strip_holds_one_frame_every_quarter_second(film, tmp_path):
    edit, cut, _ = film
    result = make_review(edit, cut, tmp_path / "r")
    shot = result.shots[0]
    assert shot["strip_times"] == pytest.approx([0.25 * i for i in range(8)])
    strip = read_frames(tmp_path / "r" / "01-N01-strip.jpg")[0]
    assert strip.shape[1] >= 8 * 160


def test_measures_find_the_still_tail_and_the_locked_camera_drift(film, tmp_path):
    edit, cut, _ = film
    shots = {shot["key"]: shot for shot in make_review(edit, cut, tmp_path / "m").shots}
    pan = shots["N01"]["measures"]
    assert pan["camera_drift"]["largest"] > 0.1
    assert any("camera" in flag for flag in shots["N01"]["flags"])
    assert pan["still_tail"] == pytest.approx(0.5, abs=0.1)
    assert any("still at the end" in flag for flag in shots["N01"]["flags"])
    sing = shots["S02"]["measures"]
    assert sing["mouth"]["ratio"] > 2
    assert sing["camera_drift"]["largest"] < 0.01


def test_bar_sheet_marks_the_beat_a_cut_came_in_on(film, tmp_path):
    edit, cut, _ = film
    make_review(edit, cut, tmp_path / "b")
    sheet = read_frames(tmp_path / "b" / "bars-001-002.jpg")[0].astype(int)
    red = (sheet[..., 0] > 180) & (sheet[..., 1] < 90) & (sheet[..., 2] < 90)
    top, bottom = red[: sheet.shape[0] // 2], red[sheet.shape[0] // 2:]
    assert top.sum() == 0          # bar 1: one shot throughout
    assert bottom.sum() > 100      # bar 2 opens on the cut to S02


def test_motion_strip_is_bright_where_the_picture_moves(film, tmp_path):
    edit, cut, _ = film
    make_review(edit, cut, tmp_path / "s")
    pan = read_frames(tmp_path / "s" / "01-N01-motion.jpg")[0].astype(float)
    sing = read_frames(tmp_path / "s" / "02-S02-motion.jpg")[0].astype(float)
    assert pan.mean() > sing.mean()


def test_full_size_frames_on_request(film, tmp_path):
    edit, cut, _ = film
    written = extract_full_frames(edit, cut, "S02", tmp_path / "full", times=[0.0, 1.0])
    assert [path.name for path in written] == ["S02-0.000.png", "S02-1.000.png"]
    info = probe(written[0])
    assert (info.width, info.height) == (WIDTH, HEIGHT)
    every = extract_full_frames(edit, cut, "N01", tmp_path / "full", every=0.5)
    assert len(every) == 4
