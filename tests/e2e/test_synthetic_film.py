"""A whole film on a tiny synthetic song, with no GPU: the steps of docs/quickstart.md, in order.

new -> structure -> gates 1 and 2 -> time -> bars -> stills and gates 3 and 4 -> plan -> lint -> budget -> gate 5 -> shoot (fake
ComfyUI) -> place -> cut -> grade -> review -> finish -> compare. Each step reads and writes the film's own folder.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from atomic_flix.cli import main
from atomic_flix.compare.ledger import read_job_log
from atomic_flix.cut.media import probe, write_image
from atomic_flix.lint.registry import RULE_DATA
from fake_comfyui import FakeComfy
from fake_renders import make_clip
from runner_samples import SILENT_GRAPH, SUNG_GRAPH, write_graph
from tool_loader import load_tool

PERSON = ["--by", "Test Person"]
BASELINE = {
    "film": "First Film",
    "gpu": {"by_kind_of_job_seconds": {"sung_takes": {"seconds": 36000}, "plate_takes": {"seconds": 18000},
                                       "total": {"hours": 33.9}}},
    "takes": {"rendered_total": {"value": 839}, "sung": {"per_shot_mean": 20.0}, "plate": {"per_shot_mean": 10.0}},
    "rendered_to_finished": {"finished_film_seconds": {"value": 200.0}, "ratio": {"value": 26.7}},
    "builds_and_reviews": {"numbered_builds": {"value": 24}},
}


def run(*args, expect: int = 0) -> None:
    code = main([str(a) for a in args])
    assert code == expect, f"atomic-flix {' '.join(map(str, args))} returned {code}"


def gate(film: Path, name: str, words: str, *shown: str) -> None:
    if name != "spend":
        run("gate", film, "ask", name, *[x for item in shown for x in ("--shown", item)])
    else:
        run("gate", film, "ask", name)
    run("gate", film, "answer", name, *PERSON, "--words", words)


def write_stills(film: Path, keys: list[str]) -> None:
    passed = {item["id"]: "PASS: checked at full size" for item in RULE_DATA["reviewer"]}
    rng = np.random.default_rng(3)
    for key in keys:
        picture = (rng.random((256, 448, 3)) * 255).astype(np.uint8)
        write_image(film / "stills" / f"{key}.png", picture)
        record = {"how": "synthetic test picture", "figures": [],
                  "judge": {"verdict": "PASS", "full_size": True, "items": passed}}
        (film / "stills" / f"{key}.json").write_text(json.dumps(record), encoding="utf-8")


@pytest.fixture
def song(tmp_path):
    folder = tmp_path / "song"
    truth = load_tool("synth_song").write_song(folder)
    return folder, truth


def test_a_tiny_film_from_stems_to_compare(tmp_path, song, capsys):
    began = time.monotonic()
    provenance, truth = song
    film = tmp_path / "films" / "tiny-song"

    run("new", film, "--song", provenance / "mix.wav", "--voice", provenance / "voice.wav", "--band", provenance / "band.wav",
        "--drums", provenance / "drums.wav", "--lyric", provenance / "lyric.txt", "--shots", provenance / "shots.txt",
        "--star", "Nova", "--who", "a singer with short silver hair", "--aspect", "16:9", "--by", "Test Person",
        "--words", "wide, like the channel's later years")
    data = json.loads((film / "film.json").read_text(encoding="utf-8"))
    data.update({"frame": [448, 256], "final_size": [448, 256], "batch": {"takes": 1, "cards": 1},
                 "wardrobe": {"main": "wearing a white jacket over a black top"}})
    (film / "film.json").write_text(json.dumps(data), encoding="utf-8")

    run("structure", film)
    assert (film / "plan/structure.md").is_file()
    gate(film, "concept", "the rooftop one", "pitches.md", "plan/structure.md")
    run("time", film)
    lines = {line["id"]: line for line in json.loads((film / "analysis/voice-lines.json").read_text("utf-8"))["lines"]}
    for expected in truth["lines"]:
        assert lines[expected["id"]]["start"] == pytest.approx(expected["start"], abs=0.10)   # roadmap 1a: 0.10 s
    run("bars", film)
    pulse = json.loads((film / "analysis/pulse.json").read_text(encoding="utf-8"))
    assert pulse["downbeat_slot"] == truth["downbeat_slot"]
    assert np.max(np.abs(np.array(pulse["beats"]) - np.array(truth["beats"]))) < 0.02
    gate(film, "song", "yes, that is the song and the one is right", "audio/mix.wav")

    write_stills(film, ["S01", "N01", "S02", "S03", "N02"])
    gate(film, "looks", "that is her", "stills/S01.png")
    run("plan", film)
    cuts = json.loads((film / "plan/cuts.json").read_text(encoding="utf-8"))["cuts"]
    assert [cut["key"] for cut in cuts] == ["S01", "N01", "S02", "S03", "N02"]
    assert cuts[0]["grid"] == "lead" and all(cut["grid"] in ("one", "three") for cut in cuts[1:])
    gate(film, "board", "render it", "plan/board.html")

    run("lint", film, expect=1)                     # no approved hours yet: gate 5 blocks
    assert "L127" in capsys.readouterr().out
    run("budget", film)
    assert json.loads((film / "plan/budget.json").read_text(encoding="utf-8"))["takes"] == 5
    assert main(["gate", str(film), "ask", "spend"]) == 2       # gate 5 waits for a fresh eval
    run("eval", film)
    report = json.loads((film / "eval/report.json").read_text(encoding="utf-8"))
    assert report["verdicts"]["spend"] != "BLOCKED", report["blocking"]["spend"]
    gate(film, "spend", "yes, run it")
    run("lint", film)

    graphs = film / "graphs"                        # a graph is read from the film folder (or the kit's own)
    sung = write_graph(graphs, "sung.json", SUNG_GRAPH, {"needs": ["wording", "opening_still", "audio"], "light": True})
    plate = write_graph(graphs, "plate.json", SILENT_GRAPH, {"needs": ["wording", "opening_still"], "light": True})
    fake = FakeComfy(gpu_ms=30_000, renderer=make_clip).start()
    try:
        run("shoot", film, "--sung-graph", sung, "--plate-graph", plate, "--hosts", fake.host, "--poll", "0.05",
            "--timeout", "60")
    finally:
        fake.close()
    job_log = read_job_log(film / "job-log.jsonl").logged
    assert sorted((e.shot, e.kind, e.state) for e in job_log) == [
        ("N01", "cutaway", "done"), ("N02", "cutaway", "done"), ("S01", "vocal", "done"), ("S02", "vocal", "done"), ("S03", "vocal", "done")]

    run("place", film)
    for key in ("S01", "S02", "S03"):
        fit = json.loads((film / f"renders/{key}/r001.fit.json").read_text(encoding="utf-8"))
        assert fit["how"] == "sound" and fit["map"]
        assert max(phrase["cost"] for phrase in fit["vocal_spans"]) < 0.2
        assert abs(fit["offset"]) < 0.05

    run("cut", film, "--speed", "ultrafast")
    audit = json.loads((film / "cuts/v01.audit.json").read_text(encoding="utf-8"))
    assert audit["errors"] == []
    audio = audit["audio"]                          # one plain gain toward -14 LUFS, the peak kept under -1 dBFS
    assert audio["peak_after_db"] <= -1.0 + 0.05 and audio["lufs_after"] <= -14.0 + 0.5
    clip = probe(film / "cuts/v01.mp4")
    assert (clip.width, clip.height) == (448, 256)
    assert "logo" not in json.loads((film / "cuts/v01.edit.json").read_text(encoding="utf-8"))   # the cut is clean
    strobe = json.loads((film / "cuts/v01-strobe.json").read_text(encoding="utf-8"))
    assert strobe["passed"] is True

    run("grade", film, "--speed", "ultrafast")
    tone = json.loads((film / "cuts/v01-toned.tone.json").read_text(encoding="utf-8"))
    assert tone["grain"] is None and len(tone["shots"]) == len(json.loads(
        (film / "plan/cuts.json").read_text(encoding="utf-8"))["cuts"])
    assert json.loads((film / "cuts/v01-toned-strobe.json").read_text(encoding="utf-8"))["passed"] is True

    run("review", film)
    assert (film / "review/v01/MANIFEST.txt").is_file()

    toned = (film / "cuts/v01-toned.mp4").read_bytes()
    run("finish", film, "--speed", "ultrafast")    # no year: the logo, no era look
    assert "no era" in capsys.readouterr().out
    assert probe(film / "cuts/v01-final.mp4").frames == probe(film / "cuts/v01-toned.mp4").frames
    assert (film / "cuts/v01-toned.mp4").read_bytes() == toned

    run("eval", film, expect=1)                     # before v1: no cold review round yet, no judge times
    report = json.loads((film / "eval/report.json").read_text(encoding="utf-8"))
    assert report["stage"] == "v1" and "LG-ROUNDS film" in report["blocking"]["v1"]
    verdicts = {row["rule"]: row["verdict"] for row in report["rows"] if row["rule"].startswith("CT-")}
    assert verdicts["CT-AUDIT"] == verdicts["CT-GRADE"] == verdicts["CT-GRAIN"] == verdicts["CT-FLASH"] == "pass"
    assert main(["gate", str(film), "ask", "v1", "--shown", "cuts/v01-toned.mp4"]) == 2

    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(BASELINE), encoding="utf-8")
    run("compare", film, "--baseline", baseline, "--out", film / "review/compare.md")
    account = (film / "review/compare.md").read_text(encoding="utf-8")
    assert account.startswith("# Tiny Song against First Film")
    run("progress", film)
    assert time.monotonic() - began < 120


def test_overview_names_every_film_verb(capsys):
    assert main([]) == 0
    text = capsys.readouterr().out
    for verb in ("new", "time", "bars", "plan", "lint", "budget", "shoot", "place", "cut", "grade", "review",
                 "compare"):
        assert f"  {verb} " in text


def test_an_unknown_verb_is_refused(capsys):
    assert main(["fly"]) == 2
    assert "no verb" in capsys.readouterr().err


def test_shoot_refuses_before_gate_five(tmp_path, song, capsys):
    provenance, _ = song
    film = tmp_path / "films" / "early"
    run("new", film, "--song", provenance / "mix.wav", "--voice", provenance / "voice.wav")
    assert main(["shoot", str(film)]) == 2
    assert "gate 1" in capsys.readouterr().err
