"""Preflight over a whole film folder: plan, prompts, stills' records, report and board; refuses before any GPU."""

import hashlib
import json

import numpy as np
import pytest

from atomic_flix.lint import load_book, preflight
from atomic_flix.lint.__main__ import main as lint_main
from atomic_flix.plan.__main__ import main as plan_main
from atomic_flix.wav import save_wav
from sheet_samples import write_sheet

SHOTS = """\
N01 cutaway
  figures: no
  beat: dust drifts slowly through the light

S01 vocal: v01
  crop: 1.0
  place: a white salt desert
  gaze: at us
  act v01: she sways gently with the music

N02 cutaway
  figures: no
  beat: the pink sky turns slowly
"""

PASS_ALL = {"hands": "PASS", "mouth": "PASS", "identity": "PASS", "gaze": "PASS", "build": "PASS", "flat": "PASS"}


def make_film(root, shots=SHOTS):
    rate = 48000
    t = np.arange(int(22 * rate)) / rate
    voice = np.where((t >= 10.4) & (t < 13.6), 0.2 * np.sin(2 * np.pi * 220 * t), 0.0)
    save_wav(root / "audio" / "voice.wav", voice, rate)
    save_wav(root / "audio" / "mix.wav", voice * 0.5, rate)
    sha = hashlib.sha256((root / "audio" / "mix.wav").read_bytes()).hexdigest()
    film = {"name": "Test Tub", "star": {"name": "Nova", "who": "an android singer with red curls"},
            "wardrobe": {"eighties": "wearing a white 1980s jacket with wide padded shoulders over a black top"},
            "tone": "serious and soulful", "stems": {"mix": "audio/mix.wav", "voice": "audio/voice.wav"},
            "downbeat_slot": 0, "ends_at": 22.0, "look": "photo",
            "characters": {"Nova": {"identity": "refs/front.png", "hero": "refs/front.png", "body": "refs/body.png",
                                    "views": write_sheet(root, "Nova")}},
            "gates": {"song": {"sha256": sha}, "look": {"words": "yes, that is her"},
                      "spend": {"budget_s": 100000}},
            "batch": {"takes": 2, "cards": 2}}
    (root / "film.json").write_text(json.dumps(film), encoding="utf-8")
    (root / "shots.txt").write_text(shots, encoding="utf-8")
    (root / "analysis").mkdir()
    (root / "analysis" / "voice-lines.json").write_text(json.dumps(
        {"sung_db": -14.0, "lines": [{"id": "v01", "part": "lead", "text": "Hush now, the tub is warm.",
                                         "start": 10.4, "end": 13.6, "gaps": [], "provenance": "level", "flags": []}]}),
        encoding="utf-8")
    beats = [round(k * 0.5, 3) for k in range(45)]
    (root / "analysis" / "pulse.json").write_text(json.dumps(
        {"bpm": 120, "beats": beats, "downbeat_slot": 0, "grounds": {"clearance": 0.8, "spans_backing": "9/10"}}),
        encoding="utf-8")
    (root / "stills").mkdir()
    for key in ("N01", "S01", "N02"):
        (root / "stills" / f"{key}.png").write_bytes(b"png placeholder")
        record = {"judge": {"verdict": "PASS", "full_size": True, "items": PASS_ALL}}
        if key == "S01":
            record.update({"figures": ["Nova"], "refs": ["refs/front.png", "refs/body.png"]})
        (root / "stills" / f"{key}.json").write_text(json.dumps(record), encoding="utf-8")
    return root


def test_a_clean_film_passes_preflight_and_writes_the_report_and_board(tmp_path, capsys):
    root = make_film(tmp_path)
    assert plan_main([str(root)]) == 0
    assert (root / "plan" / "S01.voice-soft.wav").exists()
    assert (root / "plan" / "S01.prompt.txt").exists()
    code = lint_main([str(root)])
    out = capsys.readouterr().out
    assert code == 0, out
    account = (root / "plan" / "report.md").read_text(encoding="utf-8")
    assert "takes at 1280x704" in account and "GPU hours" in account
    assert "| S01 | sung | full |" in account
    board = (root / "plan" / "board.html").read_text(encoding="utf-8")
    for key in ("N01", "S01", "N02"):
        assert key in board
    assert 'src="stills/S01.png"' in board
    assert "Hush now, the tub is warm." in board.replace("&#x27;", "'")


def test_one_blocking_rule_refuses_the_batch(tmp_path, capsys):
    root = make_film(tmp_path, SHOTS.replace("act v01: she sways gently with the music",
                                             "act v01: she smiles at us, her hands open"))
    assert plan_main([str(root)]) == 0
    assert lint_main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "H1" in out and "H2" in out and "BLOCKED" in out
    assert "BLOCKED" in (root / "plan" / "report.md").read_text(encoding="utf-8")


def test_a_missing_judge_answer_blocks_and_is_asked(tmp_path):
    root = make_film(tmp_path)
    record = json.loads((root / "stills" / "S01.json").read_text(encoding="utf-8"))
    record["judge"]["items"] = {k: v for k, v in PASS_ALL.items() if k != "mouth"}
    (root / "stills" / "S01.json").write_text(json.dumps(record), encoding="utf-8")
    plan_main([str(root)])
    verdict = preflight(load_book(root))
    assert verdict.blocked
    assert not verdict.stoppers
    assert [(item.key, item.id) for item in verdict.open_review] == [("S01", "mouth")]


def test_over_budget_is_refused(tmp_path):
    root = make_film(tmp_path)
    film = json.loads((root / "film.json").read_text(encoding="utf-8"))
    film["gates"]["spend"]["budget_s"] = 60
    (root / "film.json").write_text(json.dumps(film), encoding="utf-8")
    plan_main([str(root)])
    verdict = preflight(load_book(root))
    assert [finding.rule for finding in verdict.stoppers] == ["L127"]


def test_a_changed_mix_stops_the_batch(tmp_path):
    root = make_film(tmp_path)
    plan_main([str(root)])
    save_wav(root / "audio" / "mix.wav", np.zeros(4800), 48000)
    assert "L006" in [finding.rule for finding in preflight(load_book(root)).stoppers]


def test_a_warn_with_a_written_reason_is_marked_answered(tmp_path):
    root = make_film(tmp_path, SHOTS.replace("  gaze: at us\n", ""))
    film = json.loads((root / "film.json").read_text(encoding="utf-8"))
    film["reasons"] = {"L020:S01": "she looks at us, as every sung shot does"}
    (root / "film.json").write_text(json.dumps(film), encoding="utf-8")
    plan_main([str(root)])
    warns = [f for f in preflight(load_book(root)).warns if f.rule == "L020"]
    assert warns and warns[0].reason.startswith("she looks at us")


def test_plan_cli_reports_a_bad_shot_list(tmp_path, capsys):
    root = make_film(tmp_path, "S01 vocal: v09\n")
    assert plan_main([str(root)]) == 2
    assert "v09" in capsys.readouterr().err


@pytest.mark.parametrize("flag", [["--vet"]])
def test_vet_mode_exits_one_only_on_blocks(tmp_path, flag):
    root = make_film(tmp_path)
    plan_main([str(root)])
    assert lint_main([str(root), *flag]) == 0
