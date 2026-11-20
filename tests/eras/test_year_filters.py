"""Years between eras, the ffmpeg side: the 1950s monochrome fades into colour between 1950 and 1960, the kinescope
fades out over the same years, and the 1970s warm lift rises from 1960 to full in 1970 and falls away to 1980. Every
filter is built from module constants and the year's weight only; at the anchors they are today's strings exactly."""

from __future__ import annotations

import subprocess

import numpy as np
import pytest

from atomic_flix.eras import (KINESCOPE, MONOCHROME, WARM_STOCK, era, era_look, kinescope, monochrome,
                              resolve_look, warm_stock, year_look)

FPS = 24
OLD_KINESCOPE = (
    "split=3[kin_a][kin_b][kin_r];"
    "[kin_b]crop=w='2*max(1,trunc(min(iw,ih)/90))':h=ih:x=0:y=0,"
    "geq=lum='255"
    "*(1-0.08*pow(0.5+0.5*cos(2*PI*2*(Y/H+T*0.09)),2))"
    "*(1-0.01*(1+sin(2*PI*T*4.7))-0.005*(1+sin(2*PI*T*11.3)))"
    "*(1-0.05*(0.5+0.5*cos(2*PI*Y/max(3,W*45/240))))'"
    ":cb=128:cr=128[kin_m];"
    "[kin_m][kin_r]scale=rw:rh:flags=neighbor[kin_mf];"
    "[kin_a][kin_mf]blend=c0_mode=multiply:c1_mode=normal:c2_mode=normal,"
    "split[kin_c][kin_d];"
    "[kin_d]lutyuv=y='clip((val-175)*2.5,0,255)':u=128:v=128,boxblur=lr='min(w,h)/30':lp=3:cr=0:cp=0[kin_glow];"
    "[kin_c][kin_glow]blend=c0_mode=screen:c0_opacity=0.55:c1_mode=normal:c2_mode=normal,"
    "vignette=angle=0.8,"
    "curves=interp=pchip:m='0/0.07 0.2/0.21 0.5/0.5 0.8/0.89 0.9/0.92 1/0.92',"
    "lutyuv=u=128:v=128"
)


def _render(source: str, chain: str | None, *, seconds: float = 0.25, size: tuple[int, int] = (320, 240)):
    width, height = size
    graph = f"[0:v]format=yuv420p,setsar=1,{chain + ',' if chain else ''}format=yuv420p,format=rgb24[v]"
    command = ["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
               f"{source}{':' if '=' in source else '='}s={width}x{height}:r={FPS}:d={seconds}",
               "-filter_complex", graph, "-map", "[v]", "-f", "rawvideo", "-"]
    done = subprocess.run(command, capture_output=True)
    assert done.returncode == 0, done.stderr.decode(errors="replace")[-600:]
    return np.frombuffer(done.stdout, np.uint8).reshape(-1, height, width, 3).astype(float)


def _both(year: int) -> str | None:
    look = year_look(year)
    return ",".join(part for part in (look.prefilter, look.postfilter) if part) or None


def _colour(frames: np.ndarray) -> float:
    return float(np.abs(frames[..., 0] - frames[..., 2]).mean() + np.abs(frames[..., 1] - frames[..., 2]).mean())


# --- the strings ----------------------------------------------------------------------------------------------------

def test_at_full_strength_the_builders_give_todays_strings():
    assert KINESCOPE == OLD_KINESCOPE == kinescope(1.0)
    assert monochrome(0.0) == MONOCHROME == "lutyuv=u=128:v=128"
    assert warm_stock(1.0) == WARM_STOCK
    assert kinescope(0.0) is None and warm_stock(0.0) is None and monochrome(1.0) is None


def test_1950_is_monochrome_kinescope():
    assert (year_look(1950).prefilter, year_look(1950).postfilter) == (MONOCHROME, KINESCOPE)


def test_the_later_eras_filters_are_todays_at_their_anchors_and_beyond():
    assert (year_look(1960).prefilter, year_look(1960).postfilter) == (None, None)
    assert (year_look(1970).prefilter, year_look(1970).postfilter) == (WARM_STOCK, None)
    for year in range(1980, 2011):
        assert (year_look(year).prefilter, year_look(year).postfilter) == (None, None), year
    for year in range(1960, 2011):
        assert year_look(year).postfilter is None, year


def test_between_1950_and_1960_colour_comes_in_and_the_kinescope_goes():
    look = year_look(1955)
    assert "0.5" in look.prefilter and "u=128:v=128" not in look.prefilter
    assert look.postfilter == kinescope(0.5) and "c0_opacity=0.275" in look.postfilter
    assert "vignette=angle=0.4," in look.postfilter
    assert not look.postfilter.endswith("lutyuv=u=128:v=128")          # the colour the pre-filter let in stays


def test_the_warm_lift_rises_to_1970_and_falls_away_symmetrically():
    assert year_look(1965).prefilter == warm_stock(0.5) and year_look(1975).prefilter == warm_stock(0.5)
    assert "rs=0.03:" in warm_stock(0.5) and "saturation=1.03" in warm_stock(0.5)
    assert year_look(1961).prefilter == warm_stock(0.1) and year_look(1979).prefilter == warm_stock(0.1)


@pytest.mark.parametrize("build", [kinescope, monochrome, warm_stock])
@pytest.mark.parametrize("bad", [-0.1, 1.2, "0.5", None, True, float("nan")])
def test_the_builders_take_only_a_weight(build, bad):
    with pytest.raises((TypeError, ValueError)):
        build(bad)


def test_nothing_from_film_json_reaches_a_filter_but_the_year():
    junk = {"prefilter": "drawtext=text=x", "postfilter": "null", "preset": {"luma_smear": 1.0}}
    film = {"setup": {"year": 1955, **junk}, **junk, "era": junk, "look": junk}
    look = resolve_look(film)
    plain = year_look(1955)
    assert (look.prefilter, look.postfilter, look.preset) == (plain.prefilter, plain.postfilter, plain.preset)
    forced = resolve_look(film, "1970s")
    assert (forced.prefilter, forced.postfilter, forced.preset) == (WARM_STOCK, None, era_look("1970s").preset)
    overridden = resolve_look(film, year="1970")
    assert overridden.prefilter == WARM_STOCK and overridden.year == 1970
    assert resolve_look({"setup": {}}) is None


def test_an_era_override_is_its_pure_look():
    forced = era_look(era("1950s"))
    assert (forced.prefilter, forced.postfilter, forced.weight, forced.year) == (MONOCHROME, KINESCOPE, 0.0, None)


# --- in ffmpeg ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("year", [1950, 1955, 1956, 1960, 1965, 1970, 1975, 1980, 1996, 2000, 2010])
def test_the_years_filters_run_in_ffmpeg(year):
    look = year_look(year)
    for chain in (look.prefilter, look.postfilter):
        frames = _render("testsrc2", chain, size=(240, 426))
        assert frames.shape[1:3] == (426, 240)


def test_colour_rises_with_the_year_from_1950_to_1960():
    colour = [_colour(_render("testsrc2", _both(year))) for year in range(1950, 1961)]
    assert colour[0] < 2 and colour == sorted(colour)
    assert colour[1] < 0.2 * colour[-1]                                 # 1951 keeps about a tenth of its colour
    assert 0.3 * colour[-1] < colour[5] < 0.75 * colour[-1]             # 1955 about half
    assert colour[6] > colour[5]                                        # 1956 more: six tenths


def test_the_corner_falloff_fades_with_the_kinescope():
    def corners(year: int) -> float:
        frame = _render("color=c=0x909090", year_look(year).postfilter)[0, ..., 1]
        return float(frame[:12, :12].mean() / frame[100:140, 140:180].mean())
    ratios = [corners(year) for year in (1950, 1953, 1955, 1957, 1959)]
    assert ratios == sorted(ratios) and ratios[0] < 0.55 and ratios[-1] > 0.9


def test_the_warm_lift_is_strongest_in_1970():
    def warmth(year: int) -> float:
        frames = _render("color=c=0x404040", year_look(year).prefilter)      # the lift shows in the shadows
        return float((frames[..., 0] - frames[..., 2]).mean())
    assert warmth(1960) == pytest.approx(0, abs=1.5) and warmth(1980) == pytest.approx(0, abs=1.5)
    assert warmth(1970) > warmth(1965) > warmth(1961) > warmth(1960)
    assert warmth(1965) == pytest.approx(warmth(1975), abs=0.5)
