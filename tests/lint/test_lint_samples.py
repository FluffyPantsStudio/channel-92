"""The lint rules on a synthetic film: an invented shot list and sung prompts (tests/lint/data/sample_*), lines and a
beat grid made here. The same checks run on the first film's own data in test_first_film_regression.py when
FLIX_FIRST_FILM is set; this file keeps them covered without it."""

import json
from pathlib import Path

import pytest

from atomic_flix.lint import book_from_case, book_from_plan, check_rule, run_rules
from atomic_flix.plan import Line, Pulse, parse_shot_list, plan_film
from atomic_flix.prompts import write_prompts

DATA = Path(__file__).resolve().parent / "data"
BEAT_S = 0.5                    # 120 bpm
ENDS_AT = 50.0
FILM = {"name": "Sample Harbour", "star": {"name": "Nova", "who": "a singer"}, "tone": "serious and soulful",
        "look": "photo", "wardrobe": {"rain": "wearing a long green raincoat with the hood down"}}
LINES = (("L01", "ooo-oh-ooo", 7.0, 10.0), ("L02", "Paper boats on a silver tide", 15.0, 17.6),
         ("L03", "Carry the names I could not hide", 18.0, 20.8), ("L04", "Count the lamps along the quay", 27.0, 29.4),
         ("L05", "Every one is lit for me", 29.8, 31.6), ("L06", "Hold the rope and let it go", 37.0, 39.8))


def sample_sung() -> list[dict]:
    return json.loads((DATA / "sample_sung.json").read_text(encoding="utf-8"))["shots"]


def kit_era(wording: str) -> str:
    """A sung prompt with the three wordings the lint rules exist to stop: a warm manner, a smile in her eyes and
    five fingers on each hand."""
    return (wording.replace("Her manner is serious and soulful.", "Her manner is calm and warm.")
            .replace("Her face stays serious and soulful while she sings; her mouth only shapes the words.",
                     "While she sings there is a smile in her eyes, never a grin.")
            .replace("natural anatomy.", "natural anatomy, five fingers on each hand."))


def _check(rule: str, shot: dict, wording: str) -> list:
    return check_rule(rule, book_from_case({"prompt": wording, "shot": {"key": shot["shot"]}}))


@pytest.fixture(scope="module")
def film():
    lines = [Line(key=key, part="lead", text=text, start=start, end=end, provenance="fixed")
             for key, text, start, end in LINES]
    shots = parse_shot_list((DATA / "sample_shots.txt").read_text(encoding="utf-8"))
    pulse = Pulse(beats=tuple(k * BEAT_S for k in range(int(ENDS_AT / BEAT_S) + 1)), downbeat_slot=0)
    plan = plan_film(shots, lines, pulse, ends_at=ENDS_AT, names=["Nova"])
    takes, stills = write_prompts(FILM, shots, plan.tasks, {line.key: line for line in lines})
    return {"lines": lines, "shots": shots, "pulse": pulse, "plan": plan, "takes": takes, "stills": stills}


def test_the_sample_shot_list_parses_into_cutaways_and_sung_shots(film):
    keys = [shot.key for shot in film["shots"]]
    assert keys == ["N01", "S01", "N02", "S02", "N03", "S03", "N04", "S04", "N05"]
    sung = {shot.key: tuple(shot.sings) for shot in film["shots"] if shot.sings}
    assert sung == {"S01": ("L01",), "S02": ("L02", "L03"), "S03": ("L04", "L05"), "S04": ("L06",)}


def test_named_hands_and_a_warm_manner_are_blocked_in_every_kit_era_prompt():
    shots = sample_sung()
    assert [s["shot"] for s in shots if _check("H1", s, kit_era(s["prompt"]))] == ["S01", "S02", "S03", "S04"]
    assert [s["shot"] for s in shots if _check("H2", s, kit_era(s["prompt"]))] == ["S01", "S02", "S03", "S04"]
    assert not [s["shot"] for s in shots if _check("H1", s, s["prompt"])]


def test_never_laughs_and_a_holding_rest_are_blocked_where_written():
    shots = sample_sung()
    assert [s["shot"] for s in shots if _check("H3", s, s["prompt"])] == ["S01", "S03"]   # "neither laughs" too
    assert [s["shot"] for s in shots if _check("L051", s, s["prompt"])] == ["S03"]


def test_the_sample_plan_cuts_on_the_bar_and_its_prompts_pass(film):
    plan = film["plan"]
    assert len(plan.cuts) == len(film["shots"])
    assert {cut.grid for cut in plan.cuts} <= {"lead", "one", "three"}
    book = book_from_plan({**FILM, "downbeat_slot": 0}, film["shots"], plan, film["lines"], film["pulse"],
                          prompts=film["takes"], still_prompts=film["stills"])
    assert not check_rule("L051", book)
    stoppers = {f.rule for f in run_rules(book, ["prompt"]) if f.level == "block"}
    assert stoppers <= {"CM1", "W1"}
