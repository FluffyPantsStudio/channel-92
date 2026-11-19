"""The GPU plan the new kit would run for the first film, as an ESTIMATE, set against what the first film did.

Nothing here is measured on new renders. Each assumption is a named constant with the evidence it rests on
(baseline.json sections, the lessons ledger); the report prints them all, and a low and a high case beside the
central one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atomic_flix.formats import tag
from atomic_flix.compare import compare_film, load_baseline, measure_film, render_report
from atomic_flix.project import create_project, set_record

FIRST_PASS_TAKES = 4          # the kit's default takes per shot (plan.estimate.DEFAULT_TAKES)
# The eight full passes over all 25 sung shots (baseline sung_reshoots) and whether the kit stops their cause
# before any GPU time. True: lint or a gate blocks it; False: no rule can see it.
SUNG_PASSES = {
    "v1 first pass": False,                                    # the pass itself
    "round 2, framing and hands": True,                        # F1 framing phrase, H1 named hands
    "round 3, framing and hands": True,                        # same
    "v4 bar-timed windows (downbeat a beat late)": True,       # L060 bar one confirmed by ear, cuts on one or three
    "v5 new collar look": True,                                # gate 3 before any batch of more than 3 (L091)
    "v7 3.5 s tail": True,                                     # P1 pinned exit within 1.0 s of her last sound
    "v7 moving close": False,                                  # a change of the person's mind about the shot
    "v8 22-shot reshoot (grin and laugh)": True,               # H2, L014 neutral still, L050 soft copy heard
}
# Targeted re-rolls after the full passes: the first film ran picker rounds 2 to 9 over 4 to 18 shots each
# (baseline sung_reshoots). Assumed: a share of sung shots still needs one re-roll round for what only eyes see
# (identity, mouth sync, gestures).
SUNG_REROLL_SHARE = {"low": 0.25, "central": 0.5, "high": 1.0}
# Plates: 13.6 takes a shot on the first film. Moving cameras without an end still (CM1), locked plates that invent
# cuts (P3), people appearing (L044) and grain (K1) are now blocked; motion the model will not make (the walking
# tub, 36 takes) is not.
PLATE_REROLL_SHARE = {"low": 0.25, "central": 0.5, "high": 1.0}
HARD_PLATES = 2               # shots like N08 (walking tub) and N19 that cost 25 or more takes each
HARD_PLATE_EXTRA = {"low": 8, "central": 16, "high": 32}
# Stills, edits and model tests are not changed by this kit: the first film's hours are carried over.
STILL_HOURS = 5571 / 3600     # baseline gpu.by_kind_of_job_seconds.book_stills_qwen_edit
TEST_HOURS = 1150 / 3600      # baseline gpu.by_kind_of_job_seconds.video_model_test_fasth3
RATES = {"sung_pinned": 28.1, "sung_soft_pin": 26.9, "sung_unpinned": 14.6, "plate_pinned": 24.8,
         "plate_unpinned": 27.7}   # baseline gpu.gpu_seconds_per_video_second (GPU s per video s, timed rows)
BUILDS = {"low": 4, "central": 6, "high": 10}   # v1 plus cold-review fix rounds plus the person's rounds


def rate_name(task: dict) -> str:
    pin = task.get("pin") or "none"
    if task.get("type") == "vocal":
        return {"full": "sung_pinned", "soft": "sung_soft_pin"}.get(pin, "sung_unpinned")
    return "plate_pinned" if pin == "full" else "plate_unpinned"


@dataclass(frozen=True)
class Case:
    name: str
    sung_takes: int
    plate_takes: int
    gpu_hours_sung: float
    gpu_hours_plate: float
    video_seconds: float
    builds: int
    rows: list[dict]

    @property
    def gpu_hours(self) -> float:
        return self.gpu_hours_sung + self.gpu_hours_plate + STILL_HOURS + TEST_HOURS


def estimate_case(tasks: dict[str, dict], case: str) -> Case:
    """Takes and GPU hours per shot of the new plan under one case's assumptions."""
    full_passes = sum(1 for stopped in SUNG_PASSES.values() if not stopped)
    sung = [key for key, task in tasks.items() if task.get("type") == "vocal"]
    plates = [key for key in tasks if key not in sung]
    rows = []
    for key, task in tasks.items():
        if key in sung:
            takes = FIRST_PASS_TAKES * full_passes + FIRST_PASS_TAKES * SUNG_REROLL_SHARE[case]
        else:
            takes = FIRST_PASS_TAKES * (1 + PLATE_REROLL_SHARE[case])
        rate = RATES[rate_name(task)]
        rows.append({"key": key, "kind": "vocal" if key in sung else "cutaway", "takes": takes,
                     "seconds": int(task["seconds"]), "rate": rate, "busy_s": takes * int(task["seconds"]) * rate})
    extra_plate = HARD_PLATES * HARD_PLATE_EXTRA[case]
    plate_seconds = sum(r["seconds"] for r in rows if r["kind"] == "cutaway") / max(1, len(plates))
    plate_rate = sum(r["rate"] for r in rows if r["kind"] == "cutaway") / max(1, len(plates))
    rows.append({"key": "hard plates", "kind": "cutaway", "takes": extra_plate, "seconds": plate_seconds,
                 "rate": plate_rate, "busy_s": extra_plate * plate_seconds * plate_rate})
    sung_rows = [r for r in rows if r["kind"] == "vocal"]
    plate_rows = [r for r in rows if r["kind"] == "cutaway"]
    return Case(name=case, sung_takes=round(sum(r["takes"] for r in sung_rows)),
                plate_takes=round(sum(r["takes"] for r in plate_rows)),
                gpu_hours_sung=sum(r["busy_s"] for r in sung_rows) / 3600,
                gpu_hours_plate=sum(r["busy_s"] for r in plate_rows) / 3600,
                video_seconds=sum(r["takes"] * r["seconds"] for r in rows), builds=BUILDS[case], rows=rows)


def projected_job_log(folder: Path, case: Case) -> None:
    """A film folder whose ledger holds the central case's jobs, so the kit's own comparison can read it."""
    film = create_project(folder.parent, folder.name, "First film replay, ESTIMATE", created="2026-11-20T09:00:00Z")
    clock = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)
    lines = []
    for row in case.rows:
        whole = int(round(row["takes"]))
        for n in range(1, whole + 1):
            seconds = row["seconds"] * row["rate"]
            started, clock = clock, clock + timedelta(seconds=seconds)
            lines.append({"format": tag("job-log-row"), "job_id": f"{row['key']}-r{n:03d}", "kind": row["kind"], "shot": row["key"],
                          "host": "estimate", "seed": None, "gpu_seconds": round(seconds, 1),
                          "started": started.isoformat(), "finished": clock.isoformat(), "state": "done",
                          "video_seconds": row["seconds"]})
    for kind, hours in (("still", STILL_HOURS), ("test", TEST_HOURS)):
        started, clock = clock, clock + timedelta(hours=hours)
        lines.append({"format": tag("job-log-row"), "job_id": f"{kind}-carried-over", "kind": kind, "shot": None, "host": "estimate", "seed": None,
                      "gpu_seconds": round(hours * 3600, 1), "started": started.isoformat(),
                      "finished": clock.isoformat(), "state": "done"})
    film.job_log.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    full_passes = sum(1 for stopped in SUNG_PASSES.values() if not stopped)   # counted as the baseline counts them
    set_record(film, finished_seconds=278.67, reshoot_passes=full_passes)
    for number in range(1, case.builds + 1):
        (film.root / "cuts" / f"v{number:02d}.mp4").write_bytes(b"")


def compare_report(folder: Path, baseline: Path) -> str:
    rows = compare_film(load_baseline(baseline), measure_film(folder))
    text = render_report(rows, film_name="ESTIMATE: the first film replayed with the new kit",
                         baseline_name="Girl In The Magic Tub (actual)")
    return text.replace("This film", "New kit (estimate)")


def assumptions_text() -> list[str]:
    stopped = [name for name, yes in SUNG_PASSES.items() if yes]
    kept = [name for name, yes in SUNG_PASSES.items() if not yes]
    return [
        f"- First pass: {FIRST_PASS_TAKES} takes a shot (the kit's default).",
        f"- Of the first film's 8 full sung passes, {len(stopped)} had causes lint or a gate now blocks before any "
        f"GPU time: {'; '.join(stopped)}. Kept: {'; '.join(kept)}.",
        "- Targeted sung re-rolls (one round of 4 takes) for a share of shots: "
        + ", ".join(f"{k} {v:.0%}" for k, v in SUNG_REROLL_SHARE.items()) + ".",
        "- Plates: 4 takes, plus one re-roll round of 4 for a share of shots ("
        + ", ".join(f"{k} {v:.0%}" for k, v in PLATE_REROLL_SHARE.items())
        + f"), plus {HARD_PLATES} hard plates (like the walking tub) at "
        + ", ".join(f"{k} {v}" for k, v in HARD_PLATE_EXTRA.items()) + " extra takes each.",
        "- GPU seconds per video second: the first film's timed rates by kind and pin (baseline): "
        + ", ".join(f"{k} {v}" for k, v in RATES.items()) + "; render lengths are the new plan's slices.",
        f"- Stills and model tests carried over unchanged: {STILL_HOURS:.2f} h and {TEST_HOURS:.2f} h.",
        "- Builds: " + ", ".join(f"{k} {v}" for k, v in BUILDS.items())
        + " (v1 after a clean cold review, then the person's rounds). Not measurable without making the film.",
        "- Lab work outside the job log (the cold open, about 16.7 h) and model-call cost are not estimated.",
    ]
