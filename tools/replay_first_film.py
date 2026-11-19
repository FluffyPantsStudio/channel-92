"""Replay our first film (The Girl In The Magic Tub) through the new kit, on the CPU, and write a report.

    python tools/replay_first_film.py [--film-src DIR] [--work DIR] [--baseline FILE] [--shots FILE] [--quick]

The first film's folder and baseline default to their places under FLIX_FIRST_FILM, the shot list to
docs/private/first-film/ (docs/first-film-replay.md).

1. A project from the first film's own data: stems (fixtures/first-film/audio), lyric, the hand-fixed line table
   and beat grid (fixtures/first-film/build), the shot list rewritten from the film's own shot table (kept privately), first frames.
2. time (unaided, then with the hand-fixed table as vocal_patches), bars, plan, lint, budget: the kit's own commands.
3. The film's real takes (the book's picks) placed on the song and cut on the NEW plan's bar-line cuts with the new
   cut module (ffmpeg only, no GPU); review boards with motion strips for that cut and for the shipped v24 cut;
   flash checks; what the new measures flag in v24.
4. The new plan's GPU needs as an ESTIMATE beside the first film's actual numbers (tools/replay_estimate.py).

Writes out/replay-first-film.md. Read-only on the first film's folder. `--quick` skips rendering and sheets.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(TOOLS))

from atomic_flix.cli import main as kit  # noqa: E402
from atomic_flix.cli.common import Film, write_json  # noqa: E402
from atomic_flix.cli.cut_steps import edit_spec  # noqa: E402
from atomic_flix.cli.shoot_steps import load_checked_book  # noqa: E402
from atomic_flix.cut import check_flashes, load_edit, render_cut  # noqa: E402
from atomic_flix.lint import preflight  # noqa: E402
from atomic_flix.review import make_review  # noqa: E402
import replay_estimate as est  # noqa: E402
import replay_steps as steps  # noqa: E402

FIRST_FILM_ENV = "FLIX_FIRST_FILM"
_ROOT = os.environ.get(FIRST_FILM_ENV, "").strip()
FILM_SRC = Path(_ROOT) / "films" / "the-girl-in-the-magic-tub" if _ROOT else None
BASELINE = Path(_ROOT) / "baseline.json" if _ROOT else None
FIXTURE = REPO / "fixtures" / "first-film"
SHOTS = REPO / "docs" / "private" / "first-film" / "first_film_shots.txt"
ENDS_AT = 278.67
STEMS = {"song": "song.wav", "voice": "lead.wav", "band": "rest.wav", "choir": "group.wav"}


def say(text: str) -> None:
    print(text, flush=True)


def build_project(args, work: Path, book: dict) -> Film:
    inputs = work / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    (inputs / "lyric.txt").write_text(steps.replay_lyric((args.film_src / "lyric.txt").read_text(encoding="utf-8")),
                                      encoding="utf-8")
    (inputs / "shots.txt").write_text(steps.replay_shots(args.shots.read_text(encoding="utf-8")), encoding="utf-8")
    root = work / "girl-in-the-magic-tub"
    command = ["new", root, "--name", "Girl In The Magic Tub (replay)", "--lyric", inputs / "lyric.txt",
               "--shots", inputs / "shots.txt", "--star", "Frankie", "--who", book["subject"]]
    for flag, name in STEMS.items():
        command += [f"--{flag}", FIXTURE / "audio" / name]
    assert kit([str(c) for c in command]) == 0
    film = Film.open(root)
    data = {**film.data, "frame": [1280, 704], "final_size": [1280, 720], "ends_at": ENDS_AT,
            "tone": "serious and soulful", "wardrobe": {"eighties": book["looks"]["eighties"]},
            "allow": ["Frankie"], "world": book.get("world")}
    for shot in book["shots"]:
        still = args.film_src / "frames" / f"{shot['id']}.png"
        if still.is_file():
            steps.link_or_copy(still, root / "stills" / f"{shot['id']}.png")
    return film.save(data)


def _agreement(film: Film, table: list[dict]) -> dict:
    """How the timed lines' starts agree with the hand-fixed table."""
    got = {row["id"]: row for row in json.loads(film.path("analysis/voice-lines.json").read_text("utf-8"))["lines"]}
    close = near = far = far_flagged = 0
    for row in table:
        mine = got.get(f"v{row['id'][1:]}") or {}
        off = abs(mine["start"] - row["t0"]) if row.get("t0") is not None and mine.get("start") is not None else None
        close += off is not None and off <= 0.10
        near += off is not None and off <= 0.25
        if off is None or off > 0.10:
            far += 1
            far_flagged += off is None or bool(mine.get("flags")) or mine.get("provenance") == "guess"
    return {"within_0_10": close, "within_0_25": near, "far": far, "far_flagged_or_guessed": far_flagged}


def timing(film: Film, table: list[dict], result: dict) -> Film:
    assert kit(["time", str(film.root)]) == 0
    result["timing"] = {"lines": len(table), "stem_only": _agreement(film, table)}
    steps.write_labels(FIXTURE / "build" / "words.json", film.path("analysis/word-labels.json"))
    assert kit(["time", str(film.root)]) == 0
    result["timing"]["with_labels"] = _agreement(film, table)
    film = film.save({**film.data, "vocal_patches": steps.vocal_patches(table)})
    assert kit(["time", str(film.root)]) == 0
    fixed = json.loads(film.path("analysis/voice-lines.json").read_text("utf-8"))["lines"]
    result["timing"]["with_fixes"] = sum(1 for line in fixed if line.get("provenance") == "fixed")
    return film


def bars(film: Film, beats: list[float], result: dict) -> Film:
    assert kit(["bars", str(film.root)]) == 0
    pulse = json.loads(film.path("analysis/pulse.json").read_text(encoding="utf-8"))
    ours = np.array(pulse["beats"])
    theirs = np.array(beats)
    nearest = np.array([ours[np.argmin(np.abs(ours - t))] for t in theirs])
    offsets = np.abs(nearest - theirs)
    # our beat j is the first film's beat i where j - i is the grids' index shift (the most common one)
    pairs = [(j, int(np.argmin(np.abs(theirs - t)))) for j, t in enumerate(ours)]
    shifts = [j - i for j, i in pairs if abs(theirs[i] - ours[j]) <= 0.03]
    shift = max(set(shifts), key=shifts.count)
    phase = shift % 4
    grounds = pulse.get("grounds") or {}
    result["bars"] = {"bpm": pulse["bpm"], "beats": len(ours), "fixture_beats": len(theirs),
                      "within_20ms": int(np.sum(offsets <= 0.020)), "median_ms": round(float(np.median(offsets)) * 1000, 1),
                      "p95_ms": round(float(np.percentile(offsets, 95)) * 1000, 1), "ruling": pulse.get("ruling"),
                      "guess_one_index": pulse.get("downbeat_slot"), "true_one_index": phase,
                      "clearance": grounds.get("clearance"), "stretches": grounds.get("spans_backing"),
                      "question": pulse.get("question")}
    film = film.save({**film.data, "downbeat_slot": phase})
    assert kit(["bars", str(film.root)]) == 0
    return film


def plan_and_lint(film: Film, book: dict, beats: list[float], result: dict) -> None:
    assert kit(["plan", str(film.root)]) == 0
    cuts = film.cuts()
    grids = {}
    for cut in cuts:
        grids[cut["grid"]] = grids.get(cut["grid"], 0) + 1
    result["plan"] = {"cuts": len(cuts), "grids": grids,
                      "new_counts": steps.counts_of([c["at"] for c in cuts[1:]], beats, 0),
                      "v24_counts": steps.counts_of([s["show"][0] for s in book["shots"][1:]], beats, 0)}
    kit(["lint", str(film.root)])
    verdict = preflight(load_checked_book(film))
    by_rule: dict[str, int] = {}
    for finding in verdict.findings:
        by_rule[f"{finding.level} {finding.rule}"] = by_rule.get(f"{finding.level} {finding.rule}", 0) + 1
    result["lint"] = {"blocked": verdict.blocked, "by_rule": dict(sorted(by_rule.items())),
                      "open_questions": len(verdict.open_review),
                      "stoppers": [f.line().splitlines()[0] for f in verdict.findings if f.level == "block"][:40]}
    assert kit(["budget", str(film.root)]) == 0
    result["budget"] = json.loads(film.path("plan/budget.json").read_text(encoding="utf-8"))


def place_takes(film: Film, args, book: dict, result: dict) -> None:
    lead = steps.Lead.load(FIXTURE / "audio" / "lead.wav")
    picks = book.get("picks") or {}
    rows, picked = [], {}
    for shot in book["shots"]:
        key = shot["id"]
        video, why = steps.picked_take(args.film_src / "takes", key, picks)
        aim = film.path(f"renders/{key}/r001.mp4")
        steps.link_or_copy(video, aim)
        span = float(shot.get("w0", shot["show"][0]))
        if shot.get("kind") == "sung":
            fit = steps.place_sung(lead, aim, span)
        else:
            fit = {"how": "slice", "slice_start": span, "vocal_spans": [], "map": [[span, 0.0]], "added_rests": [],
                   "offset": None}
        write_json(aim.with_suffix(".fit.json"), fit, "fit")
        picked[key] = 1
        costs = [p["cost"] for p in fit.get("vocal_spans", [])]
        rows.append({"key": key, "take": video.name, "why": why, "how": fit["how"],
                     "worst_cost": max(costs) if costs else None, "found_at": fit.get("found_at"), "span": span})
    film.save({**film.data, "picks": picked})
    sung = [r for r in rows if r["how"] == "sound"]
    worst = [r["worst_cost"] for r in sung if r["worst_cost"] is not None]
    moved = [r for r in sung if r["found_at"] is not None and abs(r["found_at"] - r["span"]) > 0.25]
    result["placing"] = {"takes": len(rows), "by_sound": len(sung), "worst_median": float(np.median(worst)),
                         "worst_max": float(np.max(worst)), "over_0_2": sum(1 for w in worst if w > 0.2),
                         "window_moved": [(r["key"], r["span"], r["found_at"]) for r in moved]}


def cut_and_review(film: Film, args, book: dict, beats: list[float], table: list[dict], result: dict) -> None:
    cuts_dir = film.path("cuts")
    spec, notes = edit_spec(film, cuts_dir, (1280, 720))
    edit_path = write_json(cuts_dir / "v01.edit.json", spec, "edit")
    out = cuts_dir / "v01.mp4"
    began = time.monotonic()
    rendered = render_cut(load_edit(edit_path), out, crf=20, x264_speed="veryfast", strict=False)
    write_json(cuts_dir / "v01.audit.json", {**rendered.audit.to_dict(), "audio": rendered.audio}, "audit")
    result["cut"] = {"seconds_to_render": round(time.monotonic() - began), "errors": rendered.audit.errors,
                     "warnings": rendered.audit.warnings, "audio": rendered.audio, "notes": notes}
    flash_new = check_flashes(out)
    began = time.monotonic()
    review_new = make_review(load_edit(edit_path), out, film.path("review/v01"))
    result["review_new"] = _flags(review_new, time.monotonic() - began)
    result["flash_new"] = flash_new.to_dict()
    v24 = args.film_src / "v24-cut.mp4"
    if not v24.is_file():
        result["v24"] = None
        return
    edit = steps.v24_edit(book, args.film_src / "takes", beats, table, ENDS_AT)
    began = time.monotonic()
    review_old = make_review(edit, v24, args.work / "review-v24")
    graded = args.film_src / "v24-graded.mp4"
    result["v24"] = {"review": _flags(review_old, time.monotonic() - began),
                     "flash_cut": check_flashes(v24).to_dict(),
                     "flash_graded": check_flashes(graded).to_dict() if graded.is_file() else None}


def _flags(review, seconds: float) -> dict:
    per_shot = {shot["key"]: shot["flags"] for shot in review.shots}
    kinds: dict[str, int] = {}
    for flags in per_shot.values():
        for flag in flags:
            word = ("still end" if "still at the end" in flag else "still start" if "still at the start" in flag
                    else "drift" if "drifts" in flag else "jump" if "jump" in flag
                    else "mouth not measured" if "mouth box" in flag else "other")
            kinds[word] = kinds.get(word, 0) + 1
    return {"folder": str(review.folder), "shots": len(review.shots), "flagged": sum(1 for f in per_shot.values() if f),
            "kinds": kinds, "per_shot": per_shot, "seconds": round(seconds)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--film-src", type=Path, default=FILM_SRC)
    parser.add_argument("--work", type=Path, default=REPO / "out" / "replay-first-film")
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--shots", type=Path, default=SHOTS, help="the first film's shot list in the kit's format")
    parser.add_argument("--report", type=Path, default=REPO / "out" / "replay-first-film.md")
    parser.add_argument("--quick", action="store_true", help="skip rendering the cut and the review boards")
    args = parser.parse_args(argv)
    missing = [flag for flag, value in (("--film-src", args.film_src), ("--baseline", args.baseline)) if value is None]
    if missing:
        parser.error(f"give {' and '.join(missing)} or set {FIRST_FILM_ENV} (docs/first-film-replay.md)")
    if not args.shots.is_file():
        parser.error(f"no shot list at {args.shots} (docs/first-film-replay.md)")
    if args.work.exists():
        import shutil
        shutil.rmtree(args.work)
    book = json.loads((args.film_src / "book.json").read_text(encoding="utf-8"))
    table = steps.table_lines(FIXTURE / "build")
    beats = json.loads((FIXTURE / "build" / "beats.json").read_text(encoding="utf-8"))["beats"]
    result: dict = {}
    film = build_project(args, args.work, book)
    say("project made; timing")
    film = timing(film, table, result)
    say(f"timing: {result['timing']}; bars")
    film = bars(film, beats, result)
    say(f"bars: {result['bars']}; plan and lint")
    plan_and_lint(film, book, beats, result)
    say("placing the takes")
    place_takes(film, args, book, result)
    result["v24_tails"] = steps.silent_tails(book, table, args.shots.read_text(encoding="utf-8"))
    new_tasks = Film.open(film.root).tasks()
    result["new_tails"] = [(key, task.get("exit_after_last")) for key, task in new_tasks.items()
                           if task.get("type") == "vocal"]
    if not args.quick:
        say("cutting and reviewing")
        cut_and_review(Film.open(film.root), args, book, beats, table, result)
    tasks = Film.open(film.root).tasks()
    cases = {name: est.estimate_case(tasks, name) for name in ("low", "central", "high")}
    est.projected_job_log(args.work / "estimate", cases["central"])
    result["compare"] = est.compare_report(args.work / "estimate", args.baseline)
    write_json(args.work / "replay.json", {k: v for k, v in result.items() if k != "compare"}, "replay")
    from replay_report import account
    args.report.write_text(account(result, cases, json.loads(args.baseline.read_text(encoding="utf-8"))),
                           encoding="utf-8")
    say(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
