"""The six points where a person decides, in the order a film meets them."""

from __future__ import annotations

from dataclasses import dataclass


class GateRefused(ValueError):
    """The kit will not take this step: a gate lacks the person's answer, or an answer is not acceptable."""


@dataclass(frozen=True)
class GateSpec:
    """One gate: what the person is shown and the single question put to them."""

    id: str
    number: int
    title: str
    shows: str
    question: str


GATES: tuple[GateSpec, ...] = (
    GateSpec("concept", 1, "concept",
             "three pitches of at most 120 words each: premise, the one visual device every shot carries, "
             "the arc, one risk",
             "Which pitch is the film?"),
    GateSpec("song", 2, "the song, by ear",
             "the song itself, played to the person with a click on the bar's one; never a description or a "
             "measurement of it",
             "Is this the finished song, with the click on the one where you count it?"),
    GateSpec("looks", 3, "her face and looks",
             "the reference sheet and one or two first frames, at full size",
             "Is this her?"),
    GateSpec("board", 4, "the board",
             "every shot's first frame, its time on the song and its lines, on one sheet",
             "Is this the film you want rendered?"),
    GateSpec("spend", 5, "prompts and render time",
             "the prompts, how many renders, at what size, and the GPU hours this machine's log says they take",
             "May this batch run for these hours?"),
    GateSpec("v1", 6, "v1",
             "the cut, after a cold reviewer found no clear errors in it (or the reviewer's list, if the rounds "
             "stopped making progress)",
             "Accept, or what's wrong?"),
)

GATE_IDS: tuple[str, ...] = tuple(spec.id for spec in GATES)


def gate_spec(gate: str) -> GateSpec:
    """The gate named GATE; an unknown name is refused."""
    for spec in GATES:
        if spec.id == gate:
            return spec
    raise GateRefused(f"there is no gate called {gate!r}; the gates are {', '.join(GATE_IDS)}")
