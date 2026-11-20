# File formats and their version tags

Every JSON file the kit writes, and every row of its JSON Lines logs, starts with a format tag:

    {"format": "atomic-flix/<kind>@<version>", ...}

The kinds and their versions live in `atomic_flix/formats.py` (`VERSIONS`); `stamped(kind, data)` adds the tag and
`check_format(kind, data)` refuses a file tagged for another kind or version. A file without a tag is read as
version 1.

## Migration

None is needed. Every format below is new at version 1 (2026-11-19): the kit has no earlier release, and the names
inside the formats were settled in the same change (the maintainers' renames table, kept privately in `docs/private/`). A file written by a test build before the
tags existed has no tag and reads as version 1; `standing.json` from that build carries `atomic-flix/standing/1`,
the same format under its first spelling, and is read as is. Test folders made before the renames hold the old key
names and are made again, not converted. When a format changes in a way an old reader would misread, its version goes up
in `formats.py` and this page says what changed and how to move a file across.

## The formats

| Kind | File | Written by |
|---|---|---|
| `film` | `film.json` (its `setup` block holds the aspect and year from `choose`; `brand` holds `logo` and `intro`, `"era"` or a clip) | `new`, `choose`, and any step that saves the film |
| `standing` | `standing.json` | gates and `new` |
| `job-log-row` | each line of `job-log.jsonl` (`docs/job-log.md`) | the runner |
| `machine-log-row` | each line of the machine's job log (`jobs.jsonl`) | the runner |
| `job` | `renders/<key>/rNNN.job.json` | the runner |
| `budget` | `plan/budget.json` | `budget` |
| `voice-lines` | `analysis/voice-lines.json` | `time` |
| `word-labels` | `analysis/word-labels.json` | the word labeller |
| `pulse`, `swells` | `analysis/pulse.json`, `analysis/swells.json` | `bars` |
| `structure` | `analysis/structure.json` (its page: `plan/structure.md`) | `structure` |
| `cuts`, `task` | `plan/cuts.json`, `plan/<key>.task.json` | `plan` |
| `fit` | `renders/<key>/rNNN.fit.json` | `place` |
| `edit`, `audit`, `strobe` | `cuts/vNN.edit.json`, `cuts/vNN.audit.json`, `cuts/vNN-strobe.json` | `cut`, `cut` module |
| `tone` | `cuts/vNN-toned.tone.json` | `grade` |
| `review` | `review/vNN/review.json` | `review` |
| `scene` | a scene description (`scenes/FORMAT.md`) | a person |
| `scene-plan`, `scene-lock`, `scene-job`, `viewpoint`, `capture` | `plan.json`, `scene.lock.json`, `job.json`, `viewpoint.json`, `capture.json` in a capture folder | `scenes plan`, `scenes capture` |
| `controls` | `controls/controls-<model>.json` | `scenes controls` |
| `graph-meta` | `<graph>.meta.json` beside a ComfyUI graph | a person |
| `graph-map` | `<graph>.map.json` (`atomic_flix/runner/names.py`) | a person; ours are in `atomic_flix/workflows/` |
| `fixture-truth`, `fixture-manifest` | `fixtures/*/truth.json`, `fixtures/first-film/manifest.json` | `tools/make_fixtures.py`, `tools/synth_song.py` |
| `replay` | `replay.json` in a replay folder | `tools/replay_first_film.py` |
| `eval` | `eval/report.json` (`docs/eval.md`) | `eval` |
| `packet` | `desk/<gate>/manifest.json` (`docs/desk.md`) | `packet` |
| `director` | `review/director.json`, append-only `replies` and `marks` (`docs/desk.md`) | `desk` |
| `rules-map` | `atomic_flix/data/rules-map.json` | a person; a test keeps it whole |

Optional fields added without a version change, since an old reader ignores them: a shot's `scene:` in the shot
list, carried into its task as `"scene"`; and in a still's record (`stills/<key>.json`) `judge.at` (when the judge
looked, ISO 8601), `size` ([width, height]), `props` ({prop: reference}), `master` and `look`, which the eval reads
(`docs/eval.md`).

The machine's job log, the film's job log and the job files gained the tag in every row or record; readers ignore
it, so a log that mixes tagged and untagged rows reads as one.
