"""When two neighbouring shots read as a jump cut. The plan's notes, lint rule C1 and the cut audit all ask here, so
they decide from the same evidence and cannot disagree.

The evidence is the setup name the person gave each shot and its crop size: the share of the setup's widest still
that the shot keeps (1.0 is the whole still, 0.62 a closer crop). Two shots on one setup read as a jump when their
sizes differ by less than SIZE_STEP of the smaller one. Shots on different setups, or with no setup, never do. When
the setup matches but a size was never recorded the answer is None: nobody can tell, and the caller says so.
"""

from __future__ import annotations

SIZE_STEP = 0.2


def shown_size(keep: float | None, reframe_width: float | None = None,
               frame_width: float | None = None) -> float | None:
    """The size a viewer sees: the still's crop size, made smaller again by a reframe (a crop in render pixels)."""
    if keep is None:
        return None
    if reframe_width and frame_width:
        return keep * min(1.0, reframe_width / frame_width)
    return keep


def reads_as_jump(setup_a: str | None, size_a: float | None, setup_b: str | None, size_b: float | None) -> bool | None:
    """True for a jump cut, False for none, None when one setup's sizes are not both known."""
    if not setup_a or setup_a != setup_b:
        return False
    if size_a is None or size_b is None:
        return None
    return abs(size_a - size_b) / min(size_a, size_b) < SIZE_STEP


def size_note(size_a: float, size_b: float) -> str:
    return f"sizes {size_a:g} and {size_b:g}, under {SIZE_STEP:.0%} apart"
