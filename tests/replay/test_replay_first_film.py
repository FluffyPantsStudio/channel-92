"""The first film's replay: its pure pieces always, the whole quick run with the first film's files (first_film)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import replay_estimate as est  # noqa: E402
import replay_steps as steps  # noqa: E402
from first_film_env import PRIVATE, UNSET, film_folder  # noqa: E402

FILM_SRC = film_folder()
FIXTURE = REPO / "fixtures" / "first-film"


def test_a_backing_part_at_a_lines_end_becomes_its_own_line():
    text = "[Chorus]\nLet's ride the magic tub (magical tub)\n(aa-h)\nPlain line\n"
    assert steps.replay_lyric(text) == "[Chorus]\nLet's ride the magic tub\n(magical tub)\n(aa-h)\nPlain line\n"


def test_shot_list_line_ids_take_our_numbering():
    assert steps.replay_shots("S02 vocal: L02 L03\n  act L02: oo\n  still: stills/L02.png") == \
        "S02 vocal: v02 v03\n  act v02: oo\n  still: stills/L02.png"


def test_counts_of_cut_times_on_a_grid():
    beats = [0.0, 0.5, 1.0, 1.5, 2.0]
    assert steps.counts_of([0.0, 0.51, 1.0, 1.75, 2.02], beats, 0) == {"1": 2, "2": 1, "3": 1, "4": 0, "off": 1}


def test_silent_tails_are_measured_from_the_last_line_of_each_vocal_shot():
    book = {"shots": [{"id": "S01", "show": [8.0, 14.5]}, {"id": "N01", "show": [14.5, 20.0]}]}
    table = [{"id": "L01", "t0": 9.0, "t1": 11.0}, {"id": "L02", "t0": 11.5, "t1": 13.0}]
    assert steps.silent_tails(book, table, "S01 vocal: L01 L02\n\nN01 cutaway\n") == [("S01", 1.5)]


def test_the_estimate_counts_takes_from_the_kept_passes_and_rerolls():
    tasks = {"S01": {"type": "vocal", "pin": "full", "seconds": 9}, "N01": {"type": "cutaway", "pin": "full",
                                                                           "seconds": 6}}
    case = est.estimate_case(tasks, "central")
    kept = sum(1 for stopped in est.SUNG_PASSES.values() if not stopped)
    assert case.sung_takes == round(est.FIRST_PASS_TAKES * kept + est.FIRST_PASS_TAKES * 0.5)
    assert case.plate_takes == round(est.FIRST_PASS_TAKES * 1.5 + est.HARD_PLATES * est.HARD_PLATE_EXTRA["central"])
    sung_s = case.sung_takes * 9 * est.RATES["sung_pinned"]
    assert case.gpu_hours_sung == pytest.approx(sung_s / 3600, rel=0.01)
    assert est.estimate_case(tasks, "low").gpu_hours < case.gpu_hours < est.estimate_case(tasks, "high").gpu_hours


@pytest.mark.first_film
def test_quick_replay_on_the_first_film(tmp_path, request):
    asked = "first_film" in (request.config.getoption("markexpr") or "") or os.environ.get("AF_FIRST_FILM") == "1"
    if not asked:
        pytest.skip("slow (about 30 s); run with -m first_film")
    if FILM_SRC is None:
        pytest.skip(UNSET)
    if not (FILM_SRC / "book.json").is_file() or not (FIXTURE / "audio" / "lead.wav").is_file():
        pytest.skip("the first film's folder or fixtures/first-film is not on this machine")
    if not (PRIVATE / "first_film_shots.txt").is_file():
        pytest.skip("the first film's shot list is not in docs/private/first-film (docs/first-film-replay.md)")
    import replay_first_film

    account = tmp_path / "replay.md"
    assert replay_first_film.main(["--work", str(tmp_path / "work"), "--report", str(account), "--quick"]) == 0
    data = json.loads((tmp_path / "work" / "replay.json").read_text(encoding="utf-8"))
    assert data["timing"]["with_fixes"] == 56
    assert data["bars"]["within_20ms"] >= 0.9 * data["bars"]["fixture_beats"]
    counts = data["plan"]["new_counts"]
    assert counts["2"] == 0 and counts["4"] == 0          # never a cut on the snare beats
    assert all(tail <= 1.0 for _, tail in data["new_tails"])
    assert data["placing"]["over_0_2"] == 0
    text = account.read_text(encoding="utf-8")
    assert "ESTIMATE" in text and "\u2014" not in text
