# The eval: proof that a film honored the rules

Lint proves a rule works on its own examples. The eval proves a film obeyed it: it runs every rule the kit states on
the film's own files and on its process record, and gates 5 and 6 wait for its verdict.

```
atomic-flix eval FILM [--json] [--gate {5,6}] [--stale-ok]
```

Plain `eval` runs every check and writes `FILM/eval/report.json` and a one-page `FILM/eval/report.md`; exit code 1
when BLOCKED. `--json` prints the whole report. `--gate 5` or `--gate 6` runs nothing and says whether that gate may
be asked now (exit code 1 when not). `--stale-ok` runs nothing and shows the saved report, marked STALE when an input
changed since; the gates never accept a stale report.

## The rules map

`atomic_flix/data/rules-map.json` lists every rule: the 66 of `lessons.json`, its nine reviewer questions (`RV-*`)
and five after-the-batch questions (`AB-*`), and the process rules of `AGENTS.md` and the gates (`SP-*`, `LG-*`,
`SC-*`, `CT-*`, `PS-*`, `GP-*`). Each entry has:

| field | meaning |
|---|---|
| method | `auto` (measured from the film's files), `ledger` (read from the process record), `judge` (a cold reviewer), `person` (only the person can say), or null: a gap |
| unit | `shot`, `scene` or `film` |
| level | `block`, `warn` or `note` |
| due | the gate it must hold before: `spend` (gate 5) or `v1` (gate 6) |
| check | the eval family that reads it: `lint`, `sent`, `ledger`, `scene`, `cut` |

A test fails when `lessons.json` gains a rule or a question without a map entry, when the map names one that does not
exist, or when a level disagrees. Judge, person and gap rules come out `unchecked` with the reason in `why`; they are
listed in the report, never counted as passes. The gaps today: one heavy load at a time (`GP-HEAVY`: nothing durable
records headroom or other runner processes) and never touching what is not yours (`GP-MINE`: nothing records queue
clears or deletions).

## What is checked

- **lint** (auto): `lessons.json`'s rules on the film's real book (the `lint` verb's own loader, with the gate facts
  from `standing.json`). Prompt rules also run on each distinct wording a render was actually sent with. Every
  finding is bound to its shot; a shot a rule found nothing on gets a pass row.
- **sent** (auto): the wording of every job file past `planned` (`renders/<key>/rNNN.job.json`, which the runner
  writes before it submits and keeps after) is searched for the word lists in `data/rules/` (grain, equipment, hands
  in sung takes) and the film's `never` list. A film's own `rules/<name>.txt` replaces a list. Quoted sung words are
  left out, as lint does. The same files say whether every input lay inside the film (`SP-PATHS`).
- **ledger**: `standing.json` loads under the gate machine's refusals (`LG-LOAD`); gates were asked in order
  (`LG-ORDER`), answered by a person with words (`LG-PERSON`), with the arrival recorded (`LG-ARRIVAL`), and no
  answer was reused at a second gate (`LG-REUSE`); every render carries a gate-5 yes and no yes covers more takes
  than it approved (`LG-BATCH`); each shot's still was judged (`judge.at` in `stills/<key>.json`) before its first
  render was sent (`LG-JUDGE`); every review loop ends on a clean round or stalls (`LG-ROUNDS`), each round by a
  reviewer new to the film (`LG-FRESH`).
- **scene** (auto): shots sharing a `scene:` tag share one master still (film.json `scenes.<name>.master`, else the
  first shot's still) that every later still lists in its `refs` (`SC-MASTER`), one reference per prop
  (`SC-PROPS`), one aspect from the record's `size` or the PNG header (`SC-ASPECT`) and one look (`SC-LOOK`, warn).
- **cut** (auto): the newest cut's audit, loudness, grade account and the flash check on the graded film, read from
  the files `cut` and `grade` wrote, never measured again. The newest cut is the highest `vNN` among the cut films
  and audits, so a newer film without its audit leaves the rows unchecked. A missing result file leaves its rows
  unchecked; a missing grade fails `CT-GRADE`.

## The verdict

Each row is `pass`, `fail` or `unchecked`. A kit-checkable rule (auto or ledger) left unchecked because an input is
missing, or of a shape the eval cannot read, counts as a failure; a rule with nothing on record to judge (no answers
yet, a still record missing, a time that is not a time) is unchecked or fails, never a pass. At a gate, only rows
due by that gate count:

- **BLOCKED**: a block rule failed, or a block rule the kit could check was left unchecked.
- **WARN**: otherwise, a warn rule failed or was left unchecked.
- **CLEAN**: nothing the kit can check fails. It does not mean every rule held: judge, person and gap rules stay
  unchecked by design, and the report puts their count next to the verdict.

The report's `verdict` is for the gate the film is heading to (gate 6 once gate 5 has passed), and `verdicts` and
`blocking` hold both, for reading; the gate hook ignores them and computes the verdict again from the rows.

## Paths

Every path the film's files name (the shot list in film.json, the mix, a task's still, closing still, audio and graph)
is read only inside the film folder (a graph may also lie in the kit's own graphs): an absolute path, a `..` part or
a link out of the folder is refused and never read, and the rows that needed it fail or stay unchecked. Lint's own
book reads paths the same way.

## Staleness and the gate hook

The report keeps the SHA-256 of every input it read: the film's files by folder (`plan/` with its voices, `stills/`,
`renders/` job files, `cuts/` results and films, `analysis/`, `standing.json`, `film.json`, the shot list and the
mix), every file a task points at wherever it lies in the film (recorded as missing when it is not there), and the
kit's rule data and version. Each row carries the hash of its family's inputs. The report is stale once any input
changes, appears or goes.

The hook holds gates 5 and 6 at three moments, and fails closed at each:

- **asking** (`atomic-flix gate FILM ask spend` or `ask v1`, `ask_gate` in Python): refused while the report is
  missing, malformed, stale or BLOCKED for that gate, while its inputs do not match their own hash, or while a rule of
  the rules map has no row. At gate 6 the cut shown must be the cut the eval read (`cuts/vNN`).
- **answering yes** (`answer`, `answer_gate`): the same check again, where the only change allowed since the eval is
  the gate's own ask in standing.json. Edit anything between the question and the answer and the yes is refused; a
  no is always recorded.
- **shooting** (`shoot`, and the runner's own `shoot`): gate 5's check again, where only gate 5's ask, answer and
  batch may have changed. A film touched since the eval, a resumed batch included, needs a new `eval` first.

This is bookkeeping, like the gates themselves (`docs/gates.md`): it catches a stale or blocked report and a forged
verdict field, not someone who rewrites the rows. Run `eval` last, right before asking.