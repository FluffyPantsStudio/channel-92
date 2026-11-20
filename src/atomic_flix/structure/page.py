"""plan/structure.md: the song's structure as a page a person reads at gate 1, beside the concept."""

from __future__ import annotations

from typing import Sequence

from .measures import MIXED_QUIET_S, TREND_DB
from .pacing import SAME_DB
from .sections import INSTRUMENTAL_MIN_S, UNLABELLED

COUNTS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")
UNSETTLED = "needs_click_check"
ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth")


def count(n: int) -> str:
    return COUNTS[n] if 0 <= n < len(COUNTS) else str(n)


def ordinal(n: int) -> str:
    return ORDINALS[n - 1] if 1 <= n <= len(ORDINALS) else f"{n}th"


def clock(seconds: float) -> str:
    """m:ss, the seconds cut (not rounded) the way a player shows them."""
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def clock_tenths(seconds: float) -> str:
    minutes, rest = divmod(round(seconds, 1), 60)
    return f"{int(minutes)}:{rest:04.1f}"


def percent(share: float) -> str:
    return f"{round(100 * share)} percent"


def _gaps_phrase(pacing: dict) -> str:
    gaps, threshold = pacing["story_gaps"], pacing["story_gap_threshold_s"]
    if not gaps:
        return f"no instrumental break of {threshold:g} s or more"
    longest = gaps[0]
    plural = "break" if len(gaps) == 1 else "breaks"
    return (f"{count(len(gaps))} instrumental {plural} of {threshold:g} s or more, the longest "
            f"{longest['duration_s']:.0f} s at {clock(longest['measured'][0])}")


def _repeat_sentence(repeat: dict) -> str:
    times = repeat["times"]
    parts = []
    for n, row in enumerate(times[1:], start=2):
        if row["vs_first_db"] is None:
            parts.append(f"the {ordinal(n)} not measured")
        elif row["differs"] == "same":
            parts.append(f"the {ordinal(n)} the same within {SAME_DB:g} dB")
        else:
            parts.append(f"the {ordinal(n)} {abs(row['vs_first_db']):.1f} dB {row['differs']}")
    return (f"The {repeat['label']} comes {count(len(times))} times; the band under it against the first time: "
            f"{', '.join(parts)}.")


def reading(data: dict) -> str:
    """A few sentences made from the numbers only."""
    pacing = data["pacing"]
    first = (f"{clock(pacing['total_s'])} long; {percent(pacing['sung_share'])} in sung sections, the voice on "
             f"{percent(pacing['voice_on_share'])} of the time; {_gaps_phrase(pacing)}.")
    sentences = [first]
    if pacing["first_voice_s"] is not None:
        longest = pacing["longest_sung"]
        sentences.append(f"The voice first comes in at {clock(pacing['first_voice_s'])}; the longest unbroken sung "
                         f"stretch is {longest['duration_s']:.0f} s ({clock(longest['start'])} to "
                         f"{clock(longest['end'])}: {', '.join(longest['labels'])}).")
    sentences += [_repeat_sentence(repeat) for repeat in pacing["repeats"]]
    return " ".join(sentences)


def _bar_line(data: dict) -> str:
    if not data["snapped"]:
        return ("Edges are not snapped to the bar: there is no bar's one yet (`atomic-flix bars`). Times are where "
                "the voice starts and stops.")
    line = (f"Edges are snapped to the nearest bar's one (a bar is {data['bar_s']:.2f} s); the Snap column says how "
            "far each edge moved from where the voice starts or stops.")
    if data.get("ruling") == UNSETTLED:
        line += (f" The bar's one is not settled (`bars` ruling: {data['ruling']}), so an edge may sit two beats off "
                 "until the click check before gate 2.")
    return line


def _cell_swells(swells: Sequence[dict]) -> str:
    return ", ".join(clock_tenths(s["t"]) for s in swells) or "-"


def _row(section: dict) -> str:
    bars = f"{section['bars']:.1f}" if section["bars"] is not None else "-"
    moves = section["trend"] + (f" {section['change_db']:+.1f} dB" if section["change_db"] is not None else "")
    snap = "-" if section["snap_s"] == [0.0, 0.0] else f"{section['snap_s'][0]:+.2f} / {section['snap_s'][1]:+.2f}"
    lines = " ".join(section["lines"]) or "-"
    unsure = f" (uncertain: {' '.join(section['uncertain_lines'])})" if section["uncertain_lines"] else ""
    return (f"| {section['id']} | {section['label']} | {section['kind']} | {clock_tenths(section['start'])} | "
            f"{clock_tenths(section['end'])} | {section['duration_s']:.1f} | {bars} | {snap} | "
            f"{round(100 * section['voice_share'])} | {section['rest_level']:.2f} | {moves} | "
            f"{_cell_swells(section['swells'])} | {lines}{unsure} |")


def _sections(data: dict) -> list[str]:
    out = ["## Sections", "", _bar_line(data), "",
           "| # | Section | Kind | Start | End | Seconds | Bars | Snap (s) | Voice on % | Band level | Band moves | "
           "Swells | Lines |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    out += [_row(section) for section in data["sections"]]
    if any(section["label"] == UNLABELLED for section in data["sections"]):
        out += ["", f"{UNLABELLED}: the lead stem sings here but the lyric has no line timed here (an ad lib, a part "
                    "not written in lyric.txt, or a line `time` placed elsewhere). Listen, then write it into the "
                    "lyric or leave it."]
    return out


def _story_gaps(pacing: dict) -> list[str]:
    out = ["", f"## Story gaps: instrumental stretches of {pacing['story_gap_threshold_s']:g} s or more", "",
           "Here the voice is silent and the pictures carry the story.", ""]
    if not pacing["story_gaps"]:
        return out + [f"None: no instrumental break of {pacing['story_gap_threshold_s']:g} s or more."]
    for gap in pacing["story_gaps"]:
        start, end = gap["measured"]
        on_bars = (f" (on the bar {clock_tenths(gap['start'])} to {clock_tenths(gap['end'])}, {gap['bars']:.1f} bars)"
                   if gap["bars"] is not None else "")
        out.append(f"{gap['rank']}. {gap['duration_s']:.1f} s without the voice, {clock_tenths(start)} to "
                   f"{clock_tenths(end)}{on_bars}, after {gap['after'] or 'the start'}, before "
                   f"{gap['before'] or 'the end'}")
    return out


def _limits(data: dict) -> list[str]:
    out = ["", "## Limits", "", f"- {data['limit']}",
           f"- Sung means the lead stem is over its quiet line (18 dB under its working level, "
           f"{data['lead_working_db']} dBFS); a held note's decay down to {data['tail_line_db']} dBFS still counts. "
           "Other stems' voices are not read.",
           f"- An instrumental section is {INSTRUMENTAL_MIN_S:g} s or more with the lead silent; a section is mixed "
           f"when the voice rests {MIXED_QUIET_S:g} s or more inside it.",
           f"- Band level is the {data['rest_stem']} stem's loudness against its own loudest second (1.00); it rises "
           f"or falls when its last third is {TREND_DB:g} dB or more above or below its first third."]
    out += [f"- {note}" for note in data["notes"]]
    regions = ", ".join(f"{a:.1f} to {b:.1f}" for a, b in data["vocal_regions"]) or "none"
    return out + ["", "## Where the lead sings (seconds, measured)", "", regions]


def structure_page(data: dict, film_name: str) -> str:
    """The Markdown page for plan/structure.md."""
    lines = [f"# {film_name}: the song's structure", "", reading(data), ""]
    lines += _sections(data) + _story_gaps(data["pacing"]) + _limits(data)
    return "\n".join(lines) + "\n"
