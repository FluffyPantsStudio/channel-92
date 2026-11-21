"""A character's sheet pictures are inputs of the eval: a changed or missing picture makes a saved report stale."""

from __future__ import annotations

import json

from atomic_flix.eval.inputs import MISSING, group_files, input_table

VIEWS = {"front": "refs/nova-front.png", "back": "refs/nova-back.png"}


def _film(tmp_path, views=VIEWS):
    (tmp_path / "film.json").write_text(json.dumps({"star": {"name": "Nova", "views": views}}), encoding="utf-8")
    (tmp_path / "refs").mkdir(exist_ok=True)
    (tmp_path / "refs" / "nova-front.png").write_bytes(b"front")


def test_the_sheet_pictures_are_inputs_of_lint_and_scene_checks(tmp_path):
    _film(tmp_path)
    for group in ("lint", "scene"):
        assert {"refs/nova-front.png", "refs/nova-back.png"} <= set(group_files(tmp_path, group))


def test_a_changed_or_missing_sheet_picture_changes_the_table(tmp_path):
    _film(tmp_path)
    before = input_table(tmp_path)
    assert before["refs/nova-back.png"] == MISSING
    (tmp_path / "refs" / "nova-back.png").write_bytes(b"back")
    assert input_table(tmp_path) != before
    (tmp_path / "refs" / "nova-front.png").write_bytes(b"front, redrawn")
    assert input_table(tmp_path)["refs/nova-front.png"] != before["refs/nova-front.png"]


def test_a_view_outside_the_film_folder_is_refused_never_read(tmp_path):
    _film(tmp_path, {"front": "../elsewhere.png", "back": "/etc/passwd"})
    refused = [name for name in group_files(tmp_path, "lint") if name.startswith("refused:")]
    assert len(refused) == 2
