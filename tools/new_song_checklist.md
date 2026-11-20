# New song checklist

What the person supplies, what the kit does, gate by gate. Run `atomic-flix progress FILM` at any point: it names the
next gate and everything missing or stale.

## Start with a dry run

```
atomic-flix new out/films/next-song --name "Next Song" --lyric out/next-song/lyric.txt --star Nova --dry-run
```

The validator names what a new film still lacks, for example:

- `audio/mix.wav` missing: the finished song (gate 2, and the sound of every cut).
- `audio/voice.wav` missing: the lead vocal alone (`time` reads every line from it; every vocal render hears it).
- `audio/band.wav`, `audio/drums.wav` missing: the beat grid and the bar's one (drums first, else band, else mix).
- `shots.txt` missing: the shot list (`plan`, gate 4).
- `star.who` missing: one sentence from canon, approved by the person, for the still prompts.
- A lyric as published is not yet the lyric as sung: the take's repeats, wordless lines and any backing parts must be
  checked against the vocal stem and written out.

## What the person supplies

| What | Why | Notes |
|---|---|---|
| Stems of the exact take: mix, lead vocal, band (instrumental), drums | `time`, `bars`, every render's audio, the cut's sound | Ask for a drum stem if one exists (the bar's one is weaker without it). |
| The restored master | The mix laid over the final cut | Gate 2 fingerprints the file the person approved; a new master after gate 2 reopens it. |
| The concept pick | Gate 1 | Three pitches of at most 120 words: premise, the one visual device, the arc, one risk. |
| The lyric as sung | `time` | Repeats written out, `[Section]` lines, backing in parentheses. |
| The singer's sentence and looks from canon | Still prompts | From the site's canon files, approved by the person; never invented. |
| The answer at each of the six gates | Everything after it | Recorded word for word with `atomic-flix gate FILM answer GATE --by NAME --words "..."`. |

## The six gates and what the kit does for each

| Gate | Shown, and the one question | Before it, the kit | After a yes |
|---|---|---|---|
| 1 Concept | Three pitches. "Which pitch is the film?" | Nothing to run. `new` makes the folder and lists what is missing. | The shot list can be written for the chosen pitch. |
| 2 The song, by ear | The mix with a click on the bar's one. "Is this the finished song, with the click on the one where you count it?" | `time` (line table, flags), `bars` (beats, the bar's one with its margin; says when it is unsure), `tools/click.py` for the click. | The mix is fingerprinted; `downbeat_slot` goes into film.json if the ear moved the one. Lint stops if the mix changes later (L006). |
| 3 Her face and looks | The reference sheet and one or two first frames at full size. "Is this her?" | Still prompts in `plan/<key>.still-prompt.txt`; the judge questions per still (hands, mouth, marks, identity, gaze, build, flat areas). | Batches of more than three vocal shots may run (L091). |
| 4 The board | Every first frame, its time and lines on one sheet (`plan/board.html`). "Is this the film you want rendered?" | `plan` (cuts on the one or three, slices, gated and soft voices, prompts), `lint` (every rule from the first film). | The prompts and slices are fixed for the batch. |
| 5 Prompts and render time | `plan/report.md` and `plan/budget.json`. "May this batch run for these hours?" | `budget`: takes, size, GPU hours from this machine's log (else the first film's rates); `lint` must be clear apart from this approval; `eval` fresh and not BLOCKED for gate 5. | `shoot` runs (it refuses before this yes); `place` lines each render up with its sound. |
| 6 v1 | The cut, after a cold reviewer found no clear errors. "Accept, or what's wrong?" | `cut` (one encode, song at -14 LUFS, audit, flash check), `review` (sheets with motion strips and measures), the cold-review rounds recorded in standing.json, then `eval` fresh and not BLOCKED for gate 6. | After v1 only what the person flagged changes; `compare` sets the film beside the first one. |

## Order of commands

```
atomic-flix new FILM --song MIX --voice VOX --band BAND --drums DRUMS --lyric LYRIC --shots SHOTS --star Nova --who "..."
atomic-flix gate FILM ask concept --shown pitches.md ; atomic-flix gate FILM answer concept --by NAME --words "..."
atomic-flix time FILM ; atomic-flix bars FILM ; python tools/click.py ... (then gate 2)
(stills made and judged into stills/<key>.png and stills/<key>.json; gate 3)
atomic-flix plan FILM ; atomic-flix lint FILM (gate 4)
atomic-flix budget FILM ; atomic-flix eval FILM (gate 5)
atomic-flix shoot FILM --sung-graph ... --plate-graph ... ; atomic-flix place FILM
atomic-flix cut FILM ; atomic-flix grade FILM ; atomic-flix review FILM (cold review rounds)
atomic-flix eval FILM (then gate 6)
atomic-flix compare FILM --baseline baseline.json
```

## Not covered by the kit yet

- Making and judging the stills (an image model and a judge); the kit asks the questions and reads the answers.
- Grading (`tone`) is not built; the cut is ungraded. Word labels (a speech model) are made outside the kit.
- Picks: the person picks one render per shot by watching them (`film.json` `picks`); the kit never picks.
