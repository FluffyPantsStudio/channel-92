# The job ledger

Every GPU job a film runs (a render, a still, an edit, a model test) gets a line in the film's ledger,
`<film>/job-log.jsonl`. The runner writes it; `atomic_flix.compare` reads it to set the film's GPU time and render
counts beside the first film's, and `atomic_flix.project.validate` reports any line it cannot read.

## Format

UTF-8 text, one JSON object per line (JSON Lines), appended. Every line has exactly these nine fields; none may be
left out, and `null` is written where the table allows it.

| Field | Type | Null allowed | Meaning |
|---|---|---|---|
| `job_id` | text, not empty | no | The job's id, unique within the film and never reused (for a render, e.g. `S02-r007`). |
| `kind` | text, not empty | no | What the job makes. See the kinds below. |
| `shot` | text | yes | The shot key the job is for (`S02`, `N08`); null for a job that serves no one shot. |
| `host` | text | yes | Where it ran, as `address:port` of the ComfyUI (or another worker's name); null while only planned. |
| `seed` | whole number | yes | The seed sent with the job; null when the job takes none. |
| `gpu_seconds` | number, 0 or more | yes | GPU time from the worker's own execution timestamps; null when not measured. |
| `started` | ISO 8601 time | yes | When the job started on its host, with its offset (`2026-11-20T14:03:11+00:00`; `Z` is read as UTC, a time with no offset as UTC). |
| `finished` | ISO 8601 time | yes | When it ended, same form; not before `started`. |
| `state` | one of `planned`, `running`, `done`, `errored` | no | Where the job stands. `running` needs `started`; `done` and `errored` need `finished`. |

A job whose enqueue went unanswered is `unknown` in its job file (it may or may not be queued); it gets no ledger line
until the next run finds it on its host by client id (then `running`) or confirms the host never got it.
Each line is written with one append, one writer at a time per runner process.

Example:

```json
{"job_id": "S02-r007", "kind": "vocal", "shot": "S02", "host": "127.0.0.1:8189", "seed": 1934820044, "gpu_seconds": 149.2, "started": "2026-11-20T14:00:31+00:00", "finished": "2026-11-20T14:03:11+00:00", "status": "done"}
```

## Kinds

`kind` is free text, but these are the ones the comparison groups:

| Kind | Job | Compared with the first film's |
|---|---|---|
| `vocal` | render of a shot where she sings | sung renders |
| `mute`, `cutaway` | render of a shot where she is silent, or anything else | plate renders |
| `still`, `edit` | a first frame or an edit of one | still edits |
| `test` | a model or graph tried out | model tests |

Any other kind counts in the film's total GPU hours only, and the report names it.

## Rules for writers and readers

- A job may have more than one line: one when it is planned or starts, one when it ends. The **last line for a
  `job_id` wins**. A writer never edits or deletes earlier lines.
- Extra fields are allowed and ignored by the reader, with one exception: `video_seconds` (a number of seconds,
  0 or more, or null), the length of the video a render made. When present it gives the film's rendered-to-finished
  ratio; without it that line of the report reads "unknown".
- A blank line is skipped. Any other line that is not a JSON object with the nine fields and the types above is an
  error, reported with its line number (a line cut off by a crash mid-write shows up this way).
- GPU hours: `gpu_seconds` where present, else `finished` minus `started` (wall time, which includes any wait in the
  queue, so the report marks it as an upper bound). `planned` jobs count no time.
