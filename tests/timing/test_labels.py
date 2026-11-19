import json

from atomic_flix.timing.labels import Label, load_labels, match_labels
from atomic_flix.timing.lyric import parse_lyric


def _labels(spec):
    return [Label(text, a, b, 0.9) for text, a, b in spec]


def test_load_labels_reads_the_spec_format(tmp_path):
    path = tmp_path / "word-labels.json"
    path.write_text(json.dumps({"model": "large-v3", "words": [
        {"text": "float", "from": 188.1, "to": 188.4, "conf": 0.91}]}), encoding="utf-8")
    labels = load_labels(path)
    assert labels == [Label("float", 188.1, 188.4, 0.91)]


def test_lines_match_labels_in_order_with_skips():
    lines = parse_lyric("one two three four\nfive six seven eight\n")
    labels = _labels([("uh", 0.5, 0.6), ("one", 1.0, 1.2), ("two", 1.2, 1.4), ("three", 1.4, 1.6),
                      ("four", 1.6, 1.9), ("five", 3.0, 3.2), ("sticks", 3.2, 3.4), ("seven", 3.4, 3.6),
                      ("eight", 3.6, 3.9)])
    found = match_labels(lines, labels)
    assert [labels[i].text for i in found["v01"]] == ["one", "two", "three", "four"]
    assert [labels[i].text for i in found["v02"]] == ["five", "seven", "eight"]


def test_first_four_letters_count_as_a_match():
    lines = parse_lyric("fluorescent dreaming\n")
    labels = _labels([("fluoro", 1.0, 1.3), ("dreams", 1.3, 1.8)])
    assert len(match_labels(lines, labels)["v01"]) == 2


def test_repeated_chorus_lines_take_their_own_labels():
    lines = parse_lyric("ride the tub\nsomething else here\nride the tub\n")
    labels = _labels([("ride", 1, 1.2), ("the", 1.2, 1.3), ("tub", 1.3, 1.6),
                      ("something", 3, 3.3), ("else", 3.3, 3.5), ("here", 3.5, 3.8),
                      ("ride", 6, 6.2), ("the", 6.2, 6.3), ("tub", 6.3, 6.6)])
    found = match_labels(lines, labels)
    assert [labels[i].start for i in found["v01"]] == [1, 1.2, 1.3]
    assert [labels[i].start for i in found["v03"]] == [6, 6.2, 6.3]


def test_choir_and_wordless_lines_take_no_labels():
    lines = parse_lyric("(ride the tub)\naa-aah-aah\nride the tub\n")
    labels = _labels([("ride", 1, 1.2), ("the", 1.2, 1.3), ("tub", 1.3, 1.6)])
    found = match_labels(lines, labels)
    assert found["v01"] == [] and found["v02"] == []
    assert len(found["v03"]) == 3
