import numpy as np
import pytest

from atomic_flix.cut.edit import Cut, Edit, Placed
from atomic_flix.cut.loudness import measure_loudness
from atomic_flix.cut.media import SCALE_FLAGS, probe, read_frames
from atomic_flix.cut.render import CutError, render_cut, ffmpeg_command_for_test
from cutclips import FPS, HEIGHT, WIDTH, make_take, make_tone, read_counter


@pytest.fixture
def two_takes(tmp_path):
    a = make_take(tmp_path / "a.mp4", colour=(200, 40, 40))
    b = make_take(tmp_path / "b.mp4", colour=(40, 40, 200))
    song = make_tone(tmp_path / "song.wav", seconds=4.0)
    return a, b, song


def test_render_shows_the_mapped_frames_never_the_first_two_and_hits_loudness(two_takes, tmp_path):
    a, b, song = two_takes
    edit = Edit(fps=FPS, size=(WIDTH, HEIGHT), song=song, start=0.0, end=4.0,
                cuts=(Cut("A", 0.0), Cut("B", 2.0)),
                takes={"A": Placed("A", a, ((0.0, 0.5),)), "B": Placed("B", b, ((2.0, 1.0), (4.0, 4.0)))})
    out = tmp_path / "cut.mp4"
    result = render_cut(edit, out, crf=10, x264_speed="ultrafast")
    frames = read_frames(out)
    assert len(frames) == 96
    shown = [read_counter(frame) for frame in frames]
    expected = [n + 12 for n in range(48)] + [int(np.floor(24 + 1.5 * (n - 48) + 0.5)) for n in range(48, 96)]
    assert shown == expected
    assert 0 not in shown and 1 not in shown
    assert frames[10, 60:, :, 0].mean() > frames[10, 60:, :, 2].mean()   # take A is red
    assert frames[60, 60:, :, 2].mean() > frames[60, 60:, :, 0].mean()   # take B is blue
    loud = measure_loudness(out)
    assert abs(loud.integrated + 14.0) <= 0.5
    assert result.audio["trim_db"] > 0
    assert result.audit.errors == []


def test_render_refuses_a_slowed_take(two_takes, tmp_path):
    a, _, song = two_takes
    edit = Edit(fps=FPS, size=(WIDTH, HEIGHT), song=song, start=0.0, end=2.0, cuts=(Cut("A", 0.0),),
                takes={"A": Placed("A", a, ((0.0, 0.5), (2.0, 2.0)))})
    with pytest.raises(CutError, match="slower"):
        render_cut(edit, tmp_path / "x.mp4", x264_speed="ultrafast")
    assert not (tmp_path / "x.mp4").exists()


def test_render_refuses_a_jump_cut(two_takes, tmp_path):
    a, b, song = two_takes
    edit = Edit(fps=FPS, size=(WIDTH, HEIGHT), song=song, start=0.0, end=4.0,
                cuts=(Cut("A", 0.0), Cut("B", 2.0)),
                takes={"A": Placed("A", a, ((0.0, 0.5),), setup="moon", crop_keep=1.0),
                       "B": Placed("B", b, ((2.0, 0.5),), setup="moon", crop_keep=1.0)})
    with pytest.raises(CutError, match="jump cut"):
        render_cut(edit, tmp_path / "x.mp4", x264_speed="ultrafast")


def test_a_take_of_another_shape_fills_and_centre_crops(tmp_path):
    tall = make_take(tmp_path / "tall.mp4", count=48, width=192, height=144)
    song = make_tone(tmp_path / "song.wav", seconds=2.0)
    edit = Edit(fps=FPS, size=(WIDTH, HEIGHT), song=song, start=0.0, end=1.5, cuts=(Cut("T", 0.0),),
                takes={"T": Placed("T", tall, ((0.0, 0.25),))})
    out = tmp_path / "fill.mp4"
    render_cut(edit, out, x264_speed="ultrafast")
    info = probe(out)
    assert (info.width, info.height) == (WIDTH, HEIGHT)
    assert info.frames == 36


def test_quiet_song_is_raised_but_peak_stays_under_minus_one(tmp_path):
    rate = 48000
    t = np.arange(rate * 4) / rate
    clicks = np.zeros_like(t)
    clicks[::rate // 4] = 0.9                           # sparse loud clicks: low loudness, high peak
    clicks += 0.01 * np.sin(2 * np.pi * 330 * t)
    from atomic_flix.wav import save_wav
    song = save_wav(tmp_path / "clicks.wav", np.stack([clicks, clicks], axis=1), rate)
    take = make_take(tmp_path / "a.mp4")
    edit = Edit(fps=FPS, size=(WIDTH, HEIGHT), song=song, start=0.0, end=3.5, cuts=(Cut("A", 0.0),),
                takes={"A": Placed("A", take, ((0.0, 0.5),))})
    result = render_cut(edit, tmp_path / "c.mp4", x264_speed="ultrafast")
    assert result.audio["peak_after_db"] <= -1.0 + 1e-6
    assert any("below -16" in w for w in result.warnings)


def test_every_rescale_uses_the_accurate_flags(two_takes, tmp_path):
    a, b, song = two_takes
    edit = Edit(fps=FPS, size=(WIDTH, HEIGHT), song=song, start=0.0, end=2.0, cuts=(Cut("A", 0.0),),
                takes={"A": Placed("A", a, ((0.0, 0.5),))})
    decode, encode = ffmpeg_command_for_test(edit, tmp_path / "o.mp4")
    assert SCALE_FLAGS == "bicubic+accurate_rnd+full_chroma_int+bitexact"
    assert any(SCALE_FLAGS in part for part in decode)
    assert encode.count("-c:v") == 1
