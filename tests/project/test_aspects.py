"""The aspect table: four aspects, each with render frames that keep the kit's size rules and a delivery size."""

import pytest

from atomic_flix.aspects import (ASPECTS, AspectError, aspect, check_year, matches_aspect, ratio_of,
                                 suggested_aspect)
from atomic_flix.sizes import CONTROL_VIDEO_STEP, GRAPH_STEP


def test_the_four_aspects_are_offered():
    assert list(ASPECTS) == ["16:9", "4:3", "2.39:1", "9:16"]


@pytest.mark.parametrize("name", list(ASPECTS))
def test_every_frame_keeps_the_size_rules_and_the_ratio(name):
    row = aspect(name)
    for width, height in (row.standard, row.draft):
        assert width % GRAPH_STEP == 0 and height % GRAPH_STEP == 0
        assert matches_aspect(width, height, name), (name, width, height)
    assert row.control[0] % CONTROL_VIDEO_STEP == 0 and row.control[1] % CONTROL_VIDEO_STEP == 0
    assert matches_aspect(*row.control, name)
    assert row.delivery[0] % 2 == 0 and row.delivery[1] % 2 == 0
    assert matches_aspect(*row.delivery, name)
    assert row.draft[0] * row.draft[1] < row.standard[0] * row.standard[1]


def test_sixteen_nine_standard_stays_what_existing_films_use():
    row = aspect("16:9")
    assert row.standard == (1280, 704) and row.delivery == (1920, 1080)
    assert row.frame("standard") == (1280, 704) and row.frame("draft") == row.draft


def test_an_unknown_aspect_or_tier_is_refused_by_name():
    with pytest.raises(AspectError, match="16:9, 4:3, 2.39:1, 9:16"):
        aspect("21:9")
    with pytest.raises(AspectError, match="standard or draft"):
        aspect("4:3").frame("huge")


def test_ratios_far_apart_do_not_match():
    assert not matches_aspect(1280, 704, "4:3")
    assert not matches_aspect(320, 192, "16:9")       # 1.67 is not 16:9
    assert matches_aspect(1920, 804, "2.39:1")
    assert ratio_of("9:16") == pytest.approx(0.5625)


def test_the_year_is_checked_and_only_suggests_an_aspect():
    assert check_year(1950) == 1950 and check_year("2010") == 2010
    for wrong in (1949, 2011, "nineteen"):
        with pytest.raises(AspectError, match="1950 to 2010"):
            check_year(wrong)
    assert suggested_aspect(1962) == "4:3"
    assert suggested_aspect(2008) == "16:9"
