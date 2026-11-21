"""Prompts for a character's reference sheet: one view per picture, the figure alone on a plain background."""

from __future__ import annotations

import re

import pytest

from atomic_flix.cast import required_views
from atomic_flix.plan.vocab import find
from atomic_flix.prompts.sheets import (picture_path, sheet_prompt, sheet_requests, slug, unique_slugs,
                                       write_sheet_prompts)

FILM = {"star": {"name": "Nova", "who": "a singer with short silver hair"},
        "wardrobe": {"main": "wearing a white jacket"}}


VIEWS = ["front", "three_quarter", "profile", "back", "body_front", "body_three_quarter", "body_back"]


@pytest.mark.parametrize("view", VIEWS)
def test_every_view_prompt_isolates_the_figure(view):
    text = sheet_prompt("Nova", "a singer with short silver hair", view, "wearing a white jacket")
    assert "plain neutral studio backdrop" in text and "no environment" in text
    assert "no scenery" in text and "no other people" in text and "One figure only" in text
    assert "A tall portrait picture" in text and "No text, no letters, no logos." in text
    assert not find("grain", text)


def test_the_back_view_faces_away_and_the_profile_is_a_side_view():
    assert "facing away from the camera so that no face shows" in sheet_prompt("Nova", "a singer", "back")
    assert "full profile" in sheet_prompt("Nova", "a singer", "profile")


def test_the_star_wears_the_films_first_outfit_in_every_view():
    rows = sheet_requests(FILM)
    assert [row["view"] for row in rows] == list(required_views())
    assert all("Nova is wearing a white jacket." in row["prompt"] for row in rows)


def test_a_view_the_film_already_names_is_not_asked_for_again():
    film = {"star": {**FILM["star"], "views": {"front": "refs/nova-front.png"}}}
    assert [row["view"] for row in sheet_requests(film)] == VIEWS[1:]


def test_a_character_with_no_who_cannot_be_drawn_and_is_named():
    rows = sheet_requests({"characters": {"Ada": {}}})
    assert rows[0]["problems"] == ["Ada has no `who` in film.json: one sentence from canon saying who they are"]


def test_the_pictures_go_under_refs_with_safe_names():
    assert picture_path(slug("Ada Vale"), "three_quarter") == "refs/ada-vale-three-quarter.png"
    assert re.fullmatch(r"[a-z0-9-]+", slug("Dr. O'Neil #2"))


def test_the_prompt_files_are_written_under_plan_refs(tmp_path):
    written = [path for _, path, _ in write_sheet_prompts(FILM, tmp_path)]
    assert [path.name for path in written] == [f"nova-{view.replace('_', '-')}.prompt.txt" for view in VIEWS]
    assert all(path.parent == tmp_path / "plan" / "refs" for path in written)


def test_a_character_with_no_who_stops_the_writing(tmp_path):
    with pytest.raises(ValueError, match="Ada has no `who`"):
        write_sheet_prompts({"characters": {"Ada": {}}}, tmp_path)
    assert not (tmp_path / "plan").exists()


def test_two_names_that_make_one_slug_get_different_files():
    stems = unique_slugs(["Mira K", "Mira-K", "Хікару", "Ян"])
    assert len(set(stems.values())) == 4 and stems["Mira K"] == "mira-k" and stems["Mira-K"] == "mira-k-2"


def test_a_prompt_file_that_is_there_is_kept_unless_forced(tmp_path):
    first = write_sheet_prompts(FILM, tmp_path)
    mine = first[0][1]
    mine.write_text("my own wording\n", encoding="utf-8")
    again = write_sheet_prompts(FILM, tmp_path)
    assert not again[0][2] and mine.read_text(encoding="utf-8") == "my own wording\n"
    forced = write_sheet_prompts(FILM, tmp_path, overwrite=True)
    assert forced[0][2] and "character reference picture of Nova" in mine.read_text(encoding="utf-8")


def test_a_head_view_fills_a_three_to_four_picture_and_a_full_length_view_a_two_to_three_one():
    assert "head and shoulders fill the picture" in sheet_prompt("Nova", "a singer", "front")
    assert "head to feet fills the height" in sheet_prompt("Nova", "a singer", "body_front")


def test_the_requests_carry_a_tall_size_for_each_kind_of_view():
    sizes = {row["view"]: row["size"] for row in sheet_requests(FILM)}
    assert sizes["front"] == [1152, 1536] and sizes["body_back"] == [1024, 1536]


def test_the_films_own_style_is_said_once():
    prompt = sheet_prompt("Nova", "a singer", "front", style="1990s cel anime")
    assert prompt.count("1990s cel anime") == 1 and "Drawn in 1990s cel anime." in prompt
