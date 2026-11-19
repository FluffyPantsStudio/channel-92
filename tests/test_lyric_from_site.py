"""Taking a lyric out of the site's catalog file."""

import pytest

from tool_loader import load_tool

CATALOG = '''const songs: Song[] = [
  {
    slug: "first-song",
    title: "First",
    lyrics: "Line one, \\"quoted\\"\\nLine two\\n\\nLine three",
    year: 1950,
  },
  {
    slug: "second-song",
    lyrics: "Other words",
  }
];
'''


def test_the_lyric_of_one_slug_is_decoded():
    tool = load_tool("lyric_from_site")
    assert tool.lyric_of(CATALOG, "first-song") == 'Line one, "quoted"\nLine two\n\nLine three'
    assert tool.lyric_of(CATALOG, "second-song") == "Other words"


def test_an_unknown_slug_is_refused():
    with pytest.raises(ValueError, match="no song"):
        load_tool("lyric_from_site").lyric_of(CATALOG, "missing")


def test_the_file_says_it_is_not_checked_against_the_take(tmp_path):
    tool = load_tool("lyric_from_site")
    text = tool.lyric_file("Line one\nLine two", "first-song")
    assert text.startswith("# first-song: the lyric as published")
    assert text.endswith("Line two\n")
