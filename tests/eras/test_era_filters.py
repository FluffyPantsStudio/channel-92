"""The eras' ffmpeg filters: constant strings that parse and run in ffmpeg, the way the finishing chain places them.

The 1950s post-filter is the kinescope (a broadcast filmed off a studio monitor) and each of its parts is measured
here on synthetic frames: monochrome, darker corners, milky blacks, clipped highlights, a glow around bright areas,
two soft hum bars rolling up, a faint scan-line structure, and a flicker that never trips the flash check.
"""

from __future__ import annotations

import subprocess

import numpy as np
import pytest

from atomic_flix import eras
from atomic_flix.cut.flash import FLASH_SIZE, count_transitions, relative_luminance
from atomic_flix.eras import ERAS, era, resolve_era

FPS = 24
FILTERS = [(row.id, kind, getattr(row, kind)) for row in ERAS for kind in ("prefilter", "postfilter")
           if getattr(row, kind)]


def _render(source: str, chain: str | None, *, seconds: float = 0.25, size: tuple[int, int] = (320, 240),
            out_size: tuple[int, int] | None = None, draw: str = "") -> np.ndarray:
    """RGB frames (n, h, w, 3) of a lavfi SOURCE (with DRAW on it) through CHAIN, placed as the finishing chain
    places a filter: inside a labelled filter_complex, on yuv420p."""
    width, height = size
    tail = f",scale={out_size[0]}:{out_size[1]}" if out_size else ""
    graph = (f"[0:v]{draw + ',' if draw else ''}format=yuv420p,setsar=1,{chain + ',' if chain else ''}"
             f"format=yuv420p{tail},format=rgb24[v]")
    command = ["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
               f"{source}{':' if '=' in source else '='}s={width}x{height}:r={FPS}:d={seconds}", "-filter_complex", graph, "-map", "[v]",
               "-f", "rawvideo", "-"]
    done = subprocess.run(command, capture_output=True)
    assert done.returncode == 0, done.stderr.decode(errors="replace")[-600:]
    w, h = out_size or size
    return np.frombuffer(done.stdout, np.uint8).reshape(-1, h, w, 3).astype(float)


def _kinescope(source: str, **kw) -> np.ndarray:
    return _render(source, era("1950s").postfilter, **kw)


# --- every era ------------------------------------------------------------------------------------------------------

def test_every_filter_is_a_module_constant_string():
    constants = {value for name, value in vars(eras).items() if name.isupper() and isinstance(value, str)}
    for era_id, kind, chain in FILTERS:
        assert isinstance(chain, str) and chain in constants, f"{era_id} {kind} is not a module constant"


def test_nothing_from_film_json_reaches_a_filter():
    film = {"setup": {"year": 1955, "prefilter": "drawtext=text=x", "postfilter": "null"},
            "prefilter": "drawtext=text=x", "postfilter": "null", "era": {"postfilter": "null"}}
    assert resolve_era(film) is era("1950s")
    assert resolve_era(film, "1970s") is era("1970s")


@pytest.mark.parametrize("era_id, kind, chain", FILTERS, ids=[f"{e}-{k}" for e, k, _ in FILTERS])
@pytest.mark.parametrize("size", [(320, 240), (240, 426), (96, 54)], ids=["4:3", "9:16", "tiny"])
def test_every_filter_parses_and_runs_in_ffmpeg(era_id, kind, chain, size):
    frames = _render("testsrc2", chain, size=size)
    assert frames.shape[1:3] == (size[1], size[0]) and len(frames) == round(0.25 * FPS)


def test_the_other_eras_filters_are_unchanged():
    assert {row.id: (row.prefilter, row.postfilter) for row in ERAS[1:]} == {
        "1960s": (None, None),
        "1970s": ("colorbalance=rs=0.06:gs=0.02:bs=-0.06:rm=0.04:bm=-0.04,eq=saturation=1.06", None),
        "1980s": (None, None),
        "1990s": (None, None),
        "2000s": (None, None),
    }


# --- the 1950s kinescope --------------------------------------------------------------------------------------------

def test_the_1950s_go_grey_before_ntsc_rs_and_stay_grey_after():
    before = _render("testsrc2", era("1950s").prefilter)
    after = _kinescope("testsrc2")
    for frames in (before, after):
        assert np.abs(frames[..., 0] - frames[..., 1]).max() <= 3
        assert np.abs(frames[..., 1] - frames[..., 2]).max() <= 3


def test_the_corners_fall_off_hard():
    frame = _kinescope("color=c=0x909090", size=(320, 240))[0, ..., 1]
    centre = frame[100:140, 140:180].mean()
    corners = np.mean([frame[:12, :12].mean(), frame[:12, -12:].mean(), frame[-12:, :12].mean(),
                       frame[-12:, -12:].mean()])
    assert corners < 0.55 * centre


def test_blacks_are_lifted_to_milky_and_highlights_clip():
    black = _kinescope("color=c=black")[0, 100:140, 140:180, 1].mean()
    near_white = _kinescope("color=c=0xE8E8E8")[0, 100:140, 140:180, 1].mean()
    white = _kinescope("color=c=white")[0, 100:140, 140:180, 1].mean()
    assert 10 <= black <= 30                    # milky, not crushed and not grey
    assert white <= 240                         # the top is clipped below full white
    assert white - near_white <= 6              # and flat: near white and white come out alike


def test_bright_areas_glow_into_their_surroundings():
    with_glow = _kinescope("color=c=black", draw="drawbox=x=140:y=100:w=40:h=40:c=white:t=fill")[0, ..., 1]
    plain = _kinescope("color=c=black")[0, ..., 1]
    ring = (slice(110, 130), slice(182, 188))   # 2 to 8 pixels right of the white box
    assert with_glow[ring].mean() - plain[ring].mean() >= 4


def test_two_soft_hum_bars_roll_up_the_picture():
    frames = _kinescope("color=c=0x909090", seconds=4.0, size=(320, 240))[..., 1]
    rows = frames[:, :, 120:200].mean(axis=2)
    relative = rows / rows.mean(axis=0)         # takes the fixed corner falloff out
    kernel = np.ones(7) / 7
    smooth = np.array([np.convolve(row, kernel, "same") for row in relative])[:, 8:-8]
    depth = np.median(smooth.max(axis=1) - smooth.min(axis=1))
    assert 0.10 <= depth <= 0.17                # bands of about 10 to 15 percent
    first, later = smooth[0], smooth[24]        # one second apart: the darkest band has moved up
    low_first, low_later = int(np.argmin(first[: len(first) // 2])), int(np.argmin(later[: len(later) // 2]))
    assert low_later < low_first


def test_a_faint_scan_line_structure_follows_the_short_side():
    frame = _kinescope("color=c=0x909090", size=(960, 720))[0, :, 400:560, 1].mean(axis=1)
    detail = frame[200:520] - np.convolve(frame, np.ones(9) / 9, "same")[200:520]
    spectrum = np.abs(np.fft.rfft(detail)) / len(detail)
    peak = int(np.argmax(spectrum[1:])) + 1
    assert abs(len(detail) / peak - 3.0) < 0.2   # 720 / 240: one line every 3 pixels
    assert 0.3 <= detail.std() <= 4.0             # faint: a few levels, not stripes


def test_the_flicker_and_hum_never_make_a_flash():
    for grey in ("0x909090", "0xD0D0D0", "0x404040"):
        frames = _kinescope(f"color=c={grey}", seconds=6.0, size=(320, 240), out_size=FLASH_SIZE)
        luminance = relative_luminance(frames.astype(np.uint8))
        assert count_transitions(luminance) == []
        means = luminance.reshape(len(luminance), -1).mean(axis=1)
        assert np.ptp(means) / means.mean() > 0.02    # there is a flicker to see
