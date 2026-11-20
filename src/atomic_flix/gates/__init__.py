"""The six human gates of a film, and the cold review rounds before a cut reaches the person.

A person decides at six points and nowhere else: the concept, the song by ear, her face and looks, the board,
prompts and render time, and v1. The kit refuses to go past a gate without the person's answer on record.
"""

from .clock import now_text, parse_time
from .machine import (PERSON, PERSON_DIRECT, PROVENANCES, RELAYED, SCOPES, Answer, GateBook, GateRecord, PastAsk,
                      reads_as_machine)
from .review import ReviewLoop, ReviewRound
from .steps import GATE_IDS, GATES, GateRefused, GateSpec, gate_spec

__all__ = [
    "GATES", "GATE_IDS", "PERSON", "PERSON_DIRECT", "PROVENANCES", "RELAYED", "SCOPES", "Answer", "GateBook",
    "GateRecord", "GateRefused", "GateSpec", "PastAsk", "ReviewLoop", "ReviewRound", "gate_spec", "now_text", "parse_time",
    "reads_as_machine",
]
