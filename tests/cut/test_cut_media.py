import numpy as np

from atomic_flix.cut.media import iter_frames, probe, read_frames, write_image
from cutclips import HEIGHT, WIDTH, make_take, read_counter


def test_probe_reads_size_rate_and_frames(tmp_path):
    clip = make_take(tmp_path / "a.mp4", count=50)
    info = probe(clip)
    assert (info.width, info.height, info.frames) == (WIDTH, HEIGHT, 50)
    assert info.fps == 24.0
    assert abs(info.seconds - 50 / 24) < 1e-6


def test_read_frames_from_a_start_frame_is_exact(tmp_path):
    clip = make_take(tmp_path / "a.mp4", count=60)
    frames = read_frames(clip, start_frame=37, count=5)
    assert [read_counter(frame) for frame in frames] == [37, 38, 39, 40, 41]


def test_read_frames_far_into_a_clip_seeks_exactly(tmp_path):
    clip = make_take(tmp_path / "long.mp4", count=300)
    for start in (121, 200, 290):
        frames = read_frames(clip, start_frame=start, count=3)
        assert [read_counter(frame) for frame in frames] == [start, start + 1, start + 2]


def test_read_frames_grey_and_resized(tmp_path):
    clip = make_take(tmp_path / "a.mp4", count=10)
    frames = read_frames(clip, size=(96, 54), grey=True)
    assert frames.shape == (10, 54, 96)


def test_iter_frames_keeps_only_wanted_indices(tmp_path):
    clip = make_take(tmp_path / "a.mp4", count=40)
    kept = dict(iter_frames(clip, wanted={3, 17, 39}))
    assert sorted(kept) == [3, 17, 39]
    assert read_counter(kept[17]) == 17


def test_write_image_makes_a_jpeg_and_png(tmp_path):
    picture = np.zeros((20, 30, 3), np.uint8)
    picture[:, :15] = 255
    for name in ("a.jpg", "a.png"):
        out = write_image(tmp_path / name, picture)
        assert out.stat().st_size > 0
        back = read_frames(out)
        assert back.shape == (1, 20, 30, 3)
        assert back[0, 10, 5].mean() > 200 and back[0, 10, 25].mean() < 50
