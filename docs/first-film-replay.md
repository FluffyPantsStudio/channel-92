# Replaying the first film

The kit was measured against our first film (The Girl In The Magic Tub). That film's stems, takes, cuts, sung
prompts and shot list are not in this repository. The tests and tools that use them find them through one
environment variable, and skip or refuse with a plain reason when it is unset.

## `FLIX_FIRST_FILM`

The folder that holds the first film's working tree:

| Under `FLIX_FIRST_FILM` | Read by |
|---|---|
| `films/the-girl-in-the-magic-tub/` (stems, `build/`, `book.json`, `lyric.txt`, `takes/`, `v24-cut.mp4`) | `tools/make_fixtures.py first-film`, `tools/replay_first_film.py`, the place, grade and replay tests |
| `canon/<singer>/singing/shots.json` (the sung shots' prompts as the picked takes were made) | `tests/lint/test_first_film_regression.py` |
| `workflows/` (our ComfyUI graphs) | `tests/runner/test_runner_template.py` (the graph filled through its name map) |
| `baseline.json` (the first film's measured numbers) | `tools/replay_first_film.py` |
| `../src/data/songs.ts` (the site catalog) | `tools/lyric_from_site.py`, as in `tools/new_song_checklist.md` |

Two more local pieces, both git-ignored:

- `fixtures/first-film/`, the fixture pack: a byte copy of the film's stems and timing files with a manifest, made by
  `python tools/make_fixtures.py first-film` (its `--src` defaults to the film folder above).
- `docs/private/first-film/first_film_shots.txt`, the film's shot list rewritten in the kit's format (it has no
  source file in the film's folder), read by the lint regression and the replay. `docs/private/` also keeps the
  maintainers' detailed provenance records and the renames table.

## Running

PowerShell:

    $env:FLIX_FIRST_FILM = "D:/films/flix"
    .venv/Scripts/python.exe tools/make_fixtures.py first-film
    .venv/Scripts/python.exe -m pytest -m first_film
    .venv/Scripts/python.exe tools/replay_first_film.py --quick

POSIX shells: `export FLIX_FIRST_FILM=/path/to/flix`.

With the variable unset, `pytest -m "not first_film"` is the whole fast suite and needs nothing private; the
first-film tests skip with the reason "FLIX_FIRST_FILM is not set". The synthetic equivalents of the lint regression
are in `tests/lint/test_lint_samples.py` (data in `tests/lint/data/sample_*`).
