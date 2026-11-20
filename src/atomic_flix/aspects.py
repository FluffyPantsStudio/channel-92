"""The aspects a film can choose and the sizes each one renders and delivers at.

A film's aspect is the director's choice, made before anything is generated (`choose FILM aspect`). Each aspect has:

    standard  the render frame for real takes (a multiple of sizes.GRAPH_STEP on both sides)
    draft     a smaller render frame for quick looks, same aspect, same step
    control   the frame for a control video (a multiple of sizes.CONTROL_VIDEO_STEP, docs/integration-notes.md)
    delivery  the size the cut is delivered at (even sides)

Steps of 32 and 128 cannot hold every ratio exactly, so a size matches an aspect within RATIO_TOLERANCE (3 %):
16:9's standard 1280x704 is 1.82 against 1.78, the frame every film so far was made at.

The film's year (1950 to 2010, the years Channel 92 broadcasts) only suggests an aspect; it never decides one.
"""

from __future__ import annotations

from dataclasses import dataclass

RATIO_TOLERANCE = 0.03
FIRST_YEAR, LAST_YEAR = 1950, 2010
WIDESCREEN_FROM = 1998          # the year from which a Channel 92 era suggests 16:9 rather than 4:3
TIERS = ("standard", "draft")

Size = tuple[int, int]


class AspectError(ValueError):
    """An aspect, tier or year the kit does not offer; the message names what it does offer."""


@dataclass(frozen=True)
class Aspect:
    name: str
    ratio: float
    standard: Size
    draft: Size
    control: Size
    delivery: Size

    def frame(self, tier: str = "standard") -> Size:
        """The render frame of TIER."""
        if tier not in TIERS:
            raise AspectError(f"a render tier is standard or draft, not {tier!r}")
        return self.standard if tier == "standard" else self.draft


ASPECTS: dict[str, Aspect] = {
    "16:9": Aspect("16:9", 16 / 9, standard=(1280, 704), draft=(1024, 576), control=(1152, 640),
                   delivery=(1920, 1080)),
    "4:3": Aspect("4:3", 4 / 3, standard=(1024, 768), draft=(768, 576), control=(1024, 768), delivery=(1440, 1080)),
    "2.39:1": Aspect("2.39:1", 2.39, standard=(1536, 640), draft=(1152, 480), control=(1536, 640),
                     delivery=(1920, 804)),
    "9:16": Aspect("9:16", 9 / 16, standard=(704, 1280), draft=(576, 1024), control=(640, 1152),
                   delivery=(1080, 1920)),
}


def aspect(name: str) -> Aspect:
    """The table row for NAME; AspectError names the aspects on offer."""
    found = ASPECTS.get(str(name).strip())
    if found is None:
        raise AspectError(f"no aspect {name!r}; the aspects are {', '.join(ASPECTS)}")
    return found


def ratio_of(name: str) -> float:
    return aspect(name).ratio


def matches_aspect(width: int, height: int, name: str, tolerance: float = RATIO_TOLERANCE) -> bool:
    """WIDTHxHEIGHT is NAME's ratio within TOLERANCE (relative)."""
    if width <= 0 or height <= 0:
        return False
    wanted = ratio_of(name)
    return abs(width / height - wanted) <= tolerance * wanted


def check_year(year: object) -> int:
    """YEAR as an int when Channel 92 broadcast in it; AspectError otherwise."""
    try:
        value = int(str(year).strip())
    except ValueError:
        value = None
    if value is None or not FIRST_YEAR <= value <= LAST_YEAR:
        raise AspectError(f"a film's year is one Channel 92 broadcast in, {FIRST_YEAR} to {LAST_YEAR}, not {year!r}")
    return value


def suggested_aspect(year: int) -> str:
    """The aspect a film set in YEAR would have had on the channel: a suggestion for the director, never a choice."""
    return "16:9" if check_year(year) >= WIDESCREEN_FROM else "4:3"
