"""Character sheets (CHR1 to CHR4): every character has one tall portrait picture per view, a plain studio backdrop (a
coarse screen on the picture), the figure filling the picture; and a still seen from an angle takes that view."""

from __future__ import annotations

import json

from atomic_flix.cast import cast_of, missing_views, required_views, views_of
from atomic_flix.lint import load_book
from atomic_flix.lint.book import book_from_case
from atomic_flix.lint.registry import check_rule
from sheet_samples import view_path, write_sheet

NAMES = ("front", "three_quarter", "profile", "back", "body_front", "body_three_quarter", "body_back")
VIEWS = {name: f"refs/n-{name.replace('_', '-')}.png" for name in NAMES}


def _star(views=None) -> dict:
    return {"star": {"name": "Nova", **({"views": views} if views is not None else {})}}


# the cast -------------------------------------------------------------------------------------------------------------

def test_the_views_are_the_heads_from_every_side_and_the_full_length_views():
    assert required_views() == NAMES


def test_the_cast_is_the_star_and_every_registered_character():
    cast = cast_of({"star": {"name": "Nova", "who": "a singer"}, "characters": {"Ada": {"who": "an android"},
                                                                                "Nova": {"views": VIEWS}}})
    assert list(cast) == ["Nova", "Ada"]
    assert cast["Nova"]["who"] == "a singer" and cast["Nova"]["views"] == VIEWS


def test_a_lone_identity_picture_counts_as_the_front_view_only():
    person = {"identity": "refs/front.png"}
    assert views_of(person) == {"front": "refs/front.png"}
    assert missing_views(person) == list(NAMES[1:])


def test_non_objects_in_film_json_are_ignored_not_a_crash():
    film = {"star": {"name": "Nova", "views": ["refs/a.png"]}, "characters": {"Ada": "refs/h.png", "Mira": None}}
    assert check_rule("CHR1", book_from_case({"film": film}))[0].message.startswith("Nova's sheet has no")
    assert set(cast_of(film)) == {"Nova", "Ada", "Mira"}
    assert cast_of({"characters": ["Ada"]}) == {}


def test_a_star_and_a_character_of_one_name_share_their_views():
    film = {"star": {"name": "Nova", "views": {"front": "a.png"}}, "characters": {"Nova": {"views": {"back": "b.png"}}}}
    assert views_of(cast_of(film)["Nova"]) == {"front": "a.png", "back": "b.png"}


# CHR1 ---------------------------------------------------------------------------------------------------------------

def test_a_sheet_with_one_picture_blocks_and_names_the_missing_views():
    (finding,) = check_rule("CHR1", book_from_case({"film": _star({"front": VIEWS["front"]})}))
    assert finding.level == "block"
    assert "three_quarter, profile, back, body_front, body_three_quarter, body_back" in finding.message


def test_a_character_with_no_sheet_at_all_blocks():
    (finding,) = check_rule("CHR1", book_from_case({"film": _star()}))
    assert "front, three_quarter, profile, back, body_front" in finding.message


def test_a_view_whose_file_is_not_there_blocks():
    book = book_from_case({"film": _star(VIEWS), "files": [p for v, p in VIEWS.items() if v != "body_back"]})
    (finding,) = check_rule("CHR1", book)
    assert "body_back view refs/n-body-back.png is not in the film folder" in finding.message


def test_a_full_sheet_passes():
    assert not check_rule("CHR1", book_from_case({"film": _star(VIEWS), "files": list(VIEWS.values())}))


def test_every_registered_character_needs_a_sheet():
    film = {**_star(VIEWS), "characters": {"Ada": {"identity": "refs/h.png"}}}
    messages = [f.message for f in check_rule("CHR1", book_from_case({"film": film}))]
    assert len(messages) == 1 and messages[0].startswith("Ada's sheet has no three_quarter")


# CHR2 and CHR4 ---------------------------------------------------------------------------------------------------------

def test_a_view_with_an_environment_blocks_and_says_how_smooth_the_band_was():
    plain = {path: 0.99 for path in VIEWS.values()} | {VIEWS["back"]: 0.4}
    (finding,) = check_rule("CHR2", book_from_case({"film": _star(VIEWS), "plain": plain}))
    assert "back view" in finding.message and "40%" in finding.message


def test_a_view_that_cannot_be_read_blocks_and_says_how_to_save_it():
    plain = {VIEWS["front"]: "front.png: unsupported PNG (depth 8, colour type 3, interlace 0)"}
    (finding,) = check_rule("CHR2", book_from_case({"film": _star(VIEWS), "plain": plain}))
    assert "cannot be checked" in finding.message and "colour type 3" in finding.message
    assert "8-bit RGB PNG" in finding.message


def test_a_figure_small_in_a_wide_frame_blocks_chr4_not_chr2():
    plain = {VIEWS["body_front"]: {"ring": 0.99, "aspect": 0.55, "figure": 0.98}}
    book = book_from_case({"film": _star(VIEWS), "plain": plain})
    (finding,) = check_rule("CHR4", book)
    assert finding.level == "block" and "body_front view" in finding.message and "tall portrait" in finding.message
    assert not check_rule("CHR2", book)


def test_a_figure_that_does_not_fill_the_height_blocks():
    plain = {VIEWS["profile"]: {"ring": 0.99, "aspect": 1.5, "figure": 0.5}}
    (finding,) = check_rule("CHR4", book_from_case({"film": _star(VIEWS), "plain": plain}))
    assert "covers only 50%" in finding.message


def test_a_tall_view_the_figure_fills_passes_both():
    plain = {path: {"ring": 0.95, "aspect": 1.5, "figure": 0.95} for path in VIEWS.values()}
    book = book_from_case({"film": _star(VIEWS), "plain": plain})
    assert not check_rule("CHR2", book) and not check_rule("CHR4", book)


# CHR3 ---------------------------------------------------------------------------------------------------------------

def _seen(view, refs, **film):
    return book_from_case({"kind": "cutaway", "shot": {"view": view, "figures": True}, "film": film or _star(VIEWS),
                           "still": {"figures": ["Nova"], "refs": refs}})


def test_a_back_view_that_carries_the_front_face_blocks():
    (finding,) = check_rule("CHR3", _seen("back", [VIEWS["back"], VIEWS["front"]]))
    assert "front view" in finding.message and "face" in finding.message


def test_a_still_seen_from_an_angle_needs_that_angles_view():
    (finding,) = check_rule("CHR3", _seen("profile", [VIEWS["front"]]))
    assert "lacks the profile view" in finding.message


def test_a_still_seen_from_the_back_with_the_back_view_only_passes():
    assert not check_rule("CHR3", _seen("back", [VIEWS["back"]]))


def test_a_full_length_shot_names_its_body_view():
    assert not check_rule("CHR3", _seen("body_back", [VIEWS["body_back"]]))
    assert check_rule("CHR3", _seen("body_back", [VIEWS["back"]]))


def test_a_view_that_is_not_one_of_the_sheets_is_refused_by_name():
    (finding,) = check_rule("CHR3", _seen("above", [VIEWS["front"]]))
    assert "'above' is not one of front, three_quarter, profile, back, body_front" in finding.message


def test_a_view_the_sheet_does_not_have_blocks():
    (finding,) = check_rule("CHR3", _seen("back", [], star={"name": "Nova", "views": {"front": VIEWS["front"]}}))
    assert "Nova has no back view" in finding.message


def test_a_back_view_shot_can_pass_the_identity_rule_and_the_sheet_rule_together():
    case = {"kind": "cutaway", "shot": {"view": "back", "figures": True}, "film": _star(VIEWS),
            "still": {"figures": ["Nova"], "refs": [VIEWS["back"]]}}
    book = book_from_case(case)
    assert not check_rule("L022", book) and not check_rule("CHR3", book) and not check_rule("L013", book)
    wrong = book_from_case({**case, "still": {"figures": ["Nova"], "refs": [VIEWS["front"]]}})
    assert check_rule("L022", wrong) and check_rule("CHR3", wrong)


def test_a_front_shot_still_asks_for_the_identity_reference():
    case = {"kind": "cutaway", "shot": {"figures": True}, "film": _star(VIEWS),
            "still": {"figures": ["Nova"], "refs": []}}
    assert check_rule("L022", book_from_case(case))


# a real folder -----------------------------------------------------------------------------------------------------------

def _folder(tmp_path, **kind):
    views = write_sheet(tmp_path, "Nova", **kind)
    (tmp_path / "film.json").write_text(json.dumps({"name": "T", "star": {"name": "Nova", "views": views}}),
                                        encoding="utf-8")
    (tmp_path / "shots.txt").write_text("N01 cutaway\n  beat: dust drifts\n", encoding="utf-8")
    return load_book(tmp_path)


def test_a_loaded_film_measures_its_sheet_pictures(tmp_path):
    book = _folder(tmp_path)
    assert set(book.plain) == {view_path("Nova", v) for v in NAMES}
    assert all(measured.ok() for measured in book.plain.values())
    assert not any(check_rule(rule, book) for rule in ("CHR1", "CHR2", "CHR4"))


def test_a_loaded_film_with_busy_pictures_blocks_chr2(tmp_path):
    assert len(check_rule("CHR2", _folder(tmp_path, busy=True))) == 7


def test_a_loaded_film_with_small_figures_in_wide_pictures_blocks_chr4(tmp_path):
    book = _folder(tmp_path, wide=True)
    assert len(check_rule("CHR4", book)) == 7 and not check_rule("CHR2", book)


def test_a_corrupt_picture_blocks_with_a_message_not_a_traceback(tmp_path):
    _folder(tmp_path)
    broken = tmp_path / view_path("Nova", "back")
    broken.write_bytes(broken.read_bytes()[:60])                    # a half-copied file
    (finding,) = [f for f in check_rule("CHR2", load_book(tmp_path)) if "back view" in f.message]
    assert "cannot be checked" in finding.message
