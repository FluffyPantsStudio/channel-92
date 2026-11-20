"""Years between eras: each era's preset is the look of its decade's first year (1950, 1960 ... 2000), and a year
between two of them blends the two presets by the fraction of the way (looks.blend_presets, eras.look_for_year)."""

from __future__ import annotations

import pytest

from atomic_flix.aspects import FIRST_YEAR, LAST_YEAR, AspectError
from atomic_flix.eras import ANCHORS, ERAS, anchor_pair, era, look_for_year, year_look
from atomic_flix.looks import SETTINGS, check_preset, load_preset
from atomic_flix.looks.blend import CYCLIC, FADE_IN, GROUPS, STRENGTH, blend_presets

IDS = [row.id for row in ERAS]
YEARS = range(FIRST_YEAR, LAST_YEAR + 1)


def _on(preset: dict, switch: str) -> bool:
    return preset["snow_intensity"] > 0 if switch == "snow" else preset[switch]


def _effective(preset: dict, switch: str, key: str) -> float:
    """What a strength setting does on the picture: its value while its group is on, nothing while it is off."""
    return preset[key] if _on(preset, switch) else 0.0


# --- anchors and edges ----------------------------------------------------------------------------------------------

def test_the_anchors_are_the_decade_starts():
    assert ANCHORS == {"1950s": 1950, "1960s": 1960, "1970s": 1970, "1980s": 1980, "1990s": 1990, "2000s": 2000}


@pytest.mark.parametrize("era_id", IDS)
def test_an_anchor_year_gives_that_eras_preset_exactly(era_id):
    exact = load_preset(era_id)
    got = look_for_year(ANCHORS[era_id])
    assert set(got) == set(exact)
    for key, value in exact.items():
        assert got[key] == value and type(got[key]) is type(value), key


@pytest.mark.parametrize("year", range(2000, 2011))
def test_the_2000s_to_2010_are_the_2000s_look(year):
    assert look_for_year(year) == load_preset("2000s")


@pytest.mark.parametrize("year, low, high, weight", [
    (1950, "1950s", "1950s", 0.0), (1955, "1950s", "1960s", 0.5), (1956, "1950s", "1960s", 0.6),
    (1960, "1960s", "1960s", 0.0), (1964, "1960s", "1970s", 0.4), (1975, "1970s", "1980s", 0.5),
    (1987, "1980s", "1990s", 0.7), (1996, "1990s", "2000s", 0.6), (2000, "2000s", "2000s", 0.0),
    (2004, "2000s", "2000s", 0.0), (2010, "2000s", "2000s", 0.0)])
def test_the_weight_is_the_fraction_of_the_way_between_two_decade_starts(year, low, high, weight):
    a, b, w = anchor_pair(year)
    assert (a.id, b.id) == (low, high) and w == pytest.approx(weight)


@pytest.mark.parametrize("year", [1949, 2011, "soon"])
def test_a_year_off_the_air_is_refused(year):
    with pytest.raises(AspectError):
        look_for_year(year)


@pytest.mark.parametrize("year", YEARS)
def test_every_year_gives_a_preset_ntsc_rs_reads(year):
    assert check_preset(look_for_year(year)) == []


# --- the blending rules ---------------------------------------------------------------------------------------------

def test_1975_is_the_exact_midpoint_on_floats_that_both_anchors_share():
    low, high, mid = load_preset("1970s"), load_preset("1980s"), look_for_year(1975)
    grouped = {key: group for group in GROUPS for key in group.keys}
    for key, setting in SETTINGS.items():
        if setting.kind not in ("float", "share"):
            continue
        group = grouped.get(key)
        if group is not None and not (group.is_on(low) and group.is_on(high)):
            continue
        assert mid[key] == (low[key] + high[key]) / 2, key
    assert mid["luma_noise_intensity"] == (0.006 + 0.015) / 2        # a group on at both anchors


def _turns(a: float, b: float) -> float:
    """The circular distance between two phases, in turns (0 to 0.5)."""
    gap = abs(a - b) % 1.0
    return min(gap, 1.0 - gap)


def test_the_phase_error_is_a_turn_and_blends_the_short_way_round():
    base = load_preset("1970s")
    low, high = {**base, "chroma_phase_error": 0.95}, {**base, "chroma_phase_error": 0.05}
    half = blend_presets(low, high, 0.5)["chroma_phase_error"]
    assert _turns(half, 0.0) < 1e-9 and 0.0 <= half <= 1.0
    quarter = blend_presets(low, high, 0.25)["chroma_phase_error"]
    assert _turns(quarter, 0.975) < 1e-9 and 0.0 <= quarter <= 1.0
    assert check_preset(blend_presets(low, high, 0.5)) == []
    assert CYCLIC == {"chroma_phase_error": 1.0}                    # the only angle among the settings


@pytest.mark.parametrize("year", YEARS)
def test_every_years_phase_error_lies_on_the_short_arc_between_its_anchors(year):
    low, high, weight = anchor_pair(year)
    a, b = load_preset(low.id)["chroma_phase_error"], load_preset(high.id)["chroma_phase_error"]
    got = look_for_year(year)["chroma_phase_error"]
    assert _turns(got, a) + _turns(got, b) == pytest.approx(_turns(a, b), abs=1e-9)
    assert _turns(got, a) == pytest.approx(weight * _turns(a, b), abs=1e-9)
    if 1950 <= year <= 1960:
        assert _turns(got, 0.0) <= 0.015 + 1e-9                      # a few degrees, never a hue turned round


def test_the_1960s_phase_error_stays_exact_at_its_anchor():
    assert look_for_year(1960)["chroma_phase_error"] == 0.985


def test_whole_numbers_are_interpolated_then_rounded():
    blended = blend_presets(load_preset("1950s"), load_preset("1960s"), 0.3)
    assert blended["composite_noise_detail"] == 2                   # 2 to 1, 30 % of the way: 1.7
    assert type(blended["composite_noise_detail"]) is int
    assert blend_presets(load_preset("1950s"), load_preset("1960s"), 0.6)["composite_noise_detail"] == 1


def test_menu_settings_take_the_nearer_anchor_and_a_tie_goes_to_the_later_era():
    low, high = load_preset("1950s"), load_preset("1960s")
    assert blend_presets(low, high, 0.4)["chroma_demodulation"] == low["chroma_demodulation"]
    assert blend_presets(low, high, 0.5)["chroma_demodulation"] == high["chroma_demodulation"]
    assert blend_presets(low, high, 0.5)["random_seed"] == high["random_seed"]
    assert look_for_year(1954)["random_seed"] == 1950
    assert look_for_year(1955)["random_seed"] == 1960 and look_for_year(1956)["random_seed"] == 1960


def test_a_group_off_at_both_anchors_stays_off():
    for year in range(1951, 1960):                                   # head switching, tracking: off in both
        preset = look_for_year(year)
        assert not preset["head_switching"] and not preset["tracking_noise"] and not preset["scale_settings"]


def test_a_group_on_at_one_anchor_fades_in_from_a_fifth_of_the_way():
    low, high = load_preset("1970s"), load_preset("1980s")
    under, over = blend_presets(low, high, FADE_IN - 0.01), blend_presets(low, high, FADE_IN + 0.01)
    assert not under["tracking_noise"] and not under["head_switching"]
    assert over["tracking_noise"] and over["head_switching"]
    assert over["tracking_noise_wave_intensity"] == pytest.approx(high["tracking_noise_wave_intensity"] * 0.21)
    assert over["tracking_noise_height"] == round(high["tracking_noise_height"] * 0.21)
    assert over["tracking_noise_snow_anisotropy"] == high["tracking_noise_snow_anisotropy"]   # not a strength
    assert not look_for_year(1971)["tracking_noise"] and look_for_year(1972)["tracking_noise"]


def test_a_group_on_at_the_earlier_anchor_fades_out_the_same_way():
    assert look_for_year(1998)["vhs_settings"] and not look_for_year(1999)["vhs_settings"]
    assert look_for_year(1963)["vhs_settings"]                      # the 1960s carry it, at 70 %
    assert not look_for_year(1951)["vhs_settings"] and look_for_year(1952)["vhs_settings"]
    assert look_for_year(1994)["vhs_edge_wave"] == pytest.approx(1.0 * 0.6)


def test_tracking_noise_strength_rises_from_1970_to_1980():
    for key in ("tracking_noise_height", "tracking_noise_wave_intensity", "tracking_noise_noise_intensity",
                "tracking_noise_snow_intensity"):
        values = [_effective(look_for_year(year), "tracking_noise", key) for year in range(1970, 1981)]
        assert values == sorted(values) and values[0] == 0 and values[-1] > 0, key


def test_vhs_strength_falls_from_1990_to_2000():
    for key in ("vhs_edge_wave", "vhs_chroma_loss"):
        values = [_effective(look_for_year(year), "vhs_settings", key) for year in range(1990, 2001)]
        assert values == sorted(values, reverse=True) and values[-1] == 0, key


def test_snow_counts_as_a_group_and_fades_too():
    assert look_for_year(1971)["snow_intensity"] == 0.0
    assert look_for_year(1975)["snow_intensity"] == pytest.approx(0.00025 * 0.5)


def test_the_strength_members_are_documented_and_belong_to_their_groups():
    keys = {key for group in GROUPS for key in group.keys}
    assert set(STRENGTH) <= keys
    assert {"composite_noise_intensity", "snow_intensity", "head_switching_height",
            "head_switching_horizontal_shift", "tracking_noise_height", "tracking_noise_wave_intensity",
            "tracking_noise_snow_intensity", "tracking_noise_noise_intensity", "ringing_scale",
            "luma_noise_intensity", "chroma_noise_intensity", "vhs_chroma_loss", "vhs_sharpen", "vhs_edge_wave",
            "bandwidth_scale", "vertical_scale"} == set(STRENGTH)
    assert STRENGTH["bandwidth_scale"] == 1.0 and STRENGTH["ringing_scale"] == 0.0


def test_the_weight_must_lie_between_0_and_1():
    with pytest.raises(ValueError):
        blend_presets(load_preset("1950s"), load_preset("1960s"), 1.5)


def test_blending_leaves_its_inputs_alone():
    low, high = load_preset("1970s"), load_preset("1980s")
    before = (dict(low), dict(high))
    blend_presets(low, high, 0.5)
    assert (low, high) == before


# --- logo, intro and the progress sentence --------------------------------------------------------------------------

@pytest.mark.parametrize("year, decade", [(1956, "1950s"), (1960, "1960s"), (1969, "1960s"), (2010, "2000s")])
def test_the_logo_and_intro_follow_the_decade_not_the_blend(year, decade):
    assert year_look(year).era is era(decade)


@pytest.mark.parametrize("year, sentence", [
    (1956, "year 1956: the 1950s look, 60 percent of the way to the 1960s"),
    (1964, "year 1964: the 1960s look, 40 percent of the way to the 1970s"),
    (1975, "year 1975: halfway between the 1970s and the 1980s looks"),
    (1970, "year 1970: the 1970s look"),
    (2008, "year 2008: the 2000s look"),
    (1987, "year 1987: the 1980s look, 70 percent of the way to the 1990s")])
def test_the_look_is_said_in_one_plain_line(year, sentence):
    assert year_look(year).describe() == sentence


def test_the_blend_demo_names_the_pair_the_weight_and_what_differs(tool, capsys):
    demo = tool("blend_demo")
    assert demo.main(["1956"]) == 0
    text = capsys.readouterr().out
    assert "between 1950s (1950) and 1960s (1960), weight 0.6 toward 1960s" in text
    assert "nearer anchor 1960s" in text and "chroma_phase_error: 0.985 ->" in text
    assert "random_seed" not in text                                  # the nearer anchor's seed, unchanged
    assert demo.main(["1970"]) == 0
    assert "0 setting(s) differ from the 1970s preset" in capsys.readouterr().out
    assert demo.main(["1949"]) == 2
