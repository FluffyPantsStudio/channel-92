# atomic-flix

A kit for making a music video from a finished song's stems, on your own machine. It times every sung line, finds
the beats and the bar's one, plans cuts on the bar, writes the prompts, drives local ComfyUI graphs for the renders
and Blender for sets and passes, places each render back on the song by its sound, and assembles, grades and checks
the cut. Every stage reads and writes plain JSON in the project folder, so a person can stop, look, edit and go on.

Status (2026-11-19): Phase 1 integrated and graded. One command, `atomic-flix`, drives a film from stems to a
graded, flash-checked and reviewed cut; `docs/quickstart.md` walks a whole film on a synthetic song with no GPU, and
`tools/replay_first_film.py` replays our first film through the kit on the CPU. The ComfyUI runner is being tested
against a real ComfyUI; the scenes stage needs Blender 5.2 for its renders. Clean-room status: `docs/clean-room.md`,
`PROVENANCE.md`, `docs/shared-vocabulary.md`.

## Install

Python 3.10 or newer; numpy is the only runtime dependency. ffmpeg and ffprobe on the PATH for anything with video.
Blender only for `scenes capture` and `scenes blend`.

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"      (Windows)
.venv/bin/python -m pip install -e ".[dev]"          (Linux, macOS)
.venv\Scripts\python -m pytest                       (the fast suite)
.venv\Scripts\python -m pytest -m first_film         (the first film's regressions: set FLIX_FIRST_FILM)
.venv\Scripts\python -m pytest --cov               (with coverage)
.venv\Scripts\python -m build --wheel              (a wheel in dist/; `build` comes with the dev extra)
```

A built wheel carries everything the kit reads at run time: the lint rules and lessons (`atomic_flix/data/`), the
Blender blocks library (`atomic_flix/scenes/pieces/`) and the graph name maps (`atomic_flix/workflows/`).

Tests that replay our first film need its private files and skip without them: `docs/first-film-replay.md`.

## The command

`atomic-flix --help` lists the verbs; `atomic-flix VERB --help` explains one. Film verbs, in the order a film meets
them, each reading and writing the film's folder:

| Verb | What it does |
|---|---|
| `new FILM --song ... --voice ...` | Make a film folder from the template, copy the stems in, list what is missing. |
| `progress FILM` | The next gate, and anything missing or stale. |
| `gate FILM ask/answer/reopen GATE` | Record what the person was shown and their answer, word for word (six gates). |
| `time FILM` | Time every sung line from the voice stem (`analysis/voice-lines.json`). |
| `bars FILM` | Beats and the bar's one (`analysis/pulse.json`). |
| `plan FILM` | Cuts on the bar first (the first cut is the 0.25 s lead), then each shot's slice, gated voice, soft copy and prompts (`plan/`). |
| `lint FILM` | Preflight: every rule and picture question; `plan/report.md` and `plan/board.html`. Exit 1 while anything blocks. |
| `budget FILM` | Gate-5 GPU hours for the planned batch (`plan/budget.json`). |
| `shoot FILM` | Render the plan on the ComfyUI hosts once gate 5 says yes and lint is clear. |
| `place FILM [KEYS] [--again]` | Place each render on the song by its sound (`renders/<key>/rNNN.fit.json`). |
| `cut FILM` | Assemble the next cut on the plan's cuts in one encode, song at -14 LUFS; audit every cut; flash check. |
| `grade FILM [--palette FILE] [--measure] [--hooks]` | Each shot toward the film's own black, white and colour strength, one look, no grain; spread before and after; `hooks/tone.d/` only with `--hooks` (off by default); flash check on the graded film (`cuts/vNN-toned.mp4`). |
| `review FILM` | Boards for a cold reviewer (`review/vNN/`), from the graded film when there is one. |
| `compare FILM --baseline FILE` | The film against the first film's numbers (Markdown). |

Stage modules, by name, with their own verbs:

| Module | Verbs |
|---|---|
| `cut` | `audit EDIT.json [--both-sides]`, `encode EDIT.json OUT.mp4 [--speed slow]`, `flash FILM.mp4` |
| `grade` | `measure CUT.mp4 --edit EDIT.json`, `apply CUT.mp4 OUT.mp4 --edit EDIT.json [--palette FILE]` |
| `review` | `boards`, `frames` |
| `runner` | `ping`, `plan`, `budget`, `shoot`, `progress` |
| `scenes` | `check`, `plan`, `capture`, `blend`, `controls` |
| `timing`, `barmap`, `gates`, `folder` | the same as `time`, `bars`, `gate`, and `new`/`progress` |

What the checks decide, in short: the cut audit refuses a take played slower than 1x only beyond the placement's own
uncertainty (rates over 1, 2 and 4 s windows, `cut/rate.py`), a take's first two frames, and a jump cut (one setup,
crop sizes under 20 % apart: the same decision as lint rule C1, `setups.py`). The review's camera drift is read from
the background tiles, so a subject crossing a locked frame is reported as subject motion, not drift.

## Names and file formats

Every name in the kit is its own: each name was changed on 2026-11-19 when the kit dropped the names its specs had
passed on (the maintainers' renames table, kept privately in `docs/private/`). Every JSON file the kit writes starts with a format tag (`"format":
"atomic-flix/pulse@1"`); `docs/formats.md` lists them. ComfyUI graphs that declare other placeholder names are filled
through a name map, `<graph>.map.json` (`atomic_flix/runner/names.py`); the maps for our existing graphs ship in
the package, in `src/atomic_flix/workflows/`.

## Tools

| Script | What it does |
|---|---|
| `tools/synth_song.py OUT` | Writes the tiny synthetic song the quickstart and the end-to-end test use. |
| `tools/replay_first_film.py` | Replays our first film through the kit on the CPU and writes `out/replay-first-film.md`. |
| `tools/lyric_from_site.py` | Takes a song's lyric from the site's catalog as a starting lyric file. |
| `tools/new_song_checklist.md` | What the person supplies and what the kit does at each gate, for the next song. |
| `tools/make_fixtures.py synthetic` | Writes the synthetic beat and bar fixtures (drum, band and mix stems plus `truth.json`) to `fixtures/synthetic/`. Deterministic. |
| `tools/make_fixtures.py first-film` | Copies our first film's stems and timing files to `fixtures/first-film/` (git-ignored) with a manifest of sizes and sha256, and `TRUTH.txt`, what is known about its bars. |
| `tools/click.py` | Writes a counting click track on a beat list, optionally over the song. |
| `tools/similarity.py OLD NEW` | Compares two source trees for copied code, prose and naming; prints the distinctive measures that decide PASS and the strict counts beside them. Reads no allow-list. See `docs/clean-room.md` and `docs/shared-vocabulary.md`. |

## Confirming bar one by ear

The bar-one stage can tell the snare beats from the kick beats, but in some songs it cannot tell the bar's one from
its three. A person decides that once per song, by ear:

1. Make the click over the song. `--phase P` puts the one on every beat whose index mod 4 is P.
   ```
   python tools/click.py fixtures/first-film/build/beats.json --phase 0 --over fixtures/first-film/audio/song.wav --gain -6 --out out/click-phase0.wav
   ```
2. Listen with the song. The one is a loud high blip; two, three and four are softer and rise in pitch back toward
   the next one, so you can count "ONE two three four" along.
3. Ask: does the loud blip land where you would count one, at the start of a phrase, where the singer comes in, where
   the chords turn? If it feels like the middle of the bar, try `--phase` two higher (0 and 2, or 1 and 3). If it
   lands on the snare, try one higher or lower.
4. Write the phase you heard in the project's notes (for the first film, in `fixtures/first-film/TRUTH.txt`); it
   overrides the stage's guess.

A click without the song (`--over` left out) is useful for checking the beat grid itself.

## Licence

MIT. See `LICENSE`. The models the graphs load have their own licences; see `docs/graphs.md`.
