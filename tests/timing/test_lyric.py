from atomic_flix.timing.lyric import is_wordless, normalise_words, parse_lyric, syllables

SONG = """\
[Verse 1]
She slipped out the back of a fluorescent dream,
Badge-holding ghosts and a camera gleam. (gleam)

[Chorus]
Do you wanna ride in the magical tub
(magical tub)
aa-h-aaaaa-aha-aaaaaah

[Chorus]
Do you wanna ride in the magical tub
"""


def test_sections_ids_and_parts():
    lines = parse_lyric(SONG)
    assert [ln.id for ln in lines] == ["v01", "v02", "v03", "v04", "v05", "v06"]
    assert [ln.verse_part for ln in lines] == ["Verse 1", "Verse 1", "Chorus", "Chorus", "Chorus", "Chorus"]
    assert [ln.part for ln in lines] == ["lead", "lead", "lead", "choir", "lead", "lead"]


def test_backing_words_in_parentheses_leave_the_lead_line():
    line = parse_lyric(SONG)[1]
    assert line.text == "Badge-holding ghosts and a camera gleam. (gleam)"
    assert line.words == ("badge", "holding", "ghosts", "and", "a", "camera", "gleam")


def test_a_whole_line_in_parentheses_is_a_choir_line():
    line = parse_lyric(SONG)[3]
    assert line.part == "choir"
    assert line.words == ("magical", "tub")


def test_repeats_written_out_are_separate_lines():
    lines = parse_lyric(SONG)
    assert lines[2].words == lines[5].words
    assert lines[2].id != lines[5].id


def test_wordless_lines_are_recognised():
    lines = parse_lyric(SONG)
    assert lines[4].wordless
    assert not lines[0].wordless
    assert is_wordless("ooh ooh la la")
    assert not is_wordless("oh come on")


def test_normalise_lowercases_strips_punctuation_and_spells_digits():
    assert normalise_words("Don't STOP, 2 times!") == ("dont", "stop", "two", "times")
    assert normalise_words("busted-up") == ("busted", "up")


def test_syllable_counts_are_close_enough_for_timing():
    assert syllables("dream") == 1
    assert syllables("camera") == 3
    assert syllables("fluorescent") >= 3
    assert syllables("ride") == 1
    assert syllables("magical") == 3


def test_blank_lines_and_comments_are_ignored():
    lines = parse_lyric("# a note\n\n[Intro]\n\nhello there\n")
    assert len(lines) == 1
    assert lines[0].verse_part == "Intro"
