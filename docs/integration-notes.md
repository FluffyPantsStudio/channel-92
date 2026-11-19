# Integration notes (collected from builder reports; for the integration builder)

From the project, gates and compare builder (2026-11-19):

- The ledger is `<film>/job-log.jsonl`, one JSON object per line: `job_id, kind, shot, host, seed, gpu_seconds,
  started, finished, state`; state is `planned`, `running`, `done` or `errored`; the last line per `job_id` wins.
  Documented in `docs/job-log.md`. The runner must write exactly this.
- The runner should add an optional `video_seconds` field. Without it the rendered-to-finished ratio reads unknown.
- The runner should call `require_gate(film, "spend")` before any batch (gate 5).
- `PROVENANCE.md` needs an entry for the project, gates and compare builder: it read core spec section 8, the roadmap,
  the lessons ledger, the baseline, our own working notes and two of our statistics scripts, the first film's notes
  and its folder listing (the full list is in the maintainers' private provenance record). The old kit was not opened.
- Its tests were written before the code but never run red; re-run the suite and, where a test cannot fail, strengthen it.
- Targets in `compare`: total GPU hours at most 35, cost under half of $578, driver median tokens under 150,000, every
  other metric below the first film.

From the runner and placing builder:

- Runner verbs: `ping`, `plan`, `budget`, `shoot`, `progress`. The client has no interrupt, free or clear calls on purpose.
- Soft copy: the quieter copy restores the voiced level first, then -8 dB (a plain -8 only lands 8 dB under on quiet input).
- Control-video sizes must be multiples of 128 (both halves of the size multiples of 64).
- Pause detector and drift limit (0.08 s) are the builder's choices; confirm against the first film.
- First-film placement check: 537 sung takes, 548 phrases; worst phrase per take median 0.038, p95 0.093, max 0.099;
  505 at 0.09 or lower; the 32 above are all S21 or S23. Offsets were not checked against a record (window times
  are not in the fixture).
- Gate 5 estimate from our own job stats: 25 takes of 9 s at 1280x704 is about 0.92 GPU hours at the median, 1.70 at
  the mean.
- Live: both 3090 hosts up; commit headroom 30 GB, so one LTX load at a time. `ping` exits 1 in a non-UTF-8 shell.
- To do: PROVENANCE.md entries (runner and place, cut and review); move the `first_film` pytest marker from
  `tests/place/conftest.py` into `pyproject.toml`; the full suite cannot collect until `tests/barmap` and
  `tests/lint` are finished.

From the plan, prompts and lint builder:

- `pyproject.toml` needs package-data for `src/atomic_flix/data/` (lessons.json, baseline-rates.json, rules/*.txt) and the
  `first_film` marker (also `blender` for the scenes tests).
- PROVENANCE.md needs an entry for this builder.
- 66 rules cover 51 ledger lessons; 9 questions (hands, mouth, marks, identity, gaze, build, never-list, prop, flat
  areas) are 'needs reviewer' and preflight blocks until they are answered; 5 take-only lessons (L051c, L053, L072b,
  L084, L110) run after a batch; 15 lessons for runner and delivery stages are not covered by lint.
- First-film replay: smiling still S20 blocked (L014); named hands blocked in 25 of 25 sung prompts; late downbeat
  blocked (L060: 44 of 46 cuts on a snare beat on the old grid, 0 on ours); end freeze: shipped cut's S06, S17, S20,
  S23, S24, S25 blocked, our plan has none.
- Coverage tool is not installed in the venv.

From the Blender scenes builder:

- Street example (21-line description): Eevee 0.40 s per frame at 1920x1056 render only; full 145-frame push with
  all passes 92 s (1.57 frames per second; passes add about 0.55 s per frame); Cycles GPU 64 samples 2.37 s per frame.
- Pillow is not installed: textures use numpy and zlib only. ffmpeg is needed for the guides.
- Register the `blender` pytest marker in `pyproject.toml` (the scenes conftest does it for now).
- PROVENANCE: it also opened one of our own lab renders of the street scene (named in the private record).
- Known gaps: per-block random draws cannot pixel-match the old street script (look matches); Eevee has no
  object-index pass, so masks come from shader outputs; Blender normals are world space and are converted to camera
  space; the depth guide was not compared against the depth model our graphs use, and the pose colours were not
  compared against `control-pose-ltx23.json`.

From the real-run builder (2026-11-19, `docs/real-run.md`):

- Speed, one RTX 3090, cold model load included in `busy_s` (ComfyUI's execution start to success): Qwen image edit
  still at 640x352, 20 steps, 78.8 GPU s; LTX-2.3 sung take, `sung-ltx23-pinned.json`, 1280x704, 145 frames (6 s),
  95.7 GPU s, so 15.8 GPU s per video s. The first film's pick for the same shot (10 s, model warm) was 13.2. A cold
  load adds tens of seconds to the first job on a host; budgets from a single cold take run high.
- Memory, measured with `read_commit` every 2 s: the still load took about 21 GB of commit and kept it while
  resident (headroom 29.7 to 8.9 GB). One LTX load from 28.5 GB headroom bottomed at 1.0 GB (78.9 of 79.9 GB), about
  28 GB at peak, and kept about 12 GB resident afterwards. Set LTX sidecars to `commit_gb` 28 to 30, and refuse a
  heavy job below `commit_gb` plus 5 GB (`runner shoot --min-headroom`); the film verb `shoot` needs that option too.
- A resident model is invisible to the load gate and blocks the next heavy job through the headroom floor. Releasing
  our own load needs ComfyUI's `/free` on an idle host; the client has none on purpose. Decide this.
- Runner additions: `Request.seed` (and `"seed"` in a batch file), the headroom floor (`min_headroom_gb`,
  `--min-headroom`, summary `refused`), stills logged with null video seconds, `summarize` counting still time in GPU
  hours, "nothing waiting" for an empty run.

## Open problems from the first-film replay, settled 2026-11-19

1. **The audit refused 19 of 25 sung shots as slowed (rates 0.88 to 0.99).** Cause: the placement map, not the
   window times. The map holds a point every 0.1 s, each placed to about one 10 ms feature hop (the fit stage is held
   to 0.02 s), and the audit read the slope between neighbouring points: a 10 to 12 ms wobble over 0.1 s reads as
   0.88x. Measured on the replay's maps: whole-shot slopes 0.997 to 1.000, offsets steady within 36 ms per shot,
   slowest 1 s window 0.974. The missing window times only move a take's whole offset, never its slope. Now
   (`cut/rate.py`): the rate is read over every 1, 2 and 4 s window and the whole shot, and a window is a slowed take
   only when it is under 1 - 2U/L (U = 0.02 s placement uncertainty, L the window). A take truly under 1x (0.97x
   over a shot, 0.8x for one second) is still refused. Re-audited: 0 rate errors; the 6 head errors (old takes that
   do not reach back to the new plan's cuts) remain, as they should.
2. **Audit and lint C1 judged jump cuts on different evidence.** Both now call `atomic_flix.setups.reads_as_jump`
   (one setup and crop sizes under 20 % apart; unknown size on one setup is a warning, not a guess); the plan's size
   notes use it too. The edit carries each shot's `crop_keep`. On the replay the five setup-only "jump cuts" are gone
   (their sizes differ by 20 % or more); C1's seven warnings are pairs with a cutaway between, which the cut never
   puts side by side.
3. **A plan starting at 0 s showed the first render's opening frames.** The first cut is now the lead at 0.25 s (the
   slice head), grid `lead`; a song sung before it is refused with the reason.
6. **Drift read a moving subject as camera drift.** The camera's step is now the median step of 4 x 4 tiles that show
   background (the outer ring, or tiles a background mask covers); tiles moving apart from it are reported as
   subject motion (`subject`, a share of the picture). A walking subject a third of the frame wide now reads 0 %
   drift where the whole-picture measure read 34 %.
7. **`blocks/` sat outside the package.** It is now `src/atomic_flix/scenes/pieces/`, listed as package data; a built
   wheel carries all 26 files.
8. **PROVENANCE.md** lists what each builder's code and data show it read; anything else is marked not recorded.
