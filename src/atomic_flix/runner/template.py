"""ComfyUI graph templates with `$name` placeholders, their sidecars, and the checks made before queueing.

A template is a graph saved from ComfyUI with "Export (API)": a mapping of node id to node. Any string value that is
exactly `$name` is replaced by the value itself, keeping its type (a seed stays a number); a `$name` inside a longer
string is pasted in as text (`"flix/$save_as"`). The graph's sidecar `<graph>.meta.json` says what the graph needs,
the model's frame multiple and how much commit charge loading it costs:

    {"format": "atomic-flix/graph-meta@1", "kind": "video", "needs": ["wording", "opening_still", "audio"],
     "frame_multiple": 8, "commit_gb": 30, "size_step": 32}

A graph that does not say what it costs is not taken as free: without a sidecar, or without `commit_gb`, it counts as
a heavy load of UNSTATED_COMMIT_GB (30 GB), held by the load gate and the headroom floor. A graph that really loads
nothing big says so with `"light": true` (its `commit_gb` is then 0); `commit_gb` 0 without `light` is refused, so a
typo cannot switch the gates off. Sizes follow `sizes.py`: the sidecar's `size_step`, by default 32, or 128 for a
graph that takes a control video (`$video`).

Every name here is the kit's own; a graph that declares other names for the same inputs gets a name map
(`names.py`), passed as `names` to `check_request` and `fill`.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..formats import tag
from ..sizes import CONTROL_VIDEO_STEP, GRAPH_STEP, FrameSizeError, check_multiple

PLACEHOLDER = re.compile(r"\$([a-z][a-z_]*[0-9]*)")
IMAGE_SLOT = re.compile(r"image([0-9]+)")

FILE_SLOTS = frozenset({"opening_still", "closing_still", "audio", "likeness", "video"})
RENDER_NEEDS = ("wording", "opening_still")
META_FORMAT = tag("graph-meta")
META_KEYS = frozenset({"format", "needs", "frame_multiple", "commit_gb", "kind", "size_step", "light"})
UNSTATED_COMMIT_GB = 30.0
ALWAYS_NEEDED = ("seed", "save_as")


class TemplateError(ValueError):
    """A graph or a request that must not be queued."""


@dataclass(frozen=True)
class GraphMeta:
    """What a graph's sidecar says. `kind` is "video" (a video from a first frame) or "still"."""

    needs: tuple[str, ...] = ()
    frame_multiple: int = 8
    commit_gb: float = UNSTATED_COMMIT_GB
    kind: str = "video"
    size_step: int = GRAPH_STEP


def is_file_slot(name: str) -> bool:
    return name in FILE_SLOTS or IMAGE_SLOT.fullmatch(name) is not None


def load_graph(path: str | Path) -> dict:
    """Read an API-format graph; refuse the editor's format."""
    graph = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(graph, dict):
        raise TemplateError(f"{path}: not a ComfyUI graph (expected an object of nodes)")
    if "nodes" in graph and "links" in graph:
        raise TemplateError(f"{path} is the editor's format; in ComfyUI save it with Workflow > Export (API)")
    return graph


def _default_step(graph_path: Path) -> int:
    """CONTROL_VIDEO_STEP for a graph that takes a control video, else GRAPH_STEP."""
    try:
        takes_video = "video" in placeholders(json.loads(graph_path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        takes_video = False
    return CONTROL_VIDEO_STEP if takes_video else GRAPH_STEP


def _commit_gb(raw: dict, sidecar: Path) -> float:
    light = raw.get("light", False)
    if not isinstance(light, bool):
        raise TemplateError(f"{sidecar}: light must be true or false, not {light!r}")
    if "commit_gb" not in raw:
        return 0.0 if light else UNSTATED_COMMIT_GB
    value = float(raw["commit_gb"])
    if light and value > 0:
        raise TemplateError(f"{sidecar}: a light graph has no commit_gb; drop one of them")
    if value <= 0 and not light:
        raise TemplateError(f"{sidecar}: commit_gb {raw['commit_gb']!r} would skip the load gate; a graph that loads "
                            "nothing big says \"light\": true")
    return 0.0 if light else value


def load_meta(graph_path: str | Path) -> GraphMeta:
    """Read `<graph>.meta.json` next to the graph; a graph without one is a heavy load of UNSTATED_COMMIT_GB."""
    graph_path = Path(graph_path)
    sidecar = graph_path.with_suffix(".meta.json")
    if not sidecar.exists():
        return GraphMeta(size_step=_default_step(graph_path))
    raw = json.loads(sidecar.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TemplateError(f"{sidecar}: expected an object")
    unknown = sorted(set(raw) - META_KEYS)
    if unknown:
        raise TemplateError(f"{sidecar}: unknown key(s) {', '.join(unknown)}; a sidecar holds {', '.join(sorted(META_KEYS))}")
    if raw.get("format", META_FORMAT) != META_FORMAT:
        raise TemplateError(f"{sidecar}: format {raw.get('format')!r} is not {META_FORMAT!r}")
    return GraphMeta(
        needs=tuple(raw.get("needs", ())),
        frame_multiple=int(raw.get("frame_multiple", 8)),
        commit_gb=_commit_gb(raw, sidecar),
        kind=str(raw.get("kind", "video")),
        size_step=int(raw["size_step"]) if "size_step" in raw else _default_step(graph_path),
    )


def _strings(node: Any):
    if isinstance(node, str):
        yield node
    elif isinstance(node, Mapping):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def placeholders(graph: Any) -> set[str]:
    """Every placeholder name used anywhere in the graph."""
    return {name for text in _strings(graph) for name in PLACEHOLDER.findall(text)}


def fill(graph: Any, values: Mapping[str, Any], names: Any = None) -> Any:
    """A new graph with known placeholders set; unknown ones are left as written. `values` are keyed by the kit's
    names; `names` (a `names.GraphNames`) says what the graph calls them when it differs."""
    return _fill(graph, names.for_graph(values) if names is not None else values)


def _fill(graph: Any, values: Mapping[str, Any]) -> Any:
    if isinstance(graph, Mapping):
        return {key: _fill(value, values) for key, value in graph.items()}
    if isinstance(graph, list):
        return [_fill(value, values) for value in graph]
    if not isinstance(graph, str):
        return graph
    whole = PLACEHOLDER.fullmatch(graph)
    if whole and whole.group(1) in values:
        return values[whole.group(1)]
    return PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), graph)


def frames_for(seconds: float, fps: float, step: int) -> int:
    """Frame count for a render: seconds x fps rounded up to the model's step, plus one."""
    if step < 1:
        raise TemplateError(f"frame step must be at least 1, not {step}")
    return math.ceil(round(seconds * fps, 6) / step) * step + 1


def check_size(width: int, height: int, step: int) -> None:
    """The graph's size rule (`sizes.check_multiple` with the sidecar's step), as a TemplateError."""
    try:
        check_multiple(width, height, step)
    except FrameSizeError as problem:
        raise TemplateError(str(problem)) from None


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def check_request(graph: Mapping, meta: GraphMeta, values: Mapping[str, Any], *, vocal: bool,
                  silent_ok: bool = False, names: Any = None) -> None:
    """Raise TemplateError if this graph must not be queued with these values. Makes no network call. Every name
    checked is the kit's: the graph's own names are read through `names` (a `names.GraphNames`) when given."""
    used = names.kit_names(placeholders(graph)) if names is not None else placeholders(graph)
    if meta.kind == "video":
        absent = [name for name in RENDER_NEEDS if name not in used]
        if absent:
            raise TemplateError(f"a render graph needs ${' and $'.join(absent)}")
    elif "wording" not in used:
        raise TemplateError("a graph needs $wording")
    absent = [name for name in ALWAYS_NEEDED if name not in used]
    if absent:
        raise TemplateError(f"the graph has no ${' or $'.join(absent)}: ComfyUI skips a graph it has already run "
                            "unchanged and saves nothing")
    if vocal and "audio" not in used and not silent_ok:
        raise TemplateError("a vocal task on a graph without $audio: the render would never hear her line "
                            "(allow it with silent_ok)")
    images_given = sorted(int(m.group(1)) for k in values if (m := IMAGE_SLOT.fullmatch(k)) and not _missing(values[k]))
    image_slots = sorted(int(m.group(1)) for k in used if (m := IMAGE_SLOT.fullmatch(k)))
    if len(images_given) > len(image_slots):
        raise TemplateError(f"{len(images_given)} input images but the graph has {len(image_slots)} image slot(s): "
                            "a reference would be ignored")
    wanted = sorted(used | set(meta.needs))
    empty = [name for name in wanted if _missing(values.get(name))]
    if empty:
        raise TemplateError(f"no value for ${', $'.join(empty)}: an empty input is never sent")
