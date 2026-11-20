"""Replay our first film (The Girl In The Magic Tub) through plan and lint.

The costly mistakes of that film must be caught or blocked before a GPU is used: the smiling still (L014), named
hands (L031), the late downbeat (L060), and the end freeze (L051, L051b). Run with `-s` to see what was caught.

The line table and beat grid come from fixtures/first-film (made by tools/make_fixtures.py first-film, not in git);
the sung prompts from the film's own record under FLIX_FIRST_FILM, and the shot list (rewritten in the kit's format
from the film's shot table) from docs/private/first-film/, which is not in git either (docs/first-film-replay.md).
The same rules on synthetic data: test_lint_samples.py.
"""

import json
from pathlib import Path

import pytest

from atomic_flix.lint import book_from_case, book_from_plan, check_rule, preflight, run_rules
from atomic_flix.plan import Line, Pulse, parse_shot_list, plan_film
from atomic_flix.prompts import write_prompts
from first_film_env import PRIVATE, UNSET, first_film_star, flix_root
from first_film_env import sung_record as sung_record_path

pytestmark = pytest.mark.first_film

REPO = Path(__file__).resolve().parents[2]
BUILD = REPO / "fixtures" / "first-film" / "build"
SUNG = sung_record_path()
STAR = first_film_star()
SHOT_LIST = PRIVATE / "first_film_shots.txt"
ENDS_AT = 278.7
FILM = {"name": "Girl In The Magic Tub", "star": {"name": STAR, "who": "an android singer"},
        "tone": "serious and soulful", "look": "photo",
        "wardrobe": {"eighties": "wearing a white 1980s jacket with wide padded shoulders over a black top"}}

if flix_root() is None:
    pytest.skip(UNSET, allow_module_level=True)
if SUNG is None or STAR is None:
    pytest.skip("the first film's sung record or its book (with the singer's name) is not on this machine",
                allow_module_level=True)
if not (BUILD / "lines.json").exists():
    pytest.skip("fixtures/first-film is missing: run tools/make_fixtures.py first-film", allow_module_level=True)
if not SUNG.is_file() or not SHOT_LIST.is_file():
    pytest.skip(f"the first film's sung record ({SUNG}) or shot list ({SHOT_LIST}) is not on this machine",
                allow_module_level=True)


def first_film_lines() -> list[Line]:
    """The first film's hand-fixed line table, read from the fixture's own format into ours."""
    rows = json.loads((BUILD / "lines.json").read_text(encoding="utf-8"))["lines"]
    return [Line(key=row["id"], part=row.get("who", "lead"), text=row.get("words", ""), start=row["t0"],
                 end=row["t1"], gaps=tuple(tuple(p) for p in row.get("pauses", [])),
                 provenance="fixed" if row.get("fixed") else "level") for row in rows]


def first_film_beats() -> tuple[float, ...]:
    return tuple(json.loads((BUILD / "beats.json").read_text(encoding="utf-8"))["beats"])


def sung_record() -> dict:
    return json.loads(SUNG.read_text(encoding="utf-8"))


def kit_era(wording: str) -> str:
    """A sung prompt as the earlier kit wrote it, before our patch script (films/.../plates.py) undid three things:
    'calm and warm', a smile in her eyes 'never a grin', and five fingers on each hand."""
    return (wording.replace("Her manner is serious and soulful.", "Her manner is calm and warm.")
            .replace("Her face stays serious and soulful while she sings; her mouth only shapes the words.",
                     "While she sings there is a smile in her eyes, never a grin.")
            .replace("natural anatomy.", "natural anatomy, five fingers on each hand."))


@pytest.fixture(scope="module")
def film():
    lines = first_film_lines()
    shots = parse_shot_list(SHOT_LIST.read_text(encoding="utf-8"))
    pulse = Pulse(beats=first_film_beats(), downbeat_slot=0)
    plan = plan_film(shots, lines, pulse, ends_at=ENDS_AT, names=[STAR])
    take_files, keyframes = write_prompts(FILM, shots, plan.tasks, {line.key: line for line in lines})
    return {"lines": lines, "shots": shots, "pulse": pulse, "plan": plan, "clip_prompts": take_files, "keyframes": keyframes}


def test_named_hands_are_blocked():
    """Round two said 'her hands stay down, out of frame'; the kit wrote 'five fingers on each hand' into all 25."""
    caught = []
    for shot in sung_record()["shots"]:
        found = check_rule("H1", book_from_case({"prompt": kit_era(shot["prompt"]), "shot": {"key": shot["shot"]}}))
        caught += [finding.key for finding in found]
    assert len(caught) == 25
    round_two = "She sings to us, swaying gently. Her hands stay down, out of frame."
    assert check_rule("H1", book_from_case({"prompt": round_two}))
    print(f"\nnamed hands: H1 blocks {len(caught)} of 25 kit-era sung prompts and the round-two wording")


def test_warm_manner_and_never_laughs_are_blocked():
    shots = sung_record()["shots"]
    warm = [s["shot"] for s in shots
            if check_rule("H2", book_from_case({"prompt": kit_era(s["prompt"]), "shot": {"key": s["shot"]}}))]
    assert len(warm) == 25
    laughs = [s["shot"] for s in shots
              if check_rule("H3", book_from_case({"prompt": s["prompt"], "shot": {"key": s["shot"]}}))]
    assert laughs == ["S01", "S05", "S10", "S12", "S19", "S21"]
    hands_in_final = [s["shot"] for s in shots
                      if check_rule("H1", book_from_case({"prompt": s["prompt"], "shot": {"key": s["shot"]}}))]
    assert hands_in_final == []
    print(f"\ngrin wording: H2 blocks {len(warm)} kit-era prompts; H3 blocks 'never laughs' in {', '.join(laughs)}")


def test_smiling_still_is_blocked():
    """S20's first frame has a small smile (found 2026-11-17). With a judge record it blocks; without one, the batch
    is blocked by the missing record and the mouth question is asked, never answered for the person."""
    record = {"judge": {"verdict": "PASS", "full_size": True,
                        "items": {"mouth": "REJECT small smile, short cheek lines"}}}
    judged = book_from_case({"shot": {"key": "S20"}, "still": record})
    assert [f.key for f in check_rule("L014", judged)] == ["S20"]
    unjudged = book_from_case({"shot": {"key": "S20"}})
    verdict = preflight(unjudged)
    assert "L010" in [f.rule for f in verdict.stoppers]
    assert any(item.id == "mouth" and item.awaiting for item in verdict.review)
    print("\nsmiling still: L014 blocks S20 with the judge's answer; without one, L010 blocks and the mouth question "
          "is asked")


def test_late_downbeat_is_blocked_and_our_bar_avoids_the_snare():
    beats = first_film_beats()
    old_grid = Pulse(beats=beats, downbeat_slot=1)            # the kit's 'downbeat' was beat 2 of the real bar
    blocked = check_rule("L060", book_from_case({"pulse": {"beats": list(beats), "downbeat_slot": 1}}))
    assert blocked
    tie = {"beats": list(beats), "downbeat_slot": 0, "grounds": {"clearance": 0.001, "spans_backing": "5/8"}}
    assert check_rule("L060", book_from_case({"pulse": tie}))
    assert not check_rule("L060", book_from_case({"pulse": tie, "film": {"downbeat_slot": 0}}))
    shots = parse_shot_list(SHOT_LIST.read_text(encoding="utf-8"))
    lines = first_film_lines()
    snare = {round(t, 3) for k, t in enumerate(beats) if k % 2 == 1}
    old = plan_film(shots, lines, old_grid, ends_at=ENDS_AT)
    new = plan_film(shots, lines, Pulse(beats=beats, downbeat_slot=0), ends_at=ENDS_AT)
    on_snare_old = sum(round(cut.at, 3) in snare for cut in old.cuts)
    on_snare_new = sum(round(cut.at, 3) in snare for cut in new.cuts)
    assert on_snare_old > 30
    assert on_snare_new == 0
    print(f"\nlate downbeat: L060 blocks the kit's grid (no evidence) and the 0-or-2 tie until downbeat_slot is set by "
          f"ear; on the kit's grid {on_snare_old} of {len(old.cuts)} cuts land on a snare beat, on ours "
          f"{on_snare_new}")


def test_end_freeze_is_blocked_in_the_old_cut_and_absent_from_ours(film):
    """The shipped cut held pinned shots past her last word; our plan moves those cuts. The kit's closing rest
    'they close their lips and hold each other's gaze' is blocked too."""
    lines = {line.key: line for line in film["lines"]}
    shots = {shot.key: shot for shot in film["shots"]}
    tasks, rows = {}, sung_record()["shots"]
    for row in rows:
        shot = shots[row["shot"]]
        last = max(lines[key].end for key in shot.sings)
        tasks[row["shot"]] = {"key": row["shot"], "type": "vocal", "shown_at": row["shown_s"], "slice_start": 0.0,
                              "seconds": 15, "pin": "full" if "pinned" in row["workflow"] else "none",
                              "last_sound": last, "steps": []}
    old = book_from_plan(FILM, [shots[r["shot"]] for r in rows], film["plan"], lines, film["pulse"])
    old.tasks = tasks
    held = sorted(f.key for f in check_rule("P1", old))
    assert held == ["S06", "S17", "S20", "S23", "S24", "S25"]
    closing = [r["shot"] for r in rows
               if check_rule("L051", book_from_case({"prompt": r["prompt"], "shot": {"key": r["shot"]}}))]
    assert closing == ["S05"]
    ours = book_from_plan(FILM, film["shots"], film["plan"], film["lines"], film["pulse"], prompts=film["clip_prompts"])
    assert not check_rule("P1", ours)
    assert not check_rule("L051", ours)
    moved = [cut.key for cut in film["plan"].cuts if "moved earlier" in cut.note]
    print(f"\nend freeze: P1 blocks the shipped cut's {', '.join(held)} (pinned, 1.2 to 1.8 s past the last word); "
          f"L051 blocks S05's holding rest; our plan has no P1 ({len(moved)} cuts moved) and no holding rest")


def test_our_plan_cuts_on_the_bar_and_our_prompts_pass_the_prompt_rules(film):
    plan = film["plan"]
    grids = [cut.grid for cut in plan.cuts]
    assert set(grids) <= {"lead", "one", "three"}
    confirmed = {**FILM, "downbeat_slot": 0}       # fixtures/first-film/TRUTH.txt: phase 0, to be confirmed by ear
    book = book_from_plan(confirmed, film["shots"], plan, film["lines"], film["pulse"], prompts=film["clip_prompts"],
                          still_prompts=film["keyframes"])
    stoppers = {(f.rule, f.key) for f in run_rules(book, ["prompt"]) if f.level == "block"}
    # left for the person, by design: camera moves need drawn end stills, people in water need their garment named
    assert {rule for rule, _ in stoppers} <= {"CM1", "W1"}
    assert not [f for f in run_rules(book, ["plan"]) if f.level == "block" and f.rule != "WIN1"]
    span = [f.key for f in run_rules(book, ["plan"]) if f.rule == "WIN1"]
    assert span == ["N19"]                 # 17.3 s on screen: the film cut it in two (N19, N20)
    print(f"\nour plan: {len(grids)} cuts, all on one or three; prompt blocks left for the person: "
          f"{sorted(stoppers)}; WIN1 on {span}")
