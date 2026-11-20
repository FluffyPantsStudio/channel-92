"""For tuning the years between eras: what a year's look is made of.

    python tools/blend_demo.py 1956

prints the two eras the year lies between, the share of the way to the later one, the ffmpeg filters, and every
preset setting that differs from the nearer era's own preset (that era's value, then the year's). The rules are in
docs/eras.md ("Years between eras") and `atomic_flix/looks/blend.py`.
"""

from __future__ import annotations

import argparse
import sys

from atomic_flix.aspects import FIRST_YEAR, LAST_YEAR, AspectError
from atomic_flix.eras import ANCHORS, year_look
from atomic_flix.looks import load_preset


def report(year: object) -> list[str]:
    """The lines `blend_demo` prints for YEAR; AspectError for a year off the air."""
    look = year_look(year)
    nearer = look.nearer
    anchor = load_preset(nearer.id)
    lines = [look.describe(),
             f"between {look.low.id} ({ANCHORS[look.low.id]}) and {look.high.id} ({ANCHORS[look.high.id]}), "
             f"weight {look.weight:g} toward {look.high.id}; nearer anchor {nearer.id}; logo and intro {look.era.id}",
             f"pre-filter:  {look.prefilter or 'none'}",
             f"post-filter: {look.postfilter or 'none'}"]
    changed = [key for key in anchor if look.preset[key] != anchor[key]]
    lines.append(f"{len(changed)} setting(s) differ from the {nearer.id} preset" + (":" if changed else ""))
    lines += [f"  {key}: {anchor[key]!r} -> {look.preset[key]!r}" for key in changed]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("year", help=f"a Channel 92 year, {FIRST_YEAR} to {LAST_YEAR}")
    args = parser.parse_args(argv)
    try:
        print("\n".join(report(args.year)))
    except AspectError as problem:
        print(problem, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
