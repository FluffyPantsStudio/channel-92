"""The gate 1 timeline strip's labels: laid out before drawing, so none sits on another, none leaves the picture, and
every story gap keeps its whole label ("GAP n" and its seconds)."""

from __future__ import annotations

from itertools import combinations

import pytest

from atomic_flix.desk.pictures import STRIP_SIZE, timeline_strip
from atomic_flix.desk.strip import clock, strip_plan
from deskfilm import STRUCTURE

# The sections of a real 5:07 song with 21 sections (label, kind, start, end), copied from its analysis, and its four
# story gaps (rank, start, end, seconds): short sections cluster in the first 20 seconds and the last 40.
CLUSTERED = (
    ("Instrumental 1", "instrumental", 0.0, 4.93), ("unlabelled vocal", "sung", 4.93, 5.76),
    ("Instrumental 2", "instrumental", 5.76, 13.33), ("Intro", "sung", 13.33, 19.56),
    ("Instrumental 3", "instrumental", 19.56, 44.59), ("unlabelled vocal", "mixed", 44.59, 52.94),
    ("Verse 1", "sung", 52.94, 67.52), ("Chorus", "sung", 67.52, 90.5),
    ("Instrumental 4", "instrumental", 90.5, 103.03), ("Verse 2", "sung", 103.03, 119.72),
    ("Chorus", "sung", 119.72, 142.69), ("Instrumental 5", "instrumental", 142.69, 186.54),
    ("Bridge", "sung", 186.54, 205.34), ("Chorus", "sung", 205.34, 230.39),
    ("Instrumental 6", "instrumental", 230.39, 257.55), ("Outro", "sung", 257.55, 272.17),
    ("Instrumental 7", "instrumental", 272.17, 278.44), ("Outro (continued)", "sung", 278.44, 295.18),
    ("unlabelled vocal", "sung", 295.18, 299.37), ("Instrumental 8", "instrumental", 299.37, 303.55),
    ("unlabelled vocal", "sung", 303.55, 307.6),
)
CLUSTERED_GAPS = ((1, 142.69, 186.54, 44.2), (2, 230.39, 257.55, 27.56), (3, 19.56, 44.59, 26.99),
                  (4, 90.5, 103.03, 13.74))


def structure(sections, gaps=(), song_s=None) -> dict:
    rows = [{"id": f"s{n + 1:02d}", "label": label, "kind": kind, "start": start, "end": end}
            for n, (label, kind, start, end) in enumerate(sections)]
    return {"song_s": song_s or rows[-1]["end"], "sections": rows,
            "pacing": {"story_gaps": [{"rank": rank, "start": start, "end": end, "duration_s": seconds}
                                      for rank, start, end, seconds in gaps]}}


def even(count: int, song_s: float = 240.0) -> dict:
    step = song_s / count
    kinds = ("sung", "instrumental", "mixed")
    return structure([(f"Part {n + 1}", kinds[n % 3], n * step, (n + 1) * step) for n in range(count)])


def overlaps(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def assert_clean(plan) -> None:
    for label in plan.labels:
        left, top, right, bottom = label.box
        assert 0 <= left < right <= plan.width and 0 <= top < bottom <= plan.height, label
    for one, other in combinations(plan.labels, 2):
        assert not overlaps(one.box, other.box), (one, other)


def test_the_clustered_song_has_no_label_over_another_and_none_off_the_picture():
    plan = strip_plan(structure(CLUSTERED, CLUSTERED_GAPS))
    assert plan.width <= STRIP_SIZE[0]
    assert_clean(plan)


def test_every_story_gap_keeps_its_whole_label_inside_the_picture():
    plan = strip_plan(structure(CLUSTERED, CLUSTERED_GAPS))
    gaps = [label for label in plan.labels if label.kind == "gap"]
    assert len(gaps) == len(CLUSTERED_GAPS)
    for _, start, _, seconds in CLUSTERED_GAPS:
        texts = [" ".join(label.lines) for label in gaps]
        assert any(f"GAP {clock(start)}" in text and f"{seconds:.0f} S" in text for text in texts), texts


def test_a_gap_too_narrow_for_its_label_gets_it_outside_with_a_leader():
    plan = strip_plan(structure(CLUSTERED, CLUSTERED_GAPS))
    narrow_gap = min(CLUSTERED_GAPS, key=lambda gap: gap[3])        # the shortest gap is the narrowest outline
    narrow = next(label for label in plan.labels
                  if label.kind == "gap" and f"GAP {clock(narrow_gap[1])}" in " ".join(label.lines))
    assert narrow.leader is not None
    assert narrow.box[1] > plan.bar_bottom                 # under the bar, not cut off inside the box


def test_crowded_sections_are_numbered_and_the_key_names_every_one_with_its_start():
    plan = strip_plan(structure(CLUSTERED, CLUSTERED_GAPS))
    key = [" ".join(label.lines) for label in plan.labels if label.kind == "key"]
    assert len(key) == len(CLUSTERED)
    assert key[0].startswith("1 ") and key[0].endswith("0:00")
    assert any(text.startswith("18 OUTRO (CONTINUED)") and text.endswith("4:38") for text in key), key


def test_a_short_song_with_room_for_every_name_has_no_key():
    plan = strip_plan(STRUCTURE)
    assert not [label for label in plan.labels if label.kind == "key"]
    names = [" ".join(label.lines) for label in plan.labels if label.kind == "section"]
    assert sorted(names) == ["INTRO 0:00", "OUTRO 0:04", "VERSE 1 0:02"]
    assert_clean(plan)


@pytest.mark.parametrize("count", [1, 3, 40])
def test_the_strip_builds_clean_for_one_three_and_forty_sections(count):
    data = even(count)
    plan = strip_plan(data)
    assert_clean(plan)
    picture = timeline_strip(data, "SONG")
    assert picture.shape == (plan.height, plan.width, 3)
    assert plan.width <= 1600


def test_the_last_time_on_the_axis_stays_inside_the_picture():
    plan = strip_plan(structure([("Song", "sung", 0.0, 300.0)]))
    times = [label for label in plan.labels if label.kind == "time"]
    assert " ".join(times[-1].lines) == "5:00"
    assert_clean(plan)


def test_the_clustered_strip_draws():
    picture = timeline_strip(structure(CLUSTERED, CLUSTERED_GAPS), "THE SONG")
    assert picture.shape[1] == STRIP_SIZE[0]
