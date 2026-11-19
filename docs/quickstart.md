# Quickstart: a whole film on a tiny synthetic song

Every step below reads and writes the film's own folder, so you can stop after any of them, open the files, change
one and go on. This exact run is the test `tests/e2e/test_synthetic_film.py`; it takes about 15 seconds and needs
no GPU (a fake ComfyUI stands in for the renders). You need Python 3.10 or newer and `ffmpeg` and `ffprobe` on the
PATH.

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"        (Windows; .venv/bin/python elsewhere)
```

After that the command is `atomic-flix` (or `python -m atomic_flix.cli`). `atomic-flix --help` lists the verbs;
`atomic-flix VERB --help` explains one.

## 1. The song and a new film

```
python tools/synth_song.py work/song
atomic-flix new work/films/tiny-song --song work/song/mix.wav --voice work/song/voice.wav ^
    --band work/song/band.wav --drums work/song/drums.wav --lyric work/song/lyric.txt ^
    --shots work/song/shots.txt --star Frankie --who "an android who sings for the band"
```

The synthetic song is 34 seconds at 111 BPM with four sung lines. `new` makes the folder from the template
(`film.json`, `notes.md`, `standing.json`, an empty `job-log.jsonl` and every subfolder), copies the stems in and
prints what is still missing. Add `--dry-run` to see that report without writing anything.

The test then edits `film.json` the way a person would: `"frame": [320, 192]` and `"final_size": [320, 192]` for a
quick run, `"batch": {"takes": 1}`, and the singer's outfit.

## 2. The person's gates

A person decides at six gates, and nowhere else. Each is two commands: what was shown and the one question, then
the person's words exactly as given (they go into `notes.md` word for word).

```
atomic-flix gate work/films/tiny-song ask concept --shown pitches.md
atomic-flix gate work/films/tiny-song answer concept --by "Test Person" --words "the rooftop one"
```

Gate 2 (the song by ear) also fingerprints the mix: if the file changes later, `progress` and `lint` say so.

`--words` records the answer as relayed (someone ran the command with the person's words quoted). Leave `--words`
out at a terminal and the person types the answer there; it is recorded as typed by the person. `progress` shows
which for every gate. Neither proves who typed: see [gates.md](gates.md).

## 3. Line times and the bar's one

```
atomic-flix time work/films/tiny-song         analysis/voice-lines.json: every line's start and end
atomic-flix bars work/films/tiny-song         analysis/pulse.json: every beat and the bar's one
```

`bars` says how sure it is. Make a click on the ones with `tools/click.py` and count along before gate 2; if the
one is somewhere else, write `"downbeat_slot"` into `film.json`.

## 4. Stills, the plan and the board

Each shot needs a first frame in `stills/<key>.png` and a record `stills/<key>.json` saying how it was made and
what the judge found at full size (the test writes synthetic pictures with a passing judge record).

```
atomic-flix plan work/films/tiny-song         plan/cuts.json, plan/<key>.task.json, voices, prompts
atomic-flix lint work/films/tiny-song         plan/report.md and plan/board.html; exit 1 while anything blocks
```

`plan` puts every cut on the bar's one or three first and fits each render's slice to it. `lint` checks the plan,
the prompts and the stills against what the first film taught; before gate 5 it blocks on the missing approval
of the hours (rule L127), and on anything else it finds.

## 5. Gate 5: the hours

```
atomic-flix budget work/films/tiny-song       plan/budget.json: takes, size and GPU hours
atomic-flix gate work/films/tiny-song ask spend
atomic-flix gate work/films/tiny-song answer spend --by "Test Person" --words "yes, run it"
atomic-flix lint work/films/tiny-song         now clear
```

The hours come from this machine's job log when it has renders of the same graph, else from the first film's
measured rates. The yes covers that batch only: its takes, frame size and hours are copied into `standing.json`,
and `shoot` plans no more takes than it covers. A changed plan (re-run `budget` with other takes or size) or a
second batch needs `gate ... reopen spend`, then a new ask and answer.

## 6. Shoot, place, cut, grade, review, compare

```
atomic-flix shoot work/films/tiny-song --sung-graph graphs/sung.json --plate-graph graphs/plate.json ^
    --hosts 127.0.0.1:8188
atomic-flix place work/films/tiny-song        renders/<key>/rNNN.fit.json
atomic-flix cut work/films/tiny-song --speed veryfast
atomic-flix grade work/films/tiny-song --speed veryfast   cuts/v01-toned.mp4 and .tone.json
atomic-flix review work/films/tiny-song       review/v01/MANIFEST.txt and the boards
atomic-flix compare work/films/tiny-song --baseline baseline.json --out work/films/tiny-song/review/compare.md
```

`shoot` refuses until gate 5 holds the person's yes and lint is clear (`python -m atomic_flix.runner shoot` takes
the same checks). It writes each render, its job file, a line in the machine's log (`log/jobs.jsonl` beside the film
folders) and two lines per render in the film's ledger. In the test the hosts are a fake ComfyUI whose "model" draws
a moving test picture and carries the audio it was sent.

The graphs live in the film folder (`graphs/` here) or the kit's own `workflows/`; every input a job uploads must
lie inside the film folder. Each graph has a sidecar `<graph>.meta.json` naming its `commit_gb` (the memory its
model load commits); a graph without one counts as a 30 GB load, and one that loads nothing big says
`"light": true`. A heavy job never starts while commit headroom is under the floor, by default the heaviest
`commit_gb` plus 5 GB (`--min-headroom GB` to change it, 0 to turn it off). Hosts are `host:port` on this machine;
another machine needs `--allow-remote`, since the runner sends it the film's pictures and voice.

`place` lines each vocal render up with the audio it was sent (a cost near 0 means the same sound). `cut` uses the
person's picks from `film.json` `picks`; a shot with exactly one render uses it. It renders `cuts/v01.mp4` with the
song back over the picture, audits every cut (`cuts/v01.audit.json`) and runs the flash check
(`cuts/v01-strobe.json`). The film opens at 0.25 s of song, the plan's lead: the first render starts at 0 and its
opening frames are never shown. `grade` evens black, white and colour strength across shots toward the film's own
levels, lays one look over all (never grain), prints the spread before and after, and runs the flash check again on
the graded film (`cuts/v01-toned-strobe.json`). Programs in the film's `hooks/tone.d/` run after the grade only
with `--hooks`: they are code from the film folder, so they are off by default, and with the flag each one is
named before it runs. `review` makes the boards a cold reviewer reads, from the graded
film when there is one. `compare` sets the film's numbers beside
the first film's.

`atomic-flix progress FILM` shows the next gate and anything missing or stale at any point.
