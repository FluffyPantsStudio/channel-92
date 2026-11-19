import json
from pathlib import Path

import pytest

from similarity_samples import write_tree


@pytest.fixture
def sim(tool):
    return tool("similarity")


@pytest.fixture
def old(tmp_path):
    return write_tree(tmp_path / "old", "old")


def test_exact_copy_fails_on_every_check(sim, old, tmp_path):
    new = write_tree(tmp_path / "new", "copy")
    report = sim.compare(old, new)
    assert report["pass"] is False
    assert report["code"]["literal_runs"], "an exact copy must show literal runs"
    assert report["prose"]["sentences"], "copied docstrings must be found"
    assert report["prose"]["shingles"]
    assert report["names"]["share"] > 0.5
    assert report["keys"]["shared"]
    assert sim.main([str(old), str(new)]) == 1


def test_rename_only_copy_is_caught_by_shape(sim, old, tmp_path):
    new = write_tree(tmp_path / "new", "renamed")
    report = sim.compare(old, new)
    assert report["pass"] is False
    assert report["code"]["literal_runs"] == []
    assert report["code"]["shape_runs"], "renamed copy must show shape runs"
    longest = max(run["length"] for run in report["code"]["shape_runs"])
    assert longest > 12
    assert report["names"]["share"] < 0.05  # the renames hide the names...
    assert report["prose"]["sentences"]  # ...but not the comments and docstrings


def test_unrelated_tree_passes(sim, old, tmp_path, capsys):
    new = write_tree(tmp_path / "new", "unrelated")
    report = sim.compare(old, new)
    assert report["pass"] is True, report
    assert report["code"]["literal_runs"] == [] and report["code"]["shape_runs"] == []
    assert report["prose"]["sentences"] == [] and report["prose"]["shingles"] == []
    assert report["names"]["shared"] == []
    assert sim.main([str(old), str(new)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_report_positions_are_on_the_new_side_only(sim, old, tmp_path, capsys):
    new = write_tree(tmp_path / "new", "copy")
    sim.main([str(old), str(new)])
    out = capsys.readouterr().out
    assert "pantry/core.py:" in out
    assert str(old) not in out.split("\n", 1)[1]  # old path only in the header line


def test_stoplist_drops_builtins_stdlib_and_conventional_names(sim, tmp_path):
    src = "import os\n\ndef main(argv=None):\n    path = os.getcwd()\n    len = 3\n    json = 1\n    return path\n"
    a = tmp_path / "a"
    b = tmp_path / "b"
    for root in (a, b):
        root.mkdir()
        (root / "m.py").write_text(src, encoding="utf-8")
    names = sim.compare(a, b)["names"]
    assert names["shared"] == []


def test_identifiers_match_across_case_styles(sim, tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "m.py").write_text("def gather_moonbeams():\n    return 1\n", encoding="utf-8")
    (b / "m.py").write_text("def gatherMoonbeams():\n    return 1\n", encoding="utf-8")
    shared = sim.compare(a, b)["names"]["shared"]
    assert [item["name"] for item in shared] == ["gatherMoonbeams"]
    assert shared[0]["where"] == "m.py:1"


def test_allow_file_exempts_names_with_reasons(sim, old, tmp_path):
    new = write_tree(tmp_path / "new", "copy")
    allow = tmp_path / "allow.txt"
    allow.write_text("shelf_label  # the spec names this key\n\n# a comment line\n", encoding="utf-8")
    report = sim.compare(old, new, allow=sim.read_allow(allow))
    assert all(item["name"] != "shelf_label" for item in report["names"]["shared"])
    assert {"name": "shelf_label", "reason": "the spec names this key"} in report["allowed"]


def test_keys_and_verbs_are_collected(sim, tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    (root / "c.py").write_text(
        "import argparse\n"
        "def main():\n"
        "    p = argparse.ArgumentParser()\n"
        "    s = p.add_subparsers()\n"
        "    s.add_parser('whistle')\n"
        "    p.add_argument('--tide-table')\n"
        "    d = {'lantern_hour': 1}\n"
        "    d['harbour_bell']\n"
        "    d.get('fog_horn')\n",
        encoding="utf-8",
    )
    (root / "x.json").write_text('{"outer_reef": {"inner_lagoon": [{"coral_depth": 2}]}}', encoding="utf-8")
    scan = sim.scan_tree(root)
    assert {"lantern_hour", "harbour_bell", "fog_horn", "outer_reef", "inner_lagoon", "coral_depth"} <= set(scan.keys)
    assert {"whistle", "--tide-table"} <= set(scan.verbs)


def test_code_line_normalisation(sim):
    src = (
        '"""Module words."""\n'
        "import os\n"
        "from sys import argv\n"
        "\n"
        "value_a = 3  # trailing note\n"
        "call_me(\n"
        "    value_a, 'text'\n"
        "\n"
        ")\n"
    )
    lines = sim.code_lines(src)
    assert [(n, lit, shape) for n, lit, shape in lines] == [
        (5, "value_a = 3", "ID = LIT"),
        (6, "call_me (", "ID ("),
        (7, "value_a , 'text'", "ID , LIT"),
    ]


def test_fstring_is_one_literal_in_shape(sim):
    lines = sim.code_lines('msg = f"{a} and {b}"\n')
    assert lines[0][2] == "ID = LIT"


def test_json_report_and_usage_errors(sim, old, tmp_path):
    new = write_tree(tmp_path / "new", "unrelated")
    out = tmp_path / "r.json"
    assert sim.main([str(old), str(new), "--json", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["pass"] is True and "thresholds" in data
    assert sim.main([str(tmp_path / "missing"), str(new)]) == 2


def test_syntax_error_file_is_reported_not_fatal(sim, tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    (a / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    scan = sim.scan_tree(a)
    assert scan.skipped == ["bad.py"]


# ---- distinctive names and keys, standard vocabulary ---------------------------------------------------------------


def _pair(tmp_path, old_src: str, new_src: str, name: str = "m.py"):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / name).write_text(old_src, encoding="utf-8")
    (b / name).write_text(new_src, encoding="utf-8")
    return a, b


def test_short_common_words_leave_the_measure_but_stay_in_the_strict_count(sim, tmp_path):
    src = ("def gather_moonbeams(best, cost):\n    after = best + cost\n    lanternwick = after\n"
           "    return lanternwick\n")
    a, b = _pair(tmp_path, src, src)
    names = sim.compare(a, b, allow={})["names"]
    assert [item["name"] for item in names["shared"]] == ["gather_moonbeams", "lanternwick"]
    assert names["strict_shared"] == 5      # best, cost, after count only in the strict number
    assert names["strict_count"] == 5 and names["new_count"] == 2


def test_a_leading_underscore_does_not_make_a_name_distinctive(sim, tmp_path):
    a, b = _pair(tmp_path, "def ask():\n    return 1\n", "def _ask():\n    return 1\n")
    names = sim.compare(a, b, allow={})["names"]
    assert names["shared"] == [] and names["strict_shared"] == 1


def test_an_inner_underscore_makes_a_short_name_distinctive(sim, tmp_path):
    a, b = _pair(tmp_path, "def go_on():\n    return 1\n", "def go_on():\n    return 1\n")
    assert [item["name"] for item in sim.compare(a, b, allow={})["names"]["shared"]] == ["go_on"]


def test_domain_standard_words_are_stopped_and_listed(sim, tmp_path):
    src = "def f(channels, content, samples):\n    return channels\n"
    a, b = _pair(tmp_path, src, src)
    names = sim.compare(a, b, allow={})["names"]
    assert names["shared"] == [] and names["strict_shared"] == 3   # f is too short even for the strict list
    assert "channels" in sim.STANDARD_WORDS and "content" in sim.STANDARD_WORDS


def test_standard_keys_and_flags_leave_the_key_measure(sim, tmp_path):
    src = ("import argparse\n"
           "def main():\n"
           "    p = argparse.ArgumentParser()\n"
           "    p.add_argument('--dry-run')\n"
           "    p.add_argument('--timeout')\n"
           "    p.add_argument('--moonbeam-count')\n"
           "    d = {'duration': 1, 'avg_frame_rate': 2, 'Content-Type': 3, 'lantern_hour': 4, 'at': 5}\n")
    a, b = _pair(tmp_path, src, src)
    keys = sim.compare(a, b, allow={})["keys"]
    assert sorted(item["name"] for item in keys["shared"]) == ["--moonbeam-count", "lantern_hour"]
    assert keys["strict_shared"] == 8


def test_standard_phrases_make_no_prose_runs_but_real_prose_still_does(sim, tmp_path):
    old = ('"""Scale with force_original_aspect_ratio=increase:flags=lanczos and check the flashes after\n'
           'WCAG 2.3.1\'s general flash threshold at minus fourteen LUFS integrated loudness."""\n')
    new = ('"""Pad by force_original_aspect_ratio=increase:flags=bicubic then compare against\n'
           'WCAG 2.3.1\'s general flash threshold, aiming for -14 LUFS integrated loudness."""\n')
    a, b = _pair(tmp_path, old, new)
    prose = sim.compare(a, b, allow={})["prose"]
    assert prose["shingles"] == [] and prose["sentences"] == []
    copied = '"""The lantern keeper rings the harbour bell twice whenever fog rolls over the reef."""\n'
    a2, b2 = _pair(tmp_path / "again", copied, copied)
    assert sim.compare(a2, b2, allow={})["prose"]["shingles"]


def test_report_prints_the_strict_number_beside_the_measure(sim, tmp_path, capsys):
    src = "def gather_moonbeams(best, cost):\n    return best + cost\n"
    a, b = _pair(tmp_path, src, src)
    sim.main([str(a), str(b)])
    out = capsys.readouterr().out
    assert "strict (every name after the stop-list): 3 of 3" in out
    assert "distinctive" in out


def test_no_allow_list_is_read_by_default(sim, old, tmp_path, capsys):
    assert not hasattr(sim, "DEFAULT_ALLOW")
    assert not (Path(sim.__file__).parent / "similarity-allow.txt").exists()
    new = write_tree(tmp_path / "new", "copy")
    sim.main([str(old), str(new)])
    out = capsys.readouterr().out
    assert "[allowed]" not in out
    assert "shelf_label" in out


def test_the_no_default_allow_flag_is_gone(sim, tmp_path):
    a, b = _pair(tmp_path, "x = 1\n", "x = 1\n")
    with pytest.raises(SystemExit):
        sim.main([str(a), str(b), "--no-default-allow"])


def test_every_stop_list_entry_is_documented(sim):
    doc = (Path(sim.__file__).resolve().parents[1] / "docs" / "shared-vocabulary.md").read_text(encoding="utf-8")
    missing = [entry for entry in sorted(sim.STANDARD_WORDS | sim.STANDARD_KEYS | set(sim.STANDARD_PHRASES))
               if entry not in doc]
    assert missing == []
