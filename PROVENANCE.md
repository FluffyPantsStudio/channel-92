# Provenance

This kit is a clean-room rebuild of tools its authors had used before (`docs/clean-room.md`).

## The process

- Specs were written first, by people who had used the earlier tools. They describe behaviour (inputs, outputs, the
  numbers measured on our own films, the tests a stage must pass), not code.
- Each builder session worked from the specs, our own film data and our own scripts. No builder opened the earlier
  code, its notes, its documentation, its website or its download.
- Every name, comment, docstring, file layout and data format was written fresh. Names that a spec took over from the
  earlier tools' vocabulary were replaced by the kit's own (2026-11-19).
- Tests came first for each stage. Test data that came from our first film stays outside this repository and is read
  only when `FLIX_FIRST_FILM` points at it (`docs/first-film-replay.md`); the tests in git use synthetic data.
- A checker who is not a builder runs `tools/similarity.py OLD NEW` against the earlier code before any release. It
  reports positions on the new side only, and anything flagged is rewritten from the spec, never from the earlier text.

Each session kept a detailed record of what it read and what it did not open. Those records name private folders
and files, so they are kept out of the public tree, with the maintainers.

## Which spec each module was written from

| Module | Written from |
|---|---|
| `project`, `gates`, `compare` | core spec section 8 (project folder, gates, comparison), the roadmap, the lessons ledger, the first film's measured baseline |
| `runner` | core spec (runner, scheduling, job ledger), the roadmap; our own job statistics for the gate-5 hours |
| `place` | core spec (placing a take on the song by its sound) |
| `timing`, `barmap` | core spec (timing, beats and bars); the first film's stems and timing files as test data |
| `plan`, `prompts`, `lint`, `data/` | core spec (plan, prompts, preflight), the lessons ledger (the rules and their cases) |
| `cut`, `review` | core spec (cut, flash check, review boards) |
| `grade` | core spec (grade); our own grading script as a reference for behaviour, the code written fresh |
| `scenes` | scenes-and-tools spec; our own lab scripts for the street example and the textures as references |
| `cli`, packaging, `tools/` | core spec, the roadmap |

The specs are the core spec (`KIT-SPEC-core`), the scenes-and-tools spec (`KIT-SPEC-scenes-and-tools`), the
roadmap (`KIT-ROADMAP`) and the lessons ledger. They are not part of this repository.
