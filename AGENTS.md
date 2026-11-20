# Instructions for agents working with atomic-flix

atomic-flix turns a finished song's stems into a music video on a local machine: timing, bar detection, planning,
prompt lint, ComfyUI renders, placement against the song, cut, grade, review. Read `README.md` first, then
`docs/quickstart.md`. This file is the part an agent must get right before touching anything.

## 1. Set up the machine

1. **Python 3.10+** and a venv inside the repo:
   `python -m venv .venv`, then `.venv/Scripts/python -m pip install -e ".[dev]"` (Windows) or
   `.venv/bin/python -m pip install -e ".[dev]"`. The only runtime dependency is numpy.
2. **ffmpeg and ffprobe on the PATH.** Check with `ffmpeg -version`.
3. **Blender 5.2** only for the `scenes` verbs (`capture`, `blend`). Set `FLIX_BLENDER` to the `blender` executable if it
   is not in the usual install place. Without Blender everything else still works.
4. **ComfyUI**, one instance per GPU, listening on `127.0.0.1:8188` and `127.0.0.1:8189` (the defaults). Other hosts:
   `--hosts host:port,host:port` or `ATOMIC_FLIX_HOSTS`. Remote hosts need `--allow-remote` (plain HTTP, no auth: do
   not point it at a machine you do not control). Start each instance on its own card
   (`--cuda-device N --port P`).
5. **Models.** The kit downloads nothing. `docs/graphs.md` lists every shipped graph and the model files it loads;
   put those in your ComfyUI `models/` folders. A graph whose model is missing fails at the ComfyUI node, not in the kit.
6. **Check it:** `PYTHONUTF8=1 .venv/Scripts/python -m atomic_flix.runner ping` (both hosts up? on Windows set `PYTHONUTF8=1`, or `ping` exits 1), then the fast suite
   `.venv/Scripts/python -m pytest -q` (about 2 minutes, no GPU), then the whole synthetic film in
   `docs/quickstart.md` (about 15 s, a fake ComfyUI stands in for the renders).

Environment variables (all optional):

| Variable | Meaning |
|---|---|
| `ATOMIC_FLIX_HOSTS` | ComfyUI hosts, `host:port,host:port` |
| `ATOMIC_FLIX_MAPS` | extra folders of graph name maps (`<graph>.map.json`) and graphs |
| `ATOMIC_FLIX_COMMIT_HEADROOM_GB` | override for the commit-headroom reading (see section 3) |
| `FLIX_BLENDER` | path to the Blender executable |
| `FLIX_FIRST_FILM` | folder holding the maintainers' first film's private files; the `first_film` tests skip without it |

## 2. Run a film

`atomic-flix new FILM --song mix.wav --voice voice.wav --band band.wav --drums drums.wav --lyric lyric.txt` makes the
film folder; `atomic-flix progress FILM` always says what is next and what is missing or stale. Verbs in order:
`time`, `bars`, `plan`, `lint`, `budget`, `eval`, `shoot`, `place`, `cut`, `grade`, `review`, `compare`, with `eval`
again before gate 6. Every stage reads and writes plain JSON in the film's folder, so stop anywhere, look, edit, go
on. `atomic-flix VERB --help` explains one.

## 3. Rules an agent must not break

**Six gates belong to a person.** Concept, the song by ear, the singer's face and looks, the board, prompts and render
time (spend), and v1. Show one thing, ask one question, and record the person's own words with
`atomic-flix gate FILM answer GATE --words "..."`. Never answer a gate yourself, never invent or paraphrase the words,
never reuse one answer for another gate. `--words` is recorded as "relayed": you copied what the person said in chat.
At a terminal the person types the answer and it is recorded as "typed by the person". This is bookkeeping, not
authentication (`docs/gates.md`): the honesty is yours. A spend approval (gate 5) is bound to the batch shown (takes,
size, hours); a different batch needs a new answer.

**The ear decides, not a measurement.** Bar one (`bars`) can be uncertain: make the click (`tools/click.py`) and have
the person listen before gate 2. Timing lines the kit flags as uncertain are for a person's ear too. Never pick or rank
takes from a description or a number alone.

**One heavy load at a time.** On Windows what kills ComfyUI is the commit limit (RAM plus page file), not VRAM: a
big LTX load commits about 28 GB. The runner refuses a heavy job when headroom would fall under the graph's
`commit_gb` plus 5 GB and counts loads it has let start but that are not yet resident. A graph with no `.meta.json`
counts as heavy (30 GB). Do not defeat this with a bigger batch or a second runner process (ledger appends are not
serialised across processes).

**Never touch what is not yours.** Do not clear a ComfyUI queue, stop or restart an instance that has work, or delete
another job's files. Restart only an instance whose queue is empty.

**Lint blocks for a reason.** `atomic-flix lint` encodes the rules a first film paid for (no hands named in a sung
prompt, no smile on a singing mouth, one mood word, no grain in masters, and so on). Fix the cause; do not edit the
rules to pass. Nine questions are answered by a person or a cold reviewer (hands, mouth, marks, identity, gaze,
build, never-list, prop, flat areas); the preflight stays blocked until they are.

**The eval holds gates 5 and 6.** `atomic-flix eval FILM` checks that the film obeyed the rules, not only that the
rules work: lint on the real book and on the prompts as they were sent, the never-words in what was sent, the gate
and review ledger, scene continuity, and the cut's own checks, into `eval/report.json` and `report.md`. Gates 5 and 6
are refused, at the question, at a yes and (gate 5) before `shoot`, while the report is missing, stale or BLOCKED for
that gate. CLEAN means nothing the kit can check fails, not that every rule held. Run it last before asking, change
nothing between the question and the answer, fix what it lists, and never edit `data/rules-map.json`, a check or the
report to make a film pass; a rule nothing can check is a gap the report names (`docs/eval.md`).

**Grain and licences.** Never put grain or film-stock words in a prompt and never grade grain into a master; add it in
post. Say plainly where the output is AI-made, and follow the licence of every model you load (several open video
models ask for AI-labelled output).

**Paths stay inside the film folder.** The runner refuses inputs, outputs and graphs outside the film folder and the
kit's own `workflows/` folder. Scene files may only use blocks from the packaged library (or an explicit
`--blocks DIR`). `grade` runs hook scripts from `hooks/tone.d/` only with `--hooks`.

## 4. Contributing code (clean room)

This kit was written without copying any other kit. Keep it that way: write your own names, formats and wording; do
not paste code, docs or identifiers from other toolkits; `docs/clean-room.md` and `PROVENANCE.md` describe the process.
Tests first. Before a release run
`python tools/similarity.py PATH_TO_ANY_OTHER_TOOLKIT src` against any toolkit you read while working, and it must PASS
with no allow-list. Keep files small (under 800 lines), functions under 50 lines, no mutation of inputs, and handle
errors explicitly.

## 5. What never goes in the repo

No stems, songs, lyrics of released songs, video, images, Blender files, model weights, or API tokens. `fixtures/`,
`out/`, `docs/private/` and `.venv/` are ignored: never `git add -f` them. Test fixtures are synthetic
(`tools/make_fixtures.py synthetic`). Tests that need a real film read `FLIX_FIRST_FILM` and skip without it.
