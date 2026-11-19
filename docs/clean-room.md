# How this code was written

This kit is a clean-room rebuild of tools we had used before.

1. **Specs first, written separately.** People who had used the earlier tools wrote down what each stage must do:
   its inputs, outputs, the numbers measured on our own films, and the tests it must pass. The specs describe
   behaviour, not code.
2. **Builders read only the specs and our own data.** The people and agents who write this code work from those
   specs, our own film data and our own scripts. They do not open the earlier code, its documentation or its
   website. Each session records what it read in `PROVENANCE.md`.
3. **Original code.** Every name, comment, docstring, file layout and data format here is written fresh from the
   spec. Where the spec names a JSON key, a value or a command, we choose our own name for it: the specs' authors
   had read the earlier tools, so their names may be that code's vocabulary (2026-11-19; the maintainers' renames table, kept privately in `docs/private/`).
4. **Tests first.** Each stage starts from the spec's tests, seen to fail, then made to pass.
5. **Similarity check before release.** A checker who is not a builder runs `tools/similarity.py OLD NEW` against
   the earlier code after Phase 1 and again before any public release. It reports positions on the new side only.
   Anything it flags goes back to a builder as "rewrite this part of this file from that spec section", never with
   the earlier text.

## What the similarity check measures, and when it passes

| Check | What is compared | Passes when |
|---|---|---|
| names | Function, class, argument, variable and assigned attribute names, case and underscores ignored, after removing Python keywords, builtins, standard-library and numpy names, dunder names and a short list of conventional names (`args`, `path`, `main`...) and domain words (`bpm`, `fps`, `lufs`...) | under 5 % of the new tree's distinctive names (six letters or more, or an underscore inside, outside the standard words in `docs/shared-vocabulary.md`) also occur in the old tree; the strict share of every name is printed beside it |
| prose | Docstrings, comments, string literals of five or more words, Markdown and text files: normalised sentences of five or more words, and every run of six words with at least three that are not common small words | zero shared sentences and zero shared 6-word runs, after cutting out the standard phrases listed in `docs/shared-vocabulary.md` (WCAG terms, ffmpeg options, loudness units) |
| code | Python lines with comments, docstrings, imports, blank and bracket-only lines removed; every window of 8 lines with at least 4 distinct lines, compared as written and again with names as `ID` and literals as `LIT` | zero literal runs; shape runs cover under 1 % of the new code lines and none is longer than 12 lines |
| keys | JSON key names (from `.json` files and string keys in Python) plus CLI verbs and `--flags`, after a short generic list (`name`, `path`, `--help`...) | under 5 % of the distinctive keys (six letters or more, or an underscore or hyphen inside, outside the standard keys: ffprobe fields, HTTP headers, ComfyUI API fields, common flags) also occur in the old set; the strict share is printed beside it |

The name share is measured against the new tree's names, so it is stricter than a Jaccard index of the same value
(Jaccard can never exceed it). There is no allow-list: a name both trees share counts, whoever named it. The only
names left out of the distinctive measure are those fixed by a standard or another program's interface, each listed
with its reason in `docs/shared-vocabulary.md`, and they still count in the strict number. `--allow FILE` exempts
the names in FILE for a one-off look and prints each; a release check never passes it.

Shape runs from plain boilerplate (argument parsers, ffmpeg command lists) can occur by chance; each one under the
limits is still read and explained by the checker.

Exit code 0 means every check passed.
