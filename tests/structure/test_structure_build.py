"""The song's structure from synthetic stems: sung and instrumental sections, story gaps, pacing and the page."""

from __future__ import annotations

import numpy as np
import pytest

from atomic_flix.structure import StructureInputs, TimedLine, build_structure, structure_page, timed_lines

RATE = 8000


def track(total_s: float, spans, amp: float = 0.3, freq: float = 220.0) -> np.ndarray:
    """Silence with a sine in each (start, end) span."""
    t = np.arange(int(round(total_s * RATE))) / RATE
    out = np.zeros_like(t)
    for start, end in spans:
        inside = (t >= start) & (t < end)
        out[inside] = amp * np.sin(2 * np.pi * freq * t[inside])
    return out


def band(total_s: float, gain=lambda t: 0.2 + 0.0 * t) -> np.ndarray:
    t = np.arange(int(round(total_s * RATE))) / RATE
    return gain(t) * np.sin(2 * np.pi * 110.0 * t)


def inputs(lead, rest=None, lines=(), ones=None, swells=(), notes=()) -> StructureInputs:
    return StructureInputs(lead=lead, lead_rate=RATE, rest=band(len(lead) / RATE) if rest is None else rest,
                           rest_rate=RATE, rest_name="band", lines=tuple(lines), ones=ones, ruling=None,
                           swells=tuple(swells), notes=tuple(notes))


def line(key, label, block, start, end, flagged=False) -> TimedLine:
    return TimedLine(key, label, block, start, end, flagged)


SPANS = ((4.0, 10.0), (11.0, 16.0), (28.0, 40.0), (50.0, 58.0))
LINES = (line("v01", "Verse 1", 0, 4.0, 7.0), line("v02", "Verse 1", 0, 7.2, 10.0),
         line("v03", "Chorus", 1, 11.0, 16.0), line("v04", "Verse 2", 2, 28.0, 33.0),
         line("v05", "Chorus", 3, 34.0, 40.0), line("v06", "Chorus", 4, 50.0, 58.0, flagged=True))


def kinds(data):
    return [(s["label"], s["kind"]) for s in data["sections"]]


def test_sections_follow_the_lyric_markers_and_the_breaks_between_them():
    data = build_structure(inputs(track(62.0, SPANS), lines=LINES))
    assert kinds(data) == [("Instrumental 1", "instrumental"), ("Verse 1", "sung"), ("Chorus", "sung"),
                           ("Instrumental 2", "instrumental"), ("Verse 2", "sung"), ("Chorus", "sung"),
                           ("Instrumental 3", "instrumental"), ("Chorus", "sung"), ("Instrumental 4", "instrumental")]
    sections = data["sections"]
    assert sections[0]["start"] == 0.0 and sections[-1]["end"] == pytest.approx(62.0, abs=0.01)
    assert all(a["end"] == b["start"] for a, b in zip(sections, sections[1:]))
    assert sections[3]["start"] == pytest.approx(16.0, abs=0.1) and sections[3]["end"] == pytest.approx(28.0, abs=0.1)
    assert [s["id"] for s in sections] == [f"s{n:02d}" for n in range(1, 10)]
    assert data["vocal_regions"][0] == pytest.approx([4.0, 16.0], abs=0.1)


def test_story_gaps_are_the_instrumental_stretches_over_the_threshold_longest_first():
    data = build_structure(inputs(track(62.0, SPANS), lines=LINES))
    gaps = data["pacing"]["story_gaps"]
    assert [round(g["duration_s"]) for g in gaps] == [12, 10]
    assert gaps[0]["after"] == "Chorus" and gaps[0]["before"] == "Verse 2" and gaps[0]["rank"] == 1
    assert data["pacing"]["story_gap_threshold_s"] == 8.0
    fewer = build_structure(inputs(track(62.0, SPANS), lines=LINES), gap_s=11.0)
    assert len(fewer["pacing"]["story_gaps"]) == 1


def test_a_song_with_no_long_break_has_no_story_gaps_and_no_error():
    data = build_structure(inputs(track(20.0, ((1.0, 19.5),)), lines=()))
    assert data["pacing"]["story_gaps"] == []
    assert "no instrumental break of 8 s or more" in structure_page(data, "Tiny")


def test_pacing_counts_sung_and_instrumental_time_and_the_longest_sung_stretch():
    data = build_structure(inputs(track(62.0, SPANS), lines=LINES))
    pacing = data["pacing"]
    assert pacing["total_s"] == pytest.approx(62.0, abs=0.01)
    assert pacing["sung_s"] + pacing["instrumental_s"] == pytest.approx(62.0, abs=0.01)
    assert pacing["sung_s"] == pytest.approx(32.0, abs=0.3)
    assert pacing["voice_on_share"] == pytest.approx(31.0 / 62.0, abs=0.02)
    assert pacing["first_voice_s"] == pytest.approx(4.0, abs=0.05)
    assert pacing["longest_sung"]["duration_s"] == pytest.approx(12.0, abs=0.2)
    assert pacing["longest_sung"]["labels"] == ["Verse 1", "Chorus"]


def test_the_chorus_repeats_are_counted_and_compared_by_loudness():
    rest = band(62.0, gain=lambda t: np.where(t > 45.0, 0.4, 0.1))
    data = build_structure(inputs(track(62.0, SPANS), rest=rest, lines=LINES))
    chorus = next(r for r in data["pacing"]["repeats"] if r["label"] == "Chorus")
    assert len(chorus["times"]) == 3
    assert chorus["times"][0]["vs_first_db"] == 0.0
    assert chorus["times"][1]["vs_first_db"] == pytest.approx(0.0, abs=1.0)
    assert chorus["times"][2]["vs_first_db"] == pytest.approx(12.0, abs=1.0)
    assert chorus["times"][2]["differs"] == "louder"


def test_each_section_carries_voice_share_band_level_trend_and_swells():
    rest = band(62.0, gain=lambda t: 0.05 + 0.3 * np.clip((t - 16.0) / 12.0, 0, 1))
    swells = ({"t": 20.0, "punch": 0.4}, {"t": 51.0, "punch": 0.3})
    data = build_structure(inputs(track(62.0, SPANS), rest=rest, lines=LINES, swells=swells))
    gap = data["sections"][3]
    assert gap["voice_share"] == 0.0 and gap["trend"] == "rises" and gap["change_db"] > 2.0
    assert [s["t"] for s in gap["swells"]] == [20.0]
    verse = data["sections"][1]
    assert verse["voice_share"] > 0.8 and 0.0 < verse["rest_level"] <= 1.0
    assert data["sections"][7]["uncertain_lines"] == ["v06"]


def test_bars_snap_the_edges_and_say_by_how_much():
    ones = tuple(0.3 + 2.0 * k for k in range(31))
    data = build_structure(inputs(track(62.0, SPANS), lines=LINES, ones=ones))
    gap = data["sections"][3]
    assert gap["start"] == pytest.approx(16.3, abs=0.01) and gap["measured"][0] == pytest.approx(16.0, abs=0.1)
    assert gap["snap_s"][0] == pytest.approx(0.3, abs=0.1)
    assert gap["bars"] == pytest.approx(6.0, abs=0.1)
    assert data["sections"][0]["start"] == 0.0


def test_without_a_pulse_nothing_is_snapped_and_the_page_says_so():
    data = build_structure(inputs(track(62.0, SPANS), lines=LINES))
    assert all(s["bars"] is None and s["snap_s"] == [0.0, 0.0] for s in data["sections"])
    assert "not snapped to the bar" in structure_page(data, "Tiny")


def test_singing_the_lyric_cannot_place_is_an_unlabelled_vocal():
    spans = SPANS + ((44.0, 46.5),)
    data = build_structure(inputs(track(62.0, sorted(spans)), lines=LINES))
    assert ("unlabelled vocal", "sung") in kinds(data)
    page = structure_page(data, "Tiny")
    assert "unlabelled vocal" in page and "the lyric has no line" in page


def test_a_lyric_without_section_markers_numbers_the_sung_stretches():
    bare = tuple(line(x.id, "", 0, x.start, x.end) for x in LINES)
    data = build_structure(inputs(track(62.0, SPANS), lines=bare))
    assert [s["label"] for s in data["sections"] if s["kind"] != "instrumental"] == ["Vocal 1", "Vocal 2", "Vocal 3"]
    assert any("no [Section] markers" in note for note in data["notes"])


def test_a_silent_lead_stem_gives_one_instrumental_section_and_says_why():
    data = build_structure(inputs(np.zeros(20 * RATE), lines=LINES))
    assert kinds(data) == [("Instrumental 1", "instrumental")]
    assert data["pacing"]["first_voice_s"] is None
    assert any("lead stem is silent" in note for note in data["notes"])
    structure_page(data, "Tiny")


def test_stems_of_different_length_are_reported():
    lead = track(62.0, SPANS)
    data = build_structure(inputs(lead, rest=band(60.0), lines=LINES))
    assert data["pacing"]["total_s"] == pytest.approx(62.0, abs=0.01)
    assert any("62.00 s" in note and "60.00 s" in note for note in data["notes"])


def test_a_long_pause_inside_a_section_makes_it_mixed():
    spans = ((4.0, 8.0), (10.6, 14.0))
    lines = (line("v01", "Verse", 0, 4.0, 8.0), line("v02", "Verse", 0, 10.6, 14.0))
    data = build_structure(inputs(track(20.0, spans), lines=lines))
    verse = next(s for s in data["sections"] if s["label"] == "Verse")
    assert verse["kind"] == "mixed"


def test_the_page_opens_with_a_reading_from_the_numbers_and_states_its_limits():
    data = build_structure(inputs(track(62.0, SPANS), lines=LINES))
    page = structure_page(data, "Tiny")
    assert page.startswith("# Tiny: the song's structure")
    reading = page.split("## Sections")[0]
    assert "1:02 long" in reading and "two instrumental breaks of 8 s or more, the longest 12 s at 0:16" in reading
    assert "not from listening" in page and "gate 2" in page
    assert "| s02 | Verse 1 | sung |" in page
    assert chr(0x2014) not in page


def test_timed_lines_take_the_section_labels_from_the_lyric_and_refuse_another_lyric():
    lyric = "[Verse 1]\nLate night\nNeon ghosts\n[Chorus]\nThey call me\n[Verse 2]\nSteel hands\n[Chorus]\nThey call me\n"
    voice = {"lines": [{"id": "v01", "part": "lead", "text": "Late night", "start": 1.0, "end": 2.0, "flags": []},
                       {"id": "v02", "part": "lead", "text": "Neon ghosts", "start": None, "end": None,
                        "flags": ["no time"]},
                       {"id": "v03", "part": "lead", "text": "They call me", "start": 3.0, "end": 4.0,
                        "flags": ["uncertain (0.2): could start at 9.00 s"]},
                       {"id": "v04", "part": "lead", "text": "Steel hands", "start": 5.0, "end": 6.0, "flags": []},
                       {"id": "v05", "part": "lead", "text": "They call me", "start": 7.0, "end": 8.0, "flags": []}]}
    lines, notes = timed_lines(lyric, voice)
    assert [(x.id, x.label, x.block, x.flagged) for x in lines] == [
        ("v01", "Verse 1", 0, False), ("v03", "Chorus", 1, True), ("v04", "Verse 2", 2, False),
        ("v05", "Chorus", 3, False)]
    assert any("v02" in note and "no time" in note for note in notes)
    assert any("1 of 5" in note for note in notes)
    other = {"lines": [{**voice["lines"][0], "text": "Something else"}]}
    lines, notes = timed_lines(lyric, other)
    assert lines == () and any("another lyric" in note for note in notes)
