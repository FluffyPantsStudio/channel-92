"""Channel 92's six eras, 1950 to 2010, and the look each one lays on a finished film.

A film's era comes from its year (film.json `setup.year`, `choose FILM year YYYY`); `finish --era ID` overrides it.
A film with neither has no era, and `finish` delivers it without a look and says so. The look itself is a smooth
function of the year: each era's preset and filters are its decade's first year, and a year between two of those
blends them (`year_look`, "years between eras" below; docs/eras.md). Each era has:

    medium      what the channel's pictures went through then, in one plain line
    preset      its ntsc-rs effect settings (`atomic_flix/looks/<id>.json`, checked by `atomic_flix.looks`)
    prefilter   an ffmpeg filter run before ntsc-rs, for what ntsc-rs has no setting for (None when not needed)
    postfilter  an ffmpeg filter run in the final encode, after ntsc-rs (None when not needed)
    lines       the lines ntsc-rs works at on the frame's short side (`--scale`, set by `finish.ntsc.scale_lines`,
                so a 9:16 frame keeps 480 across); the final encode scales back to the film's size
    logo        the channel's mark as it looked in that era (the 2000s wear the channel's own modern mark)

The suggested aspect comes from the aspect table (`aspects.suggested_aspect`); it is never a choice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .aspects import check_year, suggested_aspect
from .brand.logo import logo_file
from .looks import blend_presets, load_preset, preset_file
from .looks.blend import check_weight

NTSC_LINES = 480        # on the frame's short side

# Every filter below is built from constant text and numbers worked out from a weight (0 to 1) alone: a year between
# eras scales them (`year_look`), and at full strength they are the strings the eras were tuned with.

# 1950s, before ntsc-rs: grey, so the composite signal carries no colour.
MONOCHROME = "lutyuv=u=128:v=128"
# 1950s, after ntsc-rs: the broadcast filmed off a studio monitor (kinescope), tuned on real renders (2026-11-20).
# Every part is a constant; sizes follow the frame through expressions of its own width and height.
#   the monitor: one multiplier that depends only on the row and the time, worked out on a thin strip and stretched
#     over the frame (a per-pixel geq would be six times slower): two soft hum bars 8 % deep rolling up the picture
#     (a bar passes every 5.6 s), a flicker of 1 % at 4.7 Hz and 0.5 % at 11.3 Hz (it only ever darkens, far under
#     the flash check's 10 %), and scan lines 5 % deep, one every short side / 240 pixels and never under 3
#   halation: what is brighter than 175 (of 235), blurred over 1/30 of the short side, screened back at 55 %
#   the camera: corner falloff (vignette at 0.8), then a compressed tone curve: blacks lifted to 7 %, highlights
#     clipped at 92 %; grey again at the end
# A weaker kinescope (a year between 1950 and 1960) scales the hum, flicker and scan-line depths, the halation's
# opacity, the vignette's angle and the curve's pull away from straight, and leaves out the final grey: the colour
# the pre-filter let back in stays.
_KINESCOPE_PARTS = (
    "split=3[kin_a][kin_b][kin_r];"
    "[kin_b]crop=w='2*max(1,trunc(min(iw,ih)/90))':h=ih:x=0:y=0,"
    "geq=lum='255"
    "*(1-{hum}*pow(0.5+0.5*cos(2*PI*2*(Y/H+T*0.09)),2))"
    "*(1-{flicker_a}*(1+sin(2*PI*T*4.7))-{flicker_b}*(1+sin(2*PI*T*11.3)))"
    "*(1-{scan}*(0.5+0.5*cos(2*PI*Y/max(3,W*45/240))))'"
    ":cb=128:cr=128[kin_m];"
    "[kin_m][kin_r]scale=rw:rh:flags=neighbor[kin_mf];"
    "[kin_a][kin_mf]blend=c0_mode=multiply:c1_mode=normal:c2_mode=normal,"
    "split[kin_c][kin_d];"
    "[kin_d]lutyuv=y='clip((val-175)*2.5,0,255)':u=128:v=128,boxblur=lr='min(w,h)/30':lp=3:cr=0:cp=0[kin_glow];"
    "[kin_c][kin_glow]blend=c0_mode=screen:c0_opacity={glow}:c1_mode=normal:c2_mode=normal,"
    "vignette=angle={vignette},"
    "curves=interp=pchip:m='{curve}'"
)
_KINESCOPE_FULL = {"hum": 0.08, "flicker_a": 0.01, "flicker_b": 0.005, "scan": 0.05, "glow": 0.55, "vignette": 0.8}
_KINESCOPE_CURVE = ((0, 0.07), (0.2, 0.21), (0.5, 0.5), (0.8, 0.89), (0.9, 0.92), (1, 0.92))
_WARM_PARTS = "colorbalance=rs={rs}:gs={gs}:bs={bs}:rm={rm}:bm={bm},eq=saturation={saturation}"
_WARM_FULL = {"rs": 0.06, "gs": 0.02, "bs": -0.06, "rm": 0.04, "bm": -0.04}
_WARM_SATURATION = 0.06
_COLOUR_PARTS = "lutyuv=u='128+(val-128)*{colour}':v='128+(val-128)*{colour}'"


def _number(value: float) -> str:
    """A filter number: at most four decimals, no trailing zeros (0.08, 0.275, 1)."""
    return f"{round(float(value), 4):g}"


_weight = check_weight


def kinescope(strength: float) -> str | None:
    """The 1950s post-filter at STRENGTH (1: KINESCOPE exactly; 0: None, no kinescope)."""
    strength = _weight(strength)
    if strength == 0.0:
        return None
    parts = {name: _number(value * strength) for name, value in _KINESCOPE_FULL.items()}
    curve = " ".join(f"{_number(x)}/{_number(x * (1 - strength) + y * strength)}" for x, y in _KINESCOPE_CURVE)
    built = _KINESCOPE_PARTS.format(curve=curve, **parts)
    return built + ",lutyuv=u=128:v=128" if strength == 1.0 else built


def monochrome(colour: float) -> str | None:
    """The 1950s pre-filter keeping COLOUR of the picture's colour (0: MONOCHROME exactly; 1: None, all of it)."""
    colour = _weight(colour)
    if colour == 0.0:
        return MONOCHROME
    return None if colour == 1.0 else _COLOUR_PARTS.format(colour=_number(colour))


def warm_stock(strength: float) -> str | None:
    """The 1970s warm lift at STRENGTH (1: WARM_STOCK exactly; 0: None)."""
    strength = _weight(strength)
    if strength == 0.0:
        return None
    parts = {name: _number(value * strength) for name, value in _WARM_FULL.items()}
    return _WARM_PARTS.format(saturation=_number(1 + _WARM_SATURATION * strength), **parts)


KINESCOPE = kinescope(1.0)
WARM_STOCK = warm_stock(1.0)


class EraError(ValueError):
    """An era the channel does not have; the message names the ones it does."""


@dataclass(frozen=True)
class Era:
    id: str
    first: int
    last: int
    medium: str
    prefilter: str | None = None
    postfilter: str | None = None
    lines: int = NTSC_LINES

    @property
    def preset(self) -> Path:
        return preset_file(self.id)

    @property
    def logo(self) -> Path:
        return logo_file(self.id)

    def suggested_aspect(self, year: int | None = None) -> str:
        return suggested_aspect(self.first if year is None else year)


ERAS: tuple[Era, ...] = (
    Era("1950s", 1950, 1959, "black-and-white kinescope: the broadcast filmed off a studio monitor, soft, with hum "
                             "bars and flicker", prefilter=MONOCHROME, postfilter=KINESCOPE),
    Era("1960s", 1960, 1969, "early colour broadcast: heavy colour smear and bleeding, colour a little off"),
    Era("1970s", 1970, 1979, "analog colour broadcast: dot crawl on sharp edges, ringing, warm colour",
        prefilter=WARM_STOCK),
    Era("1980s", 1980, 1989, "home tape, VHS and Betamax: tape noise, head switching at the bottom, tracking lines"),
    Era("1990s", 1990, 1999, "a worn VHS camcorder tape: long play, wavy edges, colour loss and dropouts"),
    Era("2000s", 2000, 2010, "late analog cable into early digital: mild composite noise, otherwise clean"),
)
BY_ID = {row.id: row for row in ERAS}


def era(era_id: str) -> Era:
    found = BY_ID.get(str(era_id).strip())
    if found is None:
        raise EraError(f"no era {era_id!r}; the eras are {', '.join(BY_ID)}")
    return found


def era_of_year(year: object) -> Era:
    """The era YEAR (1950 to 2010) belongs to; AspectError for a year the channel was off the air."""
    value = check_year(year)
    return next(row for row in ERAS if row.first <= value <= row.last)


def _film_year(film: Mapping) -> object:
    setup = film.get("setup")
    return setup.get("year") if isinstance(setup, Mapping) else None


def resolve_era(film: Mapping, override: str | None = None) -> Era | None:
    """The film's era: OVERRIDE when given, else from film.json setup.year, else None (no era, no look)."""
    if override:
        return era(override)
    year = _film_year(film)
    return None if year is None else era_of_year(year)


# --- years between eras ---------------------------------------------------------------------------------------------
# Each era's preset and filters are the look of its decade's first year, the anchor (1950, 1960 ... 2000). A year
# between two anchors blends the two by the fraction of the way (1975 is halfway from the 1970s to the 1980s); 2000
# to 2010 have no later anchor and are the 2000s look exactly. 1950, the first year, is the 1950s look exactly.
ANCHORS: dict[str, int] = {row.id: row.first for row in ERAS}
ANCHOR_STEP = 10


def anchor_pair(year: object) -> tuple[Era, Era, float]:
    """The two eras whose anchors YEAR lies between and the share of the way to the later one; (era, era, 0.0) at an
    anchor and from 2000 on. AspectError for a year the channel was off the air."""
    value = check_year(year)
    for low, high in zip(ERAS, ERAS[1:]):
        if value == ANCHORS[low.id]:
            return low, low, 0.0
        if ANCHORS[low.id] < value < ANCHORS[high.id]:
            return low, high, (value - ANCHORS[low.id]) / ANCHOR_STEP
    return ERAS[-1], ERAS[-1], 0.0


def _filters(weights: Mapping[str, float]) -> tuple[str | None, str | None]:
    """The ffmpeg pre and post filters for these anchor weights (each era's share of the look)."""
    fifties, seventies = weights.get("1950s", 0.0), weights.get("1970s", 0.0)
    pre = [part for part in ((monochrome(1 - fifties) if fifties else None), warm_stock(seventies)) if part]
    return (",".join(pre) or None), kinescope(fifties)


@dataclass(frozen=True)
class YearLook:
    """The look `finish` lays on: the preset (a full ntsc-rs preset), the ffmpeg filters, the two eras it lies
    between and the share of the way to the later one (0 when it is one era's look exactly). ERA, the decade the
    year belongs to (or the era asked for), brings the logo, the intro and the medium; YEAR is None for a pure era
    look chosen with --era."""

    era: Era
    year: int | None
    low: Era
    high: Era
    weight: float
    preset: dict = field(compare=False, repr=False)
    prefilter: str | None = None
    postfilter: str | None = None

    @property
    def nearer(self) -> Era:
        return self.high if self.weight >= 0.5 else self.low

    def describe(self) -> str:
        """One plain line, from the earlier era (the year's own decade): "year 1956: the 1950s look, 60 percent of
        the way to the 1960s", "year 1975: halfway between the 1970s and the 1980s looks"."""
        head = f"year {self.year}: " if self.year is not None else ""
        if self.weight == 0.0:
            return f"{head}the {self.low.id} look"
        if self.weight == 0.5:
            return f"{head}halfway between the {self.low.id} and the {self.high.id} looks"
        return f"{head}the {self.low.id} look, {round(self.weight * 100)} percent of the way to the {self.high.id}"


def era_look(chosen: Era | str) -> YearLook:
    """ERA's own look exactly (its preset and filters), as `finish --era` lays it on."""
    row = chosen if isinstance(chosen, Era) else era(chosen)
    pre, post = _filters({row.id: 1.0})
    return YearLook(era=row, year=None, low=row, high=row, weight=0.0, preset=load_preset(row.id), prefilter=pre,
                    postfilter=post)


def year_look(year: object) -> YearLook:
    """The look of YEAR (1950 to 2010): the two neighbouring eras' presets and filters blended by the share of the
    way between their anchors; the logo and intro still follow the decade (`era_of_year`)."""
    value = check_year(year)
    low, high, weight = anchor_pair(value)
    preset = blend_presets(load_preset(low.id), load_preset(high.id), weight)
    weights = {low.id: 1 - weight, high.id: weight} if low is not high else {low.id: 1.0}
    pre, post = _filters(weights)
    return YearLook(era=era_of_year(value), year=value, low=low, high=high, weight=weight, preset=preset,
                    prefilter=pre, postfilter=post)


def look_for_year(year: object) -> dict:
    """The full ntsc-rs preset for YEAR (`year_look`); it passes `looks.check_preset` for every year 1950 to 2010."""
    return year_look(year).preset


def resolve_look(film: Mapping, override: str | None = None, year: object = None) -> YearLook | None:
    """The film's look: OVERRIDE's era exactly when given, else YEAR's (a one-run override), else film.json
    setup.year's, else None. Only the year (an integer in 1950 to 2010) is read from the film; nothing else in
    film.json reaches a preset or a filter."""
    if override:
        return era_look(override)
    chosen = _film_year(film) if year is None else year
    return None if chosen is None else year_look(chosen)


__all__ = ["ANCHORS", "ERAS", "Era", "EraError", "KINESCOPE", "MONOCHROME", "NTSC_LINES", "WARM_STOCK", "YearLook",
           "anchor_pair", "era", "era_look", "era_of_year", "kinescope", "look_for_year", "monochrome",
           "resolve_era", "resolve_look", "warm_stock", "year_look"]
