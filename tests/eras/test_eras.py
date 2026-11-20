"""Channel 92's six eras: every broadcast year belongs to exactly one, the film's year picks it, `--era` overrides
it, and a film with neither has no era (and so no look)."""

from __future__ import annotations

import pytest

from atomic_flix.aspects import FIRST_YEAR, LAST_YEAR, AspectError, suggested_aspect
from atomic_flix.eras import ERAS, EraError, era, era_of_year, resolve_era
from atomic_flix.brand.logo import DEFAULT_LOGO, png_size

IDS = ["1950s", "1960s", "1970s", "1980s", "1990s", "2000s"]


def test_there_are_six_eras_in_broadcast_order():
    assert [row.id for row in ERAS] == IDS
    assert ERAS[0].first == FIRST_YEAR and ERAS[-1].last == LAST_YEAR
    for earlier, later in zip(ERAS, ERAS[1:]):
        assert later.first == earlier.last + 1


@pytest.mark.parametrize("year", range(FIRST_YEAR, LAST_YEAR + 1))
def test_every_broadcast_year_has_its_decade(year):
    found = era_of_year(year)
    assert found.first <= year <= found.last
    assert found.id == ("2000s" if year == 2010 else f"{year // 10 * 10}s")


@pytest.mark.parametrize("year, expected", [(1959, "1950s"), (1960, "1960s"), (2009, "2000s"), (2010, "2000s"),
                                            (1950, "1950s"), ("1987", "1980s")])
def test_the_edges(year, expected):
    assert era_of_year(year).id == expected


@pytest.mark.parametrize("year", [1949, 2011, "soon", None])
def test_a_year_off_the_air_is_refused(year):
    with pytest.raises(AspectError):
        era_of_year(year)


def _film(year=None):
    return {"setup": {"aspect": "4:3", **({"year": year} if year is not None else {})}}


def test_the_films_year_picks_the_era():
    assert resolve_era(_film(1987)).id == "1980s"
    assert resolve_era(_film(1998)).id == "1990s"


def test_the_override_wins_over_the_year():
    assert resolve_era(_film(1987), "1950s").id == "1950s"
    assert resolve_era(_film(), "2000s").id == "2000s"


def test_no_year_and_no_override_is_no_era():
    assert resolve_era(_film()) is None
    assert resolve_era({}) is None


def test_an_unknown_era_is_refused_by_name():
    with pytest.raises(EraError) as caught:
        resolve_era(_film(1987), "1940s")
    assert "1940s" in str(caught.value) and "1950s" in str(caught.value) and "2000s" in str(caught.value)
    with pytest.raises(EraError):
        era("eighties")


@pytest.mark.parametrize("row", ERAS, ids=IDS)
def test_every_era_has_its_medium_preset_and_logo(row):
    assert row.medium and len(row.medium) < 200 and chr(0x2014) not in row.medium
    assert row.preset.is_file() and row.preset.name == f"{row.id}.json"
    assert row.preset.parent.name == "looks"
    assert row.logo.is_file()
    width, height = png_size(row.logo)
    assert width >= 600 and height >= 200


def test_the_2000s_wear_the_channels_own_mark_and_the_older_eras_their_own():
    assert era("2000s").logo == DEFAULT_LOGO
    older = {era(name).logo for name in IDS[:-1]}
    assert len(older) == 5 and DEFAULT_LOGO not in older


def test_the_suggested_aspect_comes_from_the_aspect_table():
    for row in ERAS:
        assert row.suggested_aspect() == suggested_aspect(row.first)
        assert row.suggested_aspect(row.last) == suggested_aspect(row.last)
    assert era("1990s").suggested_aspect(1999) == "16:9" and era("1990s").suggested_aspect() == "4:3"


def test_only_the_1950s_need_a_monochrome_pre_filter_before_ntsc_rs():
    fifties = era("1950s").prefilter
    assert fifties and "u=128" in fifties and "v=128" in fifties
    for row in ERAS[1:]:
        assert row.prefilter is None or "u=128" not in row.prefilter


def test_each_era_has_its_scanlines_for_ntsc_rs():
    assert {row.lines for row in ERAS} == {480}
