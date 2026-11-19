"""Prompt builders: our sung-shot recipe, silent shots, plates and first-frame stills (core spec, stage 4)."""

import re

import pytest

from atomic_flix.plan import Line, Pulse, ShotSpec, plan_film
from atomic_flix.prompts import (edit_prompt, plate_prompt, silent_prompt, still_prompt, sung_prompt,
                                 sung_words, framing_phrase, is_wordless)

FILM = {"name": "Magic Tub", "star": {"name": "Frankie", "who": "an android singer with red curly hair"},
        "wardrobe": {"eighties": "wearing a white 1980s jacket with wide padded shoulders over a black top"},
        "tone": "serious and soulful"}


def build(shots, lines, ends_at=30.0):
    pulse = Pulse(beats=tuple(round(k * 0.5, 3) for k in range(int(ends_at / 0.5) + 1)), downbeat_slot=0)
    return plan_film(shots, lines, pulse, ends_at=ends_at)


def sung_case(text="Hush now, the tub is warm", crop=1.0, acts=None):
    lines = [Line(key="v01", part="lead", text=text, start=10.4, end=13.6)]
    shot = ShotSpec(key="S01", kind="vocal", sings=("v01",), place="a white salt desert", crop=crop,
                    acts=acts or {}, still="stills/S01.png")
    plan = build([ShotSpec(key="N01", kind="cutaway"), shot, ShotSpec(key="N02", kind="cutaway")], lines)
    return shot, plan.tasks["S01"], {line.key: line for line in lines}


def test_sung_prompt_follows_the_recipe_in_order():
    shot, task, lines = sung_case()
    text = sung_prompt(FILM, shot, task, lines)
    order = ["Frankie sings to us from a white salt desert.", "she never turns away",
             "Her manner is serious and soulful.", '"Hush now, the tub is warm"',
             "her mouth only shapes the words", "Frankie looks just as she does in the first frame"]
    positions = [text.index(piece) for piece in order]
    assert positions == sorted(positions)
    assert "from the chest up" in text


def test_sung_prompt_states_exact_seconds_and_words():
    shot, task, lines = sung_case()
    text = sung_prompt(FILM, shot, task, lines)
    spans = [(int(a), int(b)) for a, b in re.findall(r"^(\d+)-(\d+)s:", text, flags=re.M)]
    assert spans[0][0] == 0 and spans[-1][1] == task["seconds"]
    assert all(left[1] == right[0] for left, right in zip(spans, spans[1:]))


def test_sung_prompt_has_one_negative_and_no_hands_smile_or_grain():
    shot, task, lines = sung_case()
    text = sung_prompt(FILM, shot, task, lines).lower()
    for word in ("hand", "arm ", "finger", "wrist", "grain", "texture", "film stock", "laugh", "grin", "tripod"):
        assert word not in text
    negatives = re.findall(r"\b(never|not|no|without|don't|doesn't)\b", text)
    assert negatives == ["never"]
    assert "never turns away" in text


def test_sung_prompt_has_no_camera_line_when_the_camera_is_not_the_point():
    shot, task, lines = sung_case()
    assert "Camera:" not in sung_prompt(FILM, shot, task, lines)


def test_collar_framing_for_a_tight_crop():
    assert framing_phrase(0.7) == "from the collar up"
    assert framing_phrase(0.75) == "from the chest up"
    shot, task, lines = sung_case(crop=0.62)
    assert "from the collar up" in sung_prompt(FILM, shot, task, lines)


def test_wordless_note_gets_the_round_mouth():
    assert is_wordless("aa-h-aaaaa-aha-aaaaaah")
    assert is_wordless("Ooh, ooh")
    assert not is_wordless("Oh my love")
    shot, task, lines = sung_case(text="aa-h-aaaaa-aha-aaaaaah")
    assert "her lips in a soft round oo" in sung_prompt(FILM, shot, task, lines)


def test_one_plain_clause_per_sung_step():
    shot, task, lines = sung_case(acts={"v01": "she lifts her chin a little"})
    text = sung_prompt(FILM, shot, task, lines)
    sung_steps = [row for row in text.splitlines() if "she sings" in row]
    assert sung_steps and all(row.count(";") <= 2 for row in sung_steps)
    assert "she lifts her chin a little" in text


def test_full_stop_without_a_pause_becomes_a_comma():
    # spec: "Come on, come on. Just don't let go." with no pause at the stop
    lines = [Line(key="v01", part="lead", text="Come on, come on. Just don't let go.", start=1.0, end=4.0)]
    assert sung_words(["v01"], {"v01": lines[0]}) == "Come on, come on, just don't let go."


def test_full_stop_kept_where_the_stem_pauses():
    lines = {"v01": Line(key="v01", part="lead", text="Come on, come on. Just don't let go.", start=1.0, end=4.0,
                         gaps=((2.0, 2.4),))}
    assert sung_words(["v01"], lines) == "Come on, come on. Just don't let go."


def test_line_end_stop_becomes_a_comma_when_the_next_line_follows_at_once():
    lines = {"v01": Line(key="v01", part="lead", text="I fall.", start=1.0, end=2.0),
             "v02": Line(key="v02", part="lead", text="I rise.", start=2.1, end=3.0),
             "v03": Line(key="v03", part="lead", text="Again.", start=4.0, end=5.0)}
    assert sung_words(["v01", "v02", "v03"], lines) == "I fall, I rise. Again."


def test_silent_prompt_keeps_lips_closed_and_her_person():
    shot = ShotSpec(key="M01", kind="mute", figures=True, place="a bare grey room",
                    beats=("she looks up at the light", "she breathes out slowly"))
    plan = build([shot], [], ends_at=8.0)
    text = silent_prompt(FILM, shot, plan.tasks["M01"])
    assert "lips" in text and "closed" in text
    assert "stays the same person" in text
    assert "nobody new appears" in text
    assert "No people" not in text


def test_plate_prompt_with_no_people_and_a_moving_camera():
    shot = ShotSpec(key="N01", kind="cutaway", figures=False, goal="an empty street of filing-cabinet towers",
                    beats=("a drawer slides open",), cam_move="a slow push-in along the street")
    plan = build([shot], [], ends_at=8.0)
    text = plate_prompt(FILM, shot, plan.tasks["N01"])
    assert "Camera: a slow push-in along the street." in text
    assert "Colours, light and materials" in text
    assert "grain" not in text.lower()


def test_plate_prompt_omits_the_camera_when_it_is_locked():
    shot = ShotSpec(key="N01", kind="cutaway", figures=False, goal="an empty street", beats=("dust drifts",),
                    cam_move="locked")
    plan = build([shot], [], ends_at=5.0)
    assert "Camera:" not in plate_prompt(FILM, shot, plan.tasks["N01"])


def test_still_prompt_ends_with_the_edge_and_text_lines():
    shot = ShotSpec(key="S01", kind="vocal", sings=("v01",), place="a white salt desert", crop=1.0)
    text = still_prompt(FILM, shot)
    assert text.endswith("The picture fills the whole frame edge to edge. No text, no letters, no logos.")
    assert text.startswith("Photograph")
    assert "lips closed" in text
    assert "smil" not in text.lower() and "hand" not in text.lower()


def test_still_prompt_in_water_names_what_she_wears():
    shot = ShotSpec(key="N09", kind="cutaway", figures=True, place="a bath of still water under a pink sky",
                    extra={"wears": "a plain grey tank top"})
    text = still_prompt(FILM, shot)
    assert "grey tank top" in text


def test_edit_prompt_keeps_the_picture_and_names_one_change():
    text = edit_prompt("her lips are closed and level")
    assert text.startswith("The photograph in <ref_image_0>, exactly as it is, with one change:")
    assert text.endswith("No text, no letters, no logos.")


def test_builders_refuse_a_shot_of_the_wrong_kind():
    shot, task, lines = sung_case()
    with pytest.raises(ValueError):
        plate_prompt(FILM, shot, task)


def test_stop_at_a_step_end_becomes_a_comma_when_she_sings_straight_on():
    lines = [Line(key="v01", part="lead", text="Hush now, the tub is warm.", start=10.4, end=13.6),
             Line(key="v02", part="lead", text="Hold on.", start=13.7, end=16.0)]
    shots = [ShotSpec(key="N01", kind="cutaway"), ShotSpec(key="S01", kind="vocal", sings=("v01", "v02"))]
    plan = build(shots, lines)
    words = [step[3] for step in plan.tasks["S01"]["steps"] if step[3]]
    assert words == ["Hush now, the tub is warm,", "Hold on."]
