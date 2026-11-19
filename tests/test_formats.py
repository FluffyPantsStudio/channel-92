"""Format tags: every JSON file the kit writes says what it is and which version."""

from __future__ import annotations

import json

import pytest

from atomic_flix.formats import VERSIONS, FormatError, check_format, stamped, tag
from atomic_flix.project import create_project


def test_a_tag_names_the_kind_and_its_version():
    assert tag("pulse") == "atomic-flix/pulse@1"
    assert all(version >= 1 for version in VERSIONS.values())


def test_stamped_puts_the_tag_first_and_replaces_an_old_one():
    data = stamped("fit", {"format": "something else", "how": "slice"})
    assert list(data) == ["format", "how"] and data["format"] == "atomic-flix/fit@1"


def test_check_format_accepts_its_own_tag_or_none_and_refuses_another():
    check_format("edit", {"format": tag("edit")})
    check_format("edit", {})
    with pytest.raises(FormatError, match="atomic-flix/edit@1"):
        check_format("edit", {"format": tag("audit")})


def test_a_new_film_writes_tagged_files(tmp_path):
    folder = create_project(tmp_path, "tiny", "Tiny", created="2026-11-19T10:00:00+00:00")
    assert json.loads(folder.film.read_text(encoding="utf-8"))["format"] == tag("film")
    assert json.loads(folder.standing.read_text(encoding="utf-8"))["format"] == tag("standing")
