"""Where every word of the song's timeline strip goes, worked out before anything is drawn, so no label sits on
another and none leaves the picture.

Section names go in three lanes above the bar, longest sections first, each with a leader line down to where its
section starts; no label or leader may cross another. A name that fits nowhere shrinks to the section's number, and a
number that fits nowhere is left out (its colour block stays). When any name shrank, every name carries its number
and a key under the strip names every section with its start time; when all fit, there is no key. A story gap's label
("STORY GAP n" or "GAP n", and its seconds) goes inside its outline when it fits there whole, else in a lane under
the times with a leader line up to the outline; it is never cut.
"""

from __future__ import annotations

import math
import string
from dataclasses import dataclass
from typing import Sequence

FONT = set(string.ascii_uppercase + string.digits + ".-:/+%_><=()# ")
SCALE = 3                       # the pixel font at 3: 15 px tall, 12 px a character, legible on a phone at 1600 px
TEXT_H = 5 * SCALE
MARGIN = 12                     # no label comes nearer the picture's edge than this
PAD = 12                        # clear space between two labels in one lane
LEADER = 3                      # half the width a leader line keeps clear of any label
LANES = 3
LANE_PITCH = 30
LANE_TOP = 56                   # the top of the highest lane, under the title
BAR_HEIGHT = 114
GAP_EDGE = 6                    # a story gap's outline reaches this far past the bar
GAP_INSET = 10                  # its label's distance from the outline's inside edge
LOW_PITCH = 26                  # lanes under the times, for gap labels that do not fit inside their outline
SWATCH = 18                     # the colour square before each key entry
KEY_GAP = 28
KEY_CHARS = 40                  # a key entry's name is cut to this many characters (a section name, never a gap's)
LEGEND_H = 18


def font_text(text: str) -> str:
    """TEXT as the pixel font can draw it: upper case, characters it lacks dropped, spaces collapsed."""
    kept = "".join(char if char in FONT else ("" if char in "'`" else " ") for char in str(text).upper())
    return " ".join(kept.split())


def text_width(text: str, scale: int = SCALE) -> int:
    """How wide TEXT draws in the pixel font at SCALE (each glyph 3 wide plus a 1 column space, none after the last)."""
    count = len(font_text(text))
    return max(0, 4 * count - 1) * scale


def clock(seconds: float, tenths: bool = False) -> str:
    """Seconds as M:SS (or M:SS.s)."""
    minutes, rest = divmod(max(0.0, float(seconds)), 60.0)
    return f"{int(minutes)}:{rest:04.1f}" if tenths else f"{int(minutes)}:{int(rest):02d}"


@dataclass(frozen=True)
class Label:
    """One label: its kind (section, number, gap, time, key), its lines as drawn, its box (left, top, right, bottom)
    and the leader line (x, top, bottom) tying it to what it names, if any. A key entry's box holds its swatch."""

    kind: str
    lines: tuple[str, ...]
    box: tuple[int, int, int, int]
    leader: tuple[int, int, int] | None = None
    swatch: str = ""


@dataclass(frozen=True)
class StripPlan:
    """The strip's size, where the bar and the times sit, every label, and where the legend goes."""

    width: int
    height: int
    bar_top: int
    bar_bottom: int
    total_s: float
    labels: tuple[Label, ...]
    legend_y: int
    left: int = 24
    right: int = 24

    def x(self, seconds: float) -> int:
        span = self.width - self.left - self.right
        return self.left + int(round(span * min(max(seconds, 0.0), self.total_s) / self.total_s))


def _free(spans: Sequence[tuple[int, int]], start: int, end: int) -> bool:
    return all(end <= left or start >= right for left, right in spans)


def _text_free(texts: Sequence[tuple[int, int]], leaders: Sequence[tuple[int, int]], left: int, right: int) -> bool:
    """Whether a label from LEFT to RIGHT keeps PAD from every label and clear of every leader in its lane."""
    return _free(texts, left - PAD, right + PAD) and _free(leaders, left, right)


class _Lanes:
    """Lanes of labels, lane 0 nearest the bar; a leader from lane k crosses lanes 0 to k-1 and keeps them clear."""

    def __init__(self, tops: Sequence[int], width: int) -> None:
        self.tops, self.width = list(tops), width
        self.texts: list[list[tuple[int, int]]] = [[] for _ in tops]
        self.leaders: list[list[tuple[int, int]]] = [[] for _ in tops]

    def place(self, text: str, anchor: int, *, centred: bool = False, far_first: bool = False,
              grow: int = 0) -> tuple[int, int, int] | None:
        """(lane, left, right) for TEXT near ANCHOR (its leader's x) in the first lane it fits, or None. FAR_FIRST
        tries the lane farthest from the bar first (a long name there blocks only its leader's width in the lanes
        under it). With GROW, a label that fits no lane gets a new lane GROW past the last one instead (its leader
        may then cross a label on the way, never a label's box)."""
        wide = text_width(text)
        if wide > self.width - 2 * MARGIN:
            return None
        want = anchor - wide // 2 if centred else anchor
        left = min(max(want, MARGIN), self.width - MARGIN - wide)
        order = range(len(self.tops) - 1, -1, -1) if far_first else range(len(self.tops))
        for lane in order:
            clear = all(_free(self.texts[low], anchor - LEADER, anchor + LEADER) for low in range(lane))
            if clear and _text_free(self.texts[lane], self.leaders[lane], left, left + wide):
                self.texts[lane].append((left, left + wide))
                for low in range(lane):
                    self.leaders[low].append((anchor - LEADER, anchor + LEADER))
                return lane, left, left + wide
        if not grow:
            return None
        self.tops.append(self.tops[-1] + grow)
        self.texts.append([(left, left + wide)])
        self.leaders.append([])
        return len(self.tops) - 1, left, left + wide


def _section_text(section: dict, number: int, numbered: bool) -> str:
    name = f"{section.get('label') or section.get('id')} {clock(section['start'])}"
    return f"{number} {name}" if numbered else name


def _lane_tops() -> list[int]:
    return [LANE_TOP + (LANES - 1 - lane) * LANE_PITCH for lane in range(LANES)]


def _placed(lanes: _Lanes, kind: str, text: str, anchor: int, bar_top: int, far_first: bool) -> Label | None:
    spot = lanes.place(text, anchor, far_first=far_first and kind == "section")
    if spot is None:
        return None
    lane, left, right = spot
    top = lanes.tops[lane]
    return Label(kind, (font_text(text),), (left, top, right, top + TEXT_H), (anchor, top + TEXT_H + 3, bar_top))


def _section_labels(plan: StripPlan, sections: Sequence[dict], numbered: bool,
                    far_first: bool) -> tuple[list[Label], bool]:
    """Section labels in the lanes above the bar, longest sections first, then the numbers of those whose names
    found no room; also whether any name had to shrink."""
    lanes = _Lanes(_lane_tops(), plan.width)
    order = sorted(range(len(sections)), key=lambda i: (sections[i]["start"] - sections[i]["end"], i))
    anchors = [plan.x(section["start"]) + 1 for section in sections]
    labels, shrunk = [], []
    for index in order:
        label = _placed(lanes, "section", _section_text(sections[index], index + 1, numbered), anchors[index],
                        plan.bar_top, far_first)
        if label is None:
            shrunk.append(index)
        else:
            labels.append(label)
    for index in shrunk:
        label = _placed(lanes, "number", str(index + 1), anchors[index], plan.bar_top, far_first)
        if label is not None:
            labels.append(label)
    return labels, bool(shrunk)


def _times(plan: StripPlan) -> list[Label]:
    """The times under the bar, one every few seconds, each kept inside the picture and off the one before."""
    step = next((step for step in (5, 10, 15, 30, 60) if plan.total_s / step <= 12), 120)
    top = plan.bar_bottom + 12
    labels: list[Label] = []
    for second in range(0, int(plan.total_s) + 1, step):
        x, text = plan.x(second), clock(second)
        left = x + 6 if x + 6 + text_width(text) <= plan.width - MARGIN else x - 4 - text_width(text)
        box = (left, top, left + text_width(text), top + TEXT_H)
        if labels and box[0] < labels[-1].box[2] + PAD:
            continue
        labels.append(Label("time", (text,), box, (x, plan.bar_bottom + 8, plan.bar_bottom + 20)))
    return labels


def _gap_lines(gap: dict, story: bool) -> tuple[str, ...]:
    # by its start time, not its rank by length: the director counts gaps through the song, and a time cannot be mixed up
    name = f"{'STORY GAP' if story else 'GAP'} {clock(gap['start'])}" if "start" in gap else         f"{'STORY GAP' if story else 'GAP'} {gap.get('rank', '')}".strip()
    seconds = gap.get("duration_s")
    return (name,) if seconds is None else (name, f"{float(seconds):.0f} S")


def _gap_inside(plan: StripPlan, gap: dict) -> Label | None:
    """GAP's label inside its outline, two lines at its top left, when one of its forms fits there whole."""
    left, right = plan.x(gap["start"]), max(plan.x(gap["start"]) + 9, plan.x(gap["end"]))
    room = right - left - 2 * GAP_INSET
    for story in (True, False):
        lines = _gap_lines(gap, story)
        wide = max(text_width(line) for line in lines)
        if wide <= room:
            top = plan.bar_top + GAP_INSET
            bottom = top + TEXT_H * len(lines) + (LOW_PITCH - TEXT_H) * (len(lines) - 1)
            return Label("gap", lines, (left + GAP_INSET, top, left + GAP_INSET + wide, bottom))
    return None


def _clear_anchor(gap_left: int, gap_right: int, times: Sequence[Label]) -> int:
    """An x inside the gap's outline where a leader down from it crosses no time label or tick, else the middle."""
    blocked = [(t.box[0] - LEADER, t.box[2] + LEADER) for t in times]
    blocked += [(t.leader[0] - LEADER, t.leader[0] + 2 + LEADER) for t in times if t.leader]
    middle = (gap_left + gap_right) // 2
    for x in sorted(range(gap_left + 6, gap_right - 5), key=lambda x: abs(x - middle)):
        if _free(blocked, x - 1, x + 1):
            return x
    return middle


def _gap_labels(plan: StripPlan, gaps: Sequence[dict], times: Sequence[Label]) -> tuple[list[Label], int]:
    """Every story gap's label: inside its outline when it fits whole, else under the times with a leader up to the
    outline. Also the lowest y the labels under the times reach."""
    top = plan.bar_bottom + 12 + TEXT_H + 14
    lanes = _Lanes([top], plan.width)
    labels, bottom = [], plan.bar_bottom + 12 + TEXT_H
    for gap in gaps:
        inside = _gap_inside(plan, gap)
        if inside is not None:
            labels.append(inside)
            continue
        line = " ".join(_gap_lines(gap, False))
        anchor = _clear_anchor(plan.x(gap["start"]), max(plan.x(gap["start"]) + 9, plan.x(gap["end"])), times)
        lane, left, right = lanes.place(line, anchor, centred=True, grow=LOW_PITCH)
        y = lanes.tops[lane]
        labels.append(Label("gap", (font_text(line),), (left, y, right, y + TEXT_H),
                            (anchor, plan.bar_bottom + GAP_EDGE, y - 3)))
        bottom = max(bottom, y + TEXT_H)
    return labels, bottom


def _key(plan: StripPlan, sections: Sequence[dict], top: int) -> tuple[list[Label], int]:
    """Every section by number, name and start time, in columns read top to bottom; also the key's bottom."""
    texts = [font_text(f"{n + 1} {font_text(section.get('label') or section.get('id'))[:KEY_CHARS]} "
                       f"{clock(section['start'])}") for n, section in enumerate(sections)]
    cell = SWATCH + 8 + max(text_width(text) for text in texts)
    columns = max(1, min(len(texts), (plan.width - 2 * MARGIN + KEY_GAP) // (cell + KEY_GAP)))
    rows = math.ceil(len(texts) / columns)
    labels = []
    for n, (text, section) in enumerate(zip(texts, sections)):
        column, row = divmod(n, rows)
        left, y = MARGIN + column * (cell + KEY_GAP), top + row * LOW_PITCH
        right = left + SWATCH + 8 + text_width(text)
        labels.append(Label("key", (text,), (left, y, right, y + TEXT_H), swatch=str(section.get("kind") or "")))
    return labels, top + rows * LOW_PITCH - (LOW_PITCH - TEXT_H)


def strip_plan(structure: dict, width: int = 1600) -> StripPlan:
    """The layout of the timeline strip for STRUCTURE: its size and every label's box, nothing drawn yet."""
    sections = list(structure.get("sections") or [])
    total_s = float(structure.get("song_s") or (sections[-1]["end"] if sections else 0.0))
    if total_s <= 0 or not sections:
        raise ValueError("the structure has no sections")
    bar_top = LANE_TOP + (LANES - 1) * LANE_PITCH + TEXT_H + 13
    plan = StripPlan(width, 0, bar_top, bar_top + BAR_HEIGHT, total_s, (), 0)
    names, shrunk = _section_labels(plan, sections, numbered=False, far_first=False)
    if shrunk:
        names, shrunk = _section_labels(plan, sections, numbered=False, far_first=True)
    if shrunk:
        names, _ = _section_labels(plan, sections, numbered=True, far_first=True)
    times = _times(plan)
    gaps, low = _gap_labels(plan, (structure.get("pacing") or {}).get("story_gaps") or [], times)
    key, low = _key(plan, sections, low + 28) if shrunk else ([], low)
    legend_y = low + 24
    return StripPlan(width, legend_y + LEGEND_H + 22, plan.bar_top, plan.bar_bottom, total_s,
                     tuple(names + times + gaps + key), legend_y)
