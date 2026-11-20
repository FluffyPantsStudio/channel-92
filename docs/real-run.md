# Real run: the runner and placing against the local ComfyUI (2026-11-19)

Names in this record (keys in the logs and sidecars, verbs, folders) are written as the kit names them since
the renames of 2026-11-19 (the maintainers' renames table, kept privately in `docs/private/`), not as they were spelt on the day.

The first run of the new kit on real GPUs: `ping`, the gate-5 report, a small still as a smoke test, and one sung
take of the first film's S13 made end to end with the new kit and placed by sound. Hosts: two RTX 3090s,
`127.0.0.1:8188` (GPU 0) and `127.0.0.1:8189` (GPU 1). Every GPU job ran on 8189; 8188 was left alone (it held about
10 GB of VRAM for something that was not ours). No queue was cleared and no ComfyUI was stopped or restarted.
Work folders are under `out/real-run/` (git-ignored).

## 1. Ping and the gate-5 report

`atomic-flix runner ping` (0.5 s, exit 0): both hosts answer as RTX 3090, 24 GB; ffmpeg and ffprobe found; Python
in UTF-8 mode; commit headroom 30 GB (49.5 GB committed of a 79.9 GB limit).

Gate 5 on the first-film project (184 takes, all 49 shots): `atomic-flix budget` with an empty machine log gave
9.81 GPU hours at the first film's rates. After the one measured LTX take below, the same command gave 5.77 GPU
hours at 15.8 GPU s per video s (see problem 7). For 25 sung takes of 9 s from that one row: 0.99 GPU hours.
`atomic-flix runner budget` on the planned S13 job said "no measured renders" before the take (it has no fallback
to the first film's rates; the film verb has).

## 2. Smoke test: one still on GPU 1

Graph: our own `still.json` (Qwen image edit 2511, fp8, 20 steps), copied into `out/real-run/smoke/graphs/`
with a sidecar `{"kind": "still", "needs": ["wording", "image1"], "commit_gb": 20}`. Input: the S13 still. Size
640x352. Planned and run with `atomic-flix runner plan` and `atomic-flix runner shoot` (the film verb `shoot`
builds render requests from a film's plan, so it cannot carry a still job).

| What | Result |
|---|---|
| Refusal, floor 40 GB (simulated: headroom was 29.7 GB) | `refused to start: commit headroom 29.7 GB is under the floor of 40 GB`; exit 1; nothing uploaded or queued; job stays `planned` |
| Run, floor 22 GB | queued on 8189, done in 78.8 GPU s (cold model load included), 81.6 s wall, 0 s in ComfyUI's queue, `renders/T01/r001.png` |
| Same command again | no new submission, queue empty, still one log line (resumability holds) |

Machine log row (`out/real-run/log/jobs.jsonl`, written before the still fix in section 5, so `video_s` is wrong):

```json
{"time": "2026-11-19T03:04:02", "film": "smoke", "key": "T01", "n": 1, "host": "127.0.0.1:8189", "gpu": "cuda:0 NVIDIA GeForce RTX 3090 : cudaMallocAsync", "graph": "still.json", "graph_digest": "1e0545ff239a", "width": 640, "height": 352, "frames": 9, "fps": 24, "video_s": 0.375, "seed": 2849604008, "waited_s": 0.0, "busy_s": 78.8, "wall_s": 81.6, "ok": true, "error": null}
```

Film ledger (`out/real-run/smoke/job-log.jsonl`), read clean by `compare.ledger.read_job_log`:

```json
{"job_id": "T01-r001", "kind": "still", "shot": "T01", "host": "127.0.0.1:8189", "seed": 2849604008, "gpu_seconds": null, "started": "2026-11-19T08:02:40.771+00:00", "finished": null, "status": "running", "video_seconds": null}
{"job_id": "T01-r001", "kind": "still", "shot": "T01", "host": "127.0.0.1:8189", "seed": 2849604008, "gpu_seconds": 78.8, "started": "2026-11-19T08:02:40.811+00:00", "finished": "2026-11-19T08:03:59.589+00:00", "status": "done", "video_seconds": 0.375}
```

Commit while the still ran: headroom 29.7 GB before, 7.5 GB at the load, and 8.9 GB after it finished, because the
model stays resident in that ComfyUI. The still alone took about 21 GB of commit and kept it.

## 3. The project and the prompt

`out/real-run/films/s13-real`: `atomic-flix new` with the first film's stems (fixture), lyric and full shot list
(the replay's, `out/replay-first-film/inputs/`), film fields as the replay sets them (frame, tone, outfit,
vocal_patches, downbeat_slot 3, ends_at), `analysis/` copied from the replay project (same kit), and the S13 still from
`canon/<singer>/singing/stills/S13.png`. A shot list holding S13 alone does not work: the first shot always starts at
0, so S13 became 0 to 278.67 s with a 15 s render. With the whole list, `atomic-flix plan` gives the same S13 task as
the replay: slice 145.6 s for 6 s, gate 146.23 to 150.74, full pin, soft copy `plan/S13.voice-soft.wav`.

Lint on S13: no prompt rule fires. Its findings are WARN C1 (S12 and S13 on one setup at 0.8 and 0.85), WARN G1 (the
gate opens at -31.2 dB, into sound), and, once the still has a judge record, BLOCK L017 and L022 (the test film has
no identity reference or body panel for the singer). The judge record (`stills/S13.json`) is mine, made at 1280x704 by
looking at the picture (no hands, mouth closed and unsmiling, eyes on us, flat areas clean); it is not a cold judge's.
The film as a whole stays blocked (45 shots without stills, gates 2, 3 and 5 unanswered), so the film verb `shoot`
would refuse; the take was shot through `atomic-flix runner`, which does not run lint. No gate answer was recorded.

The prompt sent, against the person's pick (first film, take 22):

| | Old (take 22) | New kit |
|---|---|---|
| Length | 10 s, 241 frames | 6 s, 145 frames (the new plan's slice) |
| Audio | `build/quiet/S13.wav`, 9 s from 145.6 | `plan/S13.voice-soft.wav`, 6 s from 145.6, gated 146.23 to 150.74 |
| Turning away | not named | "she never turns away" (the recipe's one helpful negative) |
| Swaying | "swaying gently, never stopping" | "swaying gently and continuously" |
| Camera | "locked off: it does not move and does not zoom" plus a closing "Camera: Locked-off camera: no zoom, no push-in, no pull-back. One continuous shot; no cuts." | "locked off and keeps one size"; no closing camera line |
| Timeline | three steps: 0-1s lips closed, 1-6s the line, 6-10s rest swaying | one step: "0-6s: her lips together at first, then she sings ...; then she keeps swaying gently with the music, her eyes on us." |
| Look line | "...; natural anatomy. Only one Nova appears. No on-screen text." | "Nova looks just as she does in the first frame, ..., with a natural body." (no "only one Nova", no "no on-screen text") |

## 4. The S13 take

Planned with the old take's seed through the batch file (`"seed": 2673691454`, a field added in section 5), graph
our own `sung-ltx23-pinned.json` copied with the sidecar `{"needs": ["wording", "opening_still", "audio"],
"frame_multiple": 8, "commit_gb": 40}`, on 8189 (GPU 1, the free card).

1. First attempt, floor 25 GB: refused for real. The smoke still was still resident, headroom 8.3 GB.
2. I released our own still model on 8189 with ComfyUI's `/free` (`unload_models`), outside the kit, after checking
   its queue was empty. Headroom back to 29 GB.
3. Second attempt: queued on 8189, done in **95.7 GPU s** (cold load included), 96.7 s wall, 0 s queued. Output
   `renders/S13/r001.mp4`: 145 frames, 6.04 s, 48 kHz stereo sound.
4. Same command again: "nothing waiting", no submission.
5. Released the LTX model the same way afterwards (headroom 16 GB with it resident, 30 GB after).

Machine log row:

```json
{"time": "2026-11-19T03:10:04", "film": "s13-real", "key": "S13", "n": 1, "host": "127.0.0.1:8189", "gpu": "cuda:0 NVIDIA GeForce RTX 3090 : cudaMallocAsync", "graph": "sung-ltx23-pinned.json", "graph_digest": "db81bf110a61", "width": 1280, "height": 704, "frames": 145, "fps": 24, "video_s": 6.042, "seed": 2673691454, "waited_s": 0.0, "busy_s": 95.7, "wall_s": 96.7, "ok": true, "error": null}
```

Film ledger:

```json
{"job_id": "S13-r001", "kind": "vocal", "shot": "S13", "host": "127.0.0.1:8189", "seed": 2673691454, "gpu_seconds": null, "started": "2026-11-19T08:08:27.262+00:00", "finished": null, "status": "running", "video_seconds": null}
{"job_id": "S13-r001", "kind": "vocal", "shot": "S13", "host": "127.0.0.1:8189", "seed": 2673691454, "gpu_seconds": 95.7, "started": "2026-11-19T08:08:27.296+00:00", "finished": "2026-11-19T08:10:02.996+00:00", "status": "done", "video_seconds": 6.042}
```

Commit during the take: 28.5 GB headroom before; 2.6 GB from about 30 s in; **1.0 GB at the lowest** (78.9 of
79.9 GB committed, near the end); 16 GB after it finished.

Placing (`atomic-flix place`, 0.6 s): one phrase, 0.70 to 5.14 s of the slice, **cost 0.020**, rate 0.999, offset
-0.05 s, no inserted pauses, no flags from `check_fit`. Against the old pick:

| Take | Placer | Sent audio | Cost | Offset |
|---|---|---|---|---|
| Old pick, take 22 | old kit (`take-22.sync.json`) | its window | 0.028 | +0.68 s |
| Old pick, take 22 | new kit | `build/quiet/S13.wav` | 0.025 | +0.68 s |
| Old pick, take 22 | new kit | new soft copy | 0.027 | +0.68 s |
| New take r001 | new kit | new soft copy | **0.020** | -0.05 s |

So the new take is as tight to its audio as the person's pick, slightly tighter, and sings almost on time where the
old pick sang 0.68 s late inside its window. Three frames (0.5, 3.0 and 5.8 s, `out/real-run/s13-r001-strip.png`)
show her face and size holding, with her mouth open and eyes closed at 0.5 s, before the line starts at 0.7 s, and
a small closed-mouth smile on the last frame. Nobody has judged the take; it is not a pick.

## 5. Bugs fixed (tests first, `tests/runner/test_runner_real_run.py`, 17 tests; 16 red before the change, the 17th a guard that seeds still differ when none is given)

1. **No fixed seed.** `Request` had no seed, so a take could not be re-rendered with its seed. `Request.seed` (and
   `"seed"` in a batch file) now carries one; a seed that is not a whole number from 0 to 2^32-1 (or a bool, or
   text) is refused before any job is written.
2. **No refusal on low headroom.** The load gate holds only a second load it knows of; a first heavy load always
   started, whatever another ComfyUI or program had committed. `Runner(min_headroom_gb=...)` and
   `runner shoot --min-headroom GB` now refuse to start a heavy job (`commit_gb` over 0) while headroom is under the
   floor or unknown; the job stays planned, the run stops taking work, the summary says `refused`, exit 1. Checked
   before every heavy job, so a drop mid-batch stops the next one.
3. **A still counted as video.** Stills logged `video_s` as frames over fps (0.375 s), so "GPU s per video s" read
   210 for the smoke still and would pull estimates. `video_s` (log) and `video_seconds` (film ledger) are now null
   for a still. `summarize` now counts a still's GPU time in GPU hours (before, a job without video seconds dropped
   out of the hours altogether) but not in the rate.
4. **An empty run printed a nonsense estimate** ("0 takes at no size"). It now says "nothing waiting".

`tests/runner`: 88 passed, 1 skipped. Full suite at the end: 863 passed, 17 skipped.

## 6. Problems not fixed (other packages, or decisions for the integration builder)

1. **A load stays resident and keeps its commit.** The still kept about 21 GB and the LTX model about 12 GB after
   their jobs. The client has no free call on purpose, so after any job the next heavy job may be refused (as
   happened) and the machine sits near its limit. Needed: a decision on whether the runner may release its own
   loads (`/free` on a host with an empty queue, after its own job), or a documented manual step.
2. **One LTX load nearly hit the commit limit.** From 28.5 GB headroom the take left 1.0 GB. The floor of 25 GB I
   used was too low; the measured LTX peak is about 28 GB. Recommendation: LTX sidecars `commit_gb` 28 to 30 and a
   floor of `commit_gb` plus 5 GB by default (that floor would have refused this run at 28.5 GB).
3. **The film verbs cannot pass a seed or a floor.** `atomic-flix shoot` (cli/shoot_steps.py) builds its own
   requests and runner; it needs `--min-headroom` (passed to `Runner`) and, for re-renders, a seed per take.
4. **The film verb `shoot` cannot carry stills.** Stills went through `atomic-flix runner`; a still verb is missing.
5. **`Request.seconds` is required for a still.** I gave 0.04; a still should need no length.
6. **Two default log places.** `atomic-flix runner` writes `log/jobs.jsonl` under the working folder, the film verbs
   beside the film folders. One machine log was meant.
7. **The budget swaps the first film's rates for one measured row.** After one LTX take, `atomic-flix budget` priced
   every shot from it, plates included ("other graphs at this size, 84 jobs"), and the cold-load take made the rate
   15.8 GPU s per video s against the first film's 13.2 for this shot. Needs a minimum count of rows per graph
   before the log replaces the first film's rates, and no cross-graph fallback for a different kind of job.
8. **Machine log times have no offset** (local time), while the film ledger is UTC.
9. **Lint and the reused still.** The single-shot film is impossible (first shot from 0), and a reused canon still
   blocks on L017 and L022 until the film names the singer's references; the first film's references are outside what
   this run could read.
