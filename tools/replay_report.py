"""The Markdown report of the first film's replay (tools/replay_first_film.py)."""

from __future__ import annotations

import replay_estimate as est

P1_LIMIT = 1.0


def _counts(tally: dict) -> str:
    return ", ".join(f"count {k}: {v}" if k != "off" else f"off the beat: {v}" for k, v in tally.items())


def _section_inputs(r: dict) -> list[str]:
    t, b = r["timing"], r["bars"]
    stem, marked = t["stem_only"], t["with_labels"]
    return [
        "## 1. Timing and bars on the first film's stems", "",
        f"- `time` from the stem alone (no labels, no fixes): {stem['within_0_10']} of {t['lines']} line starts "
        f"within 0.10 s of the hand-fixed table, {stem['within_0_25']} within 0.25 s (roadmap: 30 within 0.25 s).",
        f"- `time` with the first film's word labels, no fixes: {marked['within_0_10']} of {t['lines']} within "
        f"0.10 s, {marked['within_0_25']} within 0.25 s; of the {marked['far']} further than 0.10 s off, "
        f"{marked['far_flagged_or_guessed']} are flagged or marked as a guess (roadmap: at least 40 within 0.10 s, "
        "every line further off flagged).",
        f"- With the table as `vocal_patches`: {t['with_fixes']} of {t['lines']} lines fixed (roadmap: 56 of 56).",
        f"- `bars` (no drum stem; the band stem): {b['bpm']} BPM, {b['beats']} beats; {b['within_20ms']} of "
        f"{b['fixture_beats']} of the first film's beats have one of ours within 20 ms (median {b['median_ms']} ms, "
        f"95th percentile {b['p95_ms']} ms).",
        f"- Bar one: status `{b['ruling']}`, margin {b['clearance']}, stretches agreeing {b['stretches']}; the stage "
        f"guessed index {b['guess_one_index']}, the known one is {b['true_one_index']} on our grid (phase 0 of the "
        "first film's grid in fixtures TRUTH.txt, from the prototype; not yet confirmed by ear). "
        + ("The stage asks for the click, as the spec says it must on a tie." if b["ruling"] != "decided" else
           "The spec's prototype found a 0-or-2 tie here; this stage decided, so the click by ear still settles it."),
        f"  Its question: {b['question']}", "",
    ]


def _section_plan(r: dict) -> list[str]:
    p, lint, budget = r["plan"], r["lint"], r["budget"]
    lines = [
        "## 2. Plan, lint and budget", "",
        f"- `plan`: {p['cuts']} cuts; grids {p['grids']}.",
        f"- Cuts after the first, by count of the bar on the first film's true grid (one = count 1):",
        f"  - new plan: {_counts(p['new_counts'])}",
        f"  - shipped v24: {_counts(p['v24_counts'])}",
        f"- `lint`: {'BLOCKED' if lint['blocked'] else 'clear'}; {lint['open_questions']} picture questions "
        "unanswered (no judge records were carried over, so every still blocks until judged).",
        "  Findings by rule: " + ", ".join(f"{k} x{v}" for k, v in lint["by_rule"].items()) + ".",
        f"- `budget`, the first batch only (4 takes a shot): {budget['takes']} takes at "
        f"{budget['size'][0]}x{budget['size'][1]}, about {budget['gpu_hours']:.1f} GPU hours ({budget['basis']}).",
        "- Lint's L006, L091 and L127 blocks are the gates (song fingerprint, the look, the hours), not recorded in a "
        "replay; L010 and the questions are the judge records; CM1, W1 and WIN1 are findings on the first film's "
        "own shot list.", "",
    ]
    return lines


def _section_tails(r: dict) -> list[str]:
    old = [(k, s) for k, s in r["v24_tails"] if s > P1_LIMIT]
    new = [(k, s) for k, s in r["new_tails"] if s is not None and s > P1_LIMIT]
    return [
        "## 3. Silent tails (a vocal shot on screen after her last sound)", "",
        f"- Shipped v24: {len(old)} of {len(r['v24_tails'])} vocal shots stay on more than {P1_LIMIT:.1f} s after her "
        "last sound: " + (", ".join(f"{k} {s:.1f} s" for k, s in old) or "none") + ".",
        f"- New plan: {len(new)} of {len(r['new_tails'])}: " + (", ".join(f"{k} {s:.1f} s" for k, s in new) or "none")
        + " (lint blocks any pinned shot over 1.0 s, rule P1).", "",
    ]


def _review_lines(title: str, review: dict) -> list[str]:
    lines = [f"- {title}: {review['flagged']} of {review['shots']} shots flagged ("
             + ", ".join(f"{k} {v}" for k, v in sorted(review["kinds"].items())) + f"); sheets in `{review['folder']}`."]
    for key, flags in review["per_shot"].items():
        real = [f for f in flags if "mouth box" not in f]
        if real:
            lines.append(f"  - {key}: " + "; ".join(real))
    return lines


def _section_cut(r: dict) -> list[str]:
    if "cut" not in r:
        return ["## 4. The cut and the review boards", "", "Skipped (`--quick`).", ""]
    c, placing = r["cut"], r["placing"]
    lines = [
        "## 4. The first film's takes cut on the new plan", "",
        f"- Placing: {placing['takes']} picked takes; {placing['by_sound']} sung takes placed by sound, worst phrase "
        f"cost median {placing['worst_median']:.3f}, max {placing['worst_max']:.3f}, {placing['over_0_2']} over 0.2. "
        f"Plates run at 1x from their window in the book.",
        f"- Rendered `cuts/v01.mp4` at 1280x720 in {c['seconds_to_render']} s (CPU, ffmpeg). Audio: "
        + (f"{c['audio'].get('lufs_after')} LUFS, peak {c['audio'].get('peak_after_db')} dBFS." if c["audio"] else "none."),
        f"- The cut audit found {len(c['errors'])} errors and {len(c['warnings'])} warnings (rendered anyway, "
        "strict off, to measure). By kind:",
    ]
    kinds = {"slower than 1x": [], "first two frames": [], "jump cut": [], "other": []}
    for error in c["errors"]:
        kind = next((k for k in kinds if k in error), "other")
        kinds[kind].append(error)
    lines += [
        f"  - {len(kinds['first two frames'])} shots where the old take, made for the old window, does not reach back "
        "to the new plan's cut: these need a new render for the new plan ("
        + ", ".join(e.split(' at ')[0] for e in kinds["first two frames"]) + ").",
        f"  - {len(kinds['slower than 1x'])} sung shots played slower than 1x beyond the placement's tolerance"
        + (" (" + "; ".join(e.split(" at ")[0] + " " + e.split("(rate ")[1].split(";")[0]
                            for e in kinds["slower than 1x"]) + ")" if kinds["slower than 1x"] else "")
        + ". Rates are read over 1, 2 and 4 s windows and the whole shot, against 2 x 0.02 s of placement uncertainty "
        "per window (`atomic_flix.cut.rate`); the point-to-point slopes of a placement map are noise, not speed.",
        f"  - {len(kinds['jump cut'])} jump cuts (one setup, crop sizes under 20 % apart, the rule lint's C1 uses)"
        + (": " + "; ".join(e.split(": ")[1].split(" side by side")[0] for e in kinds["jump cut"]) if kinds["jump cut"]
           else "") + ".",
    ]
    lines += [f"  - other: {e}" for e in kinds["other"]]
    lines += _review_lines("Review of the new cut", r["review_new"])
    lines.append(f"- Flash check of the new cut: {'PASS' if r['flash_new']['passed'] else 'FAIL'}, "
                 f"{r['flash_new']['flash_count']} flashes, at most {r['flash_new']['worst_count']} in a second.")
    return lines + [""]


def _section_v24(r: dict) -> list[str]:
    v24 = r.get("v24")
    if not v24:
        return []
    lines = ["## 5. What the new measures flag in the shipped v24 cut", "",
             "The first film's sheets (`sheets-v20/`, 46 files) were one contact sheet of eight frames per shot: no "
             "motion strip, no first and last half second, no measures. v23 and v24 had no flash check.", ""]
    lines += _review_lines("New review of v24-cut.mp4", v24["review"])
    lines += ["- Reading these: shot spans are the book's `show` times (the shipped cut list); the drift measure is "
              "the whole picture's shift, so a big subject moving through a locked frame (the walking tub in N08, "
              "N17) reads as drift too, and needs eyes on the motion strip."]
    long_tails = [k for k, s in r["v24_tails"] if s > P1_LIMIT]
    still_ends = [k for k, flags in v24["review"]["per_shot"].items() if any("still at the end" in f for f in flags)]
    lines.append(f"- Silent tails against still ends: {len(long_tails)} vocal shots outstay her last sound by over "
                 f"{P1_LIMIT:.0f} s ({', '.join(long_tails) or 'none'}); the motion measure finds a still end in "
                 f"{', '.join(still_ends) or 'none of them'}, so in the others the pinned take kept moving to the cut.")
    for name, key in (("v24-cut.mp4", "flash_cut"), ("v24-graded.mp4", "flash_graded")):
        flash = v24.get(key)
        if flash:
            lines.append(f"- Flash check of {name}: {'PASS' if flash['passed'] else 'FAIL'}, {flash['flash_count']} "
                         f"flashes, at most {flash['worst_count']} in one second (limit 3).")
    return lines + [""]


def _section_estimate(cases: dict, baseline: dict, compare: str) -> list[str]:
    takes = baseline["takes"]
    gpu = baseline["gpu"]["by_kind_of_job_seconds"]
    c = cases["central"]
    low, high = cases["low"], cases["high"]
    rows = [
        ("Sung takes", f"{takes['sung']['value']}", f"{c.sung_takes} ({low.sung_takes} to {high.sung_takes})"),
        ("Plate takes", f"{takes['plate']['value']}", f"{c.plate_takes} ({low.plate_takes} to {high.plate_takes})"),
        ("Takes in all", f"{takes['rendered_total']['value']}",
         f"{c.sung_takes + c.plate_takes} ({low.sung_takes + low.plate_takes} to {high.sung_takes + high.plate_takes})"),
        ("GPU hours, logged jobs", f"{gpu['total']['hours']}", f"{c.gpu_hours:.1f} ({low.gpu_hours:.1f} to "
                                                               f"{high.gpu_hours:.1f})"),
        ("GPU hours with lab work", "about 77 (59.5 logged + 16.7 lab)", "not estimated (lab work)"),
        ("Rendered seconds per finished second", f"{baseline['rendered_to_finished']['ratio']['value']}",
         f"{c.video_seconds / 278.67:.1f}"),
        ("Full passes over every sung shot", "8", f"{sum(1 for v in est.SUNG_PASSES.values() if not v)}"),
        ("Numbered builds", f"{baseline['builds_and_reviews']['numbered_builds']['value']}",
         f"{c.builds} ({low.builds} to {high.builds})"),
        ("Model-call cost, USD", f"{baseline['model_calls']['cost_usd_list_price']['value']}",
         "not estimated (target: under 289)"),
    ]
    lines = ["## 6. First film actual against the new kit (ESTIMATE)", "",
             "**Every number in the right-hand column is an estimate, not a measurement.** Central case, with the low "
             "and high cases in brackets.", "",
             "| Metric | First film actual | New kit estimate |", "|---|---|---|"]
    lines += [f"| {a} | {b} | {e} |" for a, b, e in rows]
    lines += ["", "Assumptions:", ""] + est.assumptions_text() + [""]
    lines += ["What cannot be known without rendering: whether first-pass takes hold her face and the mouth as well as "
              "the picked first-film takes did; how many re-rolls taste and identity checks still cost; the GPU time "
              "of the plates the new plan lengthens or shortens; the lab work behind the cold open.", "",
              "The kit's own comparison, run on a film folder holding the central case's projected ledger:", ""]
    body = compare.split("\n", 2)[2] if compare.count("\n") > 2 else compare
    return lines + ["> " + line if line else ">" for line in body.splitlines()] + [""]


def account(r: dict, cases: dict, baseline: dict) -> str:
    lines = ["# Replay of the first film through the new kit", "",
             "The Girl In The Magic Tub, replayed on the CPU from its own stems, line table, beat grid, shot list, "
             "first frames and picked takes. No GPU was used. Made by `tools/replay_first_film.py`.", ""]
    lines += _section_inputs(r) + _section_plan(r) + _section_tails(r) + _section_cut(r) + _section_v24(r)
    lines += _section_estimate(cases, baseline, r["compare"])
    return "\n".join(lines) + "\n"
