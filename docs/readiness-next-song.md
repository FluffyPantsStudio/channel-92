# Readiness for the next song, 2026-11-19

Status: the kit is built and reviewed on disk, not committed, not pushed.

## Checks that pass today
- Fast suite 1032 passed, 3 skipped. First-film replay 24 passed, 2 expected failures (timing gates, below).
- Similarity against the old toolkit: PASS with no allow-list (prose 0, code 0, distinctive names 0.1%, keys 0%).
- Code review (15 findings) and security review (2 high, medium ones) fixed with tests: `docs/fixes-2026-11-19.md`.
- A dry run of the next song validates the folder and names what is missing (`tools/new_song_checklist.md`).

## What the user must supply
1. Stems of the exact take: mix, lead vocal, instrumental, and a drum stem if one exists (the bar's one is weaker without it); the restored master.
2. The concept: a pick from three pitches, or the person's own plot, and which characters each shot shows.
3. The lyric as sung (repeats, scat line, backing).
4. The singer's one-sentence identity from canon, approved.
5. Answers at the six gates, recorded word for word.
6. Style for this clip: Japanese anime (the model bake-off needs the user's go-ahead for about 60 GB of downloads).

## Known limits (honest list)
- Timing gates are not met on the first film (34 of 56 lines within 0.10 s with labels; target 40). Every uncertain line is flagged for the ear; expect hand fixes.
- The bar's one needs an ear check against the click track (`tools/click.py`) at gate 2.
- Gate answers are bookkeeping, not authentication.
- LTX loads: one at a time unless commit headroom allows more; the runner now enforces this and refuses unknown graphs.
- SCAIL-2 over Blender plates tested to 81 frames only; longer clips need chunking.
- Blender depth guide and pose colours not compared with the depth model and pose graph in use.
- Ledger appends are not serialised across separate runner processes (one runner at a time).
- `data/lessons.json` still carries first-film file names (private relative paths); scrub before the public push.
- Any gate-5 yes recorded before the review fixes must be asked again.

## Before a public push (user decisions)
- Licence (MIT or Apache-2.0), repo name, whether PROVENANCE names the earlier tool (default: no; notes kept in git-ignored `docs/private/`).
- Check `git status` for `fixtures/`, `out/`, `docs/private/` ignored; never `git add -f`.
