# The six gates: what an answer on record does and does not prove

A film passes six gates (concept, the song by ear, her face and looks, the board, the hours, v1), and the kit
refuses to go past one without the person's answer on record in `standing.json` and, word for word, in `notes.md`.

## How an answer arrives

Every answer records how it reached the kit:

| provenance | how | shown as |
| --- | --- | --- |
| `person-direct` | `atomic-flix gate FILM answer GATE` with no `--words`, at a terminal: the person types their name and words | typed by the person |
| `relayed` | `--by NAME --words "..."` on the command line: whoever ran the command passed the person's words on, quoted exactly | relayed, the person's words quoted |
| `person` | `Answer(...)` through the Python API, which does not say | how it arrived not recorded |

Gates accept all three; `progress` (and the gate commands' own output) shows which one each passed gate holds, and
`notes.md` says it beside the words. A relayed answer needs the words (an empty quote is refused) and a name; a name
that reads as a model or an agent (`Claude`, `claude2`, `Claude-Opus`, `assistant_7`, `AGENT007`, `the model`,
`GPT4o`, any case, with digits or a plural or -bot ending) is refused, whichever way the answer arrived.

A stored answer without `approves` counts as a refusal, and an answer dated before the question it answers is
refused, both when it is made and when `standing.json` is read back.

A reply typed by the director in the Claude app and taken with `atomic-flix desk` is recorded as `relayed`, and
`notes.md` adds that it arrived that way (`docs/desk.md`).

## The limit: this is bookkeeping, not authentication

A program cannot prove who typed. `person-direct` only means the words came in on a terminal the command was
attached to; an agent driving a pseudo-terminal, or anyone at the keyboard, looks the same. `relayed` is the honest
label for the usual case of a driver passing on what the person said. The name in `--by` is whatever was typed.
Nothing here signs or checks an identity, and a person with write access to the film folder can edit
`standing.json` by hand.

What the record does give: the person's words, kept exactly; when they were given against when the question was
asked; how they arrived; and refusals for the plain mistakes (an agent signing its own name, an empty answer, a
missing yes, a time that runs backwards). Treat it as a ledger kept in good faith, and keep the gates where the
person really sees the work.

## Gate 5 binds one batch

A yes at gate 5 copies the batch it approved from `plan/budget.json` into `standing.json`: its takes, frame size
and GPU seconds. `shoot` (and `python -m atomic_flix.runner plan`/`shoot` on a film folder) plans takes against
it, at most as many as it covers, and only for the same plan; every planned job carries the approval it was
planned under, and a planned job from another approval is refused. A changed plan or a second batch needs the gate
reopened (`atomic-flix gate FILM reopen spend --reason "..."`), asked and answered again. Lint's hours check (L127)
reads the approved hours, not the budget file as it is now.
