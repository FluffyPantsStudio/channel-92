# Quickstart: a whole film on a tiny synthetic song

Every step below reads and writes the film's own folder, so you can stop after any of them, open the files, change
one and go on. This exact run is the test `tests/e2e/test_synthetic_film.py`; it takes about 15 seconds and needs
no GPU (a fake ComfyUI stands in for the renders). You need Python 3.10 or newer and `ffmpeg` and `ffprobe` on the
PATH.

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"        (Windows; .venv/bin/python elsewhere)
channel92 setup                                        (checks the prerequisites, says how to get what is missing)
channel92 setup --install                              (fetches the pinned ntsc-rs for the era looks; asks first)
```

`setup` only checks. `setup --install` downloads ntsc-rs v0.9.7 from its own GitHub release, verified against the
size and sha256 the kit pins, into a per-user tools folder ([third-party.md](third-party.md)); nothing else in the
kit downloads anything, and this synthetic run does not need it.

After that the command is `channel92`; `atomic-flix` is the same command under its first name, and the examples
here use it (so does `python -m atomic_flix.cli`). `channel92 --help` lists the verbs; `channel92 VERB --help`
explains one.

## 1. The song and a new film

```
python tools/synth_song.py work/song
atomic-flix new work/films/tiny-song --song work/song/mix.wav --voice work/song/voice.wav ^
    --band work/song/band.wav --drums work/song/drums.wav --lyric work/song/lyric.txt ^
    --shots work/song/shots.txt --star Nova --who "a singer with short silver hair" ^
    --aspect 16:9 --by "Test Person" --words "wide, like the channel's later years"
```

The synthetic song is 34 seconds at 111 BPM with four sung lines. `new` makes the folder from the template
(`film.json`, `notes.md`, `standing.json`, an empty `job-log.jsonl` and every subfolder), copies the stems in and
prints what is still missing. Add `--dry-run` to see that report without writing anything.

The test then edits `film.json` the way a person would: `"frame": [448, 256]` and `"final_size": [448, 256]` for a
quick run (still 16:9 within the kit's 3 %), `"batch": {"takes": 1}`, and the singer's outfit.

### Setup choices

Two decisions are recorded before anything is generated. They are not gates: a gate shows one thing and asks one
question; a setup choice is a decision the film is then made under.

- **Aspect**, the director's choice: 16:9, 4:3, 2.39:1 or 9:16. `atomic-flix choose FILM aspect 4:3 --by NAME
  --words "..."` (or `new --aspect`) writes film.json `setup`, the render `frame` and the delivery `final_size` from
  the aspect table (`atomic_flix/aspects.py`; `--tier draft` renders smaller for a look), and the words into
  `notes.md` word for word with the date. 16:9 renders at 1280x704 and delivers at 1920x1080, as every film so far.
- **Year**, 1950 to 2010 (the years Channel 92 broadcasts): `atomic-flix choose FILM year 1987`. It only suggests
  an aspect (4:3 before 1998, 16:9 after); it never decides one. It also picks the film's era, whose look `finish`
  lays on at the very end ([eras.md](eras.md)); `progress` names the era, or says there is none.

Until the aspect is chosen, `plan` and `shoot` refuse and `progress` lists "aspect not chosen" right after the
concept. A film.json that has a frame but no `setup` block counts as not chosen. Once it is chosen, `lint` refuses
a render frame or a first frame whose shape is not that aspect (rule AR1, within 3 %).

## 2. The song's structure, then the person's gates

Before the concept, read the song's shape:

```
atomic-flix structure work/films/tiny-song    analysis/structure.json and plan/structure.md
```

`structure` lists the sections in time order (from the lyric's `[Section]` lines; "Instrumental N" where the lead
stem is silent for 3 s or more; "unlabelled vocal" where the lead sings a part the lyric has no timed line for),
each snapped to the bar's one with the margin, how much of it the voice is on and how loud the band is under it.
Then the story gaps (instrumental stretches of 8 s or more, `--gap` to change it: where the pictures alone carry the
story), where the voice comes in, the longest unbroken sung stretch and how the repeats compare. It runs `time` and
`bars` first when their files are missing. Gate 1 shows `plan/structure.md` together with the concept, so the story
is planned on the song's own timeline. It is measured, not heard: gate 2 is where a person confirms it by ear.

A person decides at six gates, and nowhere else. Each is two commands: what was shown and the one question, then
the person's words exactly as given (they go into `notes.md` word for word).

```
atomic-flix gate work/films/tiny-song ask concept --shown pitches.md --shown plan/structure.md
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
atomic-flix eval work/films/tiny-song         eval/report.json and report.md: WARN or CLEAN, not BLOCKED
atomic-flix gate work/films/tiny-song ask spend
atomic-flix gate work/films/tiny-song answer spend --by "Test Person" --words "yes, run it"
atomic-flix lint work/films/tiny-song         now clear
```

The hours come from this machine's job log when it has renders of the same graph, else from the first film's
measured rates. The yes covers that batch only: its takes, frame size and hours are copied into `standing.json`,
and `shoot` plans no more takes than it covers. A changed plan (re-run `budget` with other takes or size) or a
second batch needs `gate ... reopen spend`, then a new ask and answer.

Gate 5 is not asked until `eval` has a fresh report that is not BLOCKED for it: run `eval` after `budget`, since a
report is stale once any file it read changes. The yes and `shoot` check it again, allowing only gate 5's own ask,
answer and batch to have changed, so anything edited in between needs a new `eval`. Rules due at gate 6 (the prompts as sent, the cut's checks, the
review rounds) are listed but do not hold gate 5. `docs/eval.md` says what the eval checks.

## 6. Shoot, place, cut, grade, review, finish, compare

```
atomic-flix shoot work/films/tiny-song --sung-graph graphs/sung.json --plate-graph graphs/plate.json ^
    --hosts 127.0.0.1:8188
atomic-flix place work/films/tiny-song        renders/<key>/rNNN.fit.json
atomic-flix cut work/films/tiny-song --speed veryfast
atomic-flix grade work/films/tiny-song --speed veryfast   cuts/v01-toned.mp4 and .tone.json
atomic-flix review work/films/tiny-song       review/v01/MANIFEST.txt and the boards
atomic-flix finish work/films/tiny-song --speed veryfast  cuts/v01-final.mp4: logo, era look, intro
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
(`cuts/v01-strobe.json`). The cut stays clean: no logo, no look, no intro (those are `finish`'s, below). The film
opens at 0.25 s of song, the plan's lead: the first render starts at 0 and its
opening frames are never shown. `grade` evens black, white and colour strength across shots toward the film's own
levels, lays one look over all (never grain), prints the spread before and after, and runs the flash check again on
the graded film (`cuts/v01-toned-strobe.json`). Programs in the film's `hooks/tone.d/` run after the grade only
with `--hooks`: they are code from the film folder, so they are off by default, and with the flag each one is
named before it runs. `review` makes the boards a cold reviewer reads, from the graded
film when there is one. `compare` sets the film's numbers beside
the first film's.

### Finishing: logo, era look, intro

`finish` is the last step on the picture. It takes the graded cut (`cuts/v01-toned.mp4`, else `cuts/v01.mp4`) and
writes `cuts/v01-final.mp4`, in this order:

1. **The logo**, top right on every frame: 14 % of the frame's width, 3 % of the width in from the top and right
   edges, never scaled up past the file's own size. It is the era's own mark (the 2000s and a film with no era wear
   the channel's modern mark). `--no-logo` or film.json `"brand": {"logo": false}` leave it off.
2. **The era's look**: the era's ffmpeg pre-filter (the 1950s go monochrome; the 1970s get warmer), then ntsc-rs
   with the era's preset on a clean temporary file (kept beside the output), then one final encode back to the film's
   size with the era's post-filter (the 1950s kinescope: hum bars, flicker, scan lines, glow, dark corners, milky
   blacks) and the cut's own sound. The film's year picks the era, and a year between two eras' first years blends
   their looks (1975 is halfway between the 1970s and the 1980s); `--year 1987` sets another year for one
   run, `--era 1980s` lays that era's own look on; `--no-look` leaves it off. ntsc-rs is a separate program (`channel92 setup --install` fetches the pinned build,
   [third-party.md](third-party.md)); `--ntsc-rs PATH`, else `CHANNEL92_NTSC_RS`, else the kit tools folder, else
   the PATH. A path given that is not there stops the step; with none found the film is finished without the look
   and the step says to run `channel92 setup --install`, so nothing is lost. `finish` never downloads anything.
3. **The intro**, joined in front, when film.json asks for one: `"brand": {"intro": "era"}` for the era's own (5
   silent seconds revealing the era's logo, made by ffmpeg at the film's frame size and kept in the film's
   `brand/` folder), or a path in the film folder for a clip of your own. The intro is made in the era's style
   already, so it never goes through ntsc-rs.

The masters stay clean: `cuts/v01.mp4` and `cuts/v01-toned.mp4` are only read, and grain and tape artefacts exist
only in the final. The flash check runs on the final too (`cuts/v01-final-strobe.json`). Before the batch, approve
the era by eye: `atomic-flix finish FILM --sample still.png` writes `plan/look-sample.png`, one frame of the look
and logo on that still. The eras, their looks, logos and intros: [eras.md](eras.md). In this run the film has no
year, so `finish` lays on the channel's logo and says there is no era.

Before gate 6, `eval` again: in this run it says BLOCKED, because no cold review round is on record yet
(`LG-ROUNDS`) and the synthetic stills carry no time for the judge's look (`LG-JUDGE`). Gate 6 waits until a fresh
report is not BLOCKED for it.

`atomic-flix progress FILM` shows the next gate and anything missing or stale at any point.
