"""The one frame-size rule of the kit, shared by the runner and the control clips.

A size passed to a ComfyUI graph follows that graph's sidecar (`size_step`). A control video (the `$video` input of a
union-control graph, made by `scenes controls --for ltx`) must be a multiple of CONTROL_VIDEO_STEP on both sides: the
graph halves the frame and needs even latents there (docs/integration-notes.md), so 1152x640 and 1280x768 work and
1280x704 does not. A graph that takes `$video` and whose sidecar names no step gets CONTROL_VIDEO_STEP.
"""

from __future__ import annotations

CONTROL_VIDEO_STEP = 128
GRAPH_STEP = 32


class FrameSizeError(ValueError):
    """A width or height that breaks the step it must keep."""


def check_multiple(width: int, height: int, step: int, why: str = "") -> None:
    """Refuse a size whose sides are not positive multiples of STEP; WHY is added to the message."""
    if step < 1:
        raise FrameSizeError(f"a size step must be at least 1, not {step}")
    for side, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value % step:
            raise FrameSizeError(f"{width}x{height}: {side} {value} is not a positive multiple of {step}{why}")
