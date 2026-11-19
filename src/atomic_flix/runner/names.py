"""Placeholder names: the kit's own names, and the names a graph file declares.

The kit fills a graph by its own placeholder names (`$wording`, `$opening_still`, `$closing_still`, `$likeness`,
`$save_as`, `$seed`, `$audio`, `$width`...). A graph made for the kit uses them directly. A graph made earlier, with
other names for the same inputs, gets a name map instead of an edit: `<graph>.map.json`, looked for beside the graph,
then in each folder of the `ATOMIC_FLIX_MAPS` environment variable, then in the package's own `workflows/` folder
(`atomic_flix/workflows/`, shipped in the wheel, where the maps for our existing graphs live). The graph file is
never changed.

    {"format": "atomic-flix/graph-map@1", "names": {"wording": "text", "opening_still": "start_image"}}

`names` maps a kit name to the name the graph declares; a kit name not listed is the same in the graph (an optional
`"graph"` key names the graph file the map was written for). Two kit names
may not share one graph name. A map that is unreadable or malformed stops the job before anything is queued.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .template import TemplateError
from ..formats import tag

MAP_FORMAT = tag("graph-map")
MAP_SUFFIX = ".map.json"
MAPS_ENV = "ATOMIC_FLIX_MAPS"
KIT_MAPS = Path(__file__).resolve().parents[1] / "workflows"
NAME = re.compile(r"[a-z][a-z_]*[0-9]*")


class NameMapError(TemplateError):
    """A name map that cannot be used."""


@dataclass(frozen=True)
class GraphNames:
    """Kit name to graph name, for one graph. Names not in `to_graph` are the same on both sides."""

    to_graph: Mapping[str, str] = field(default_factory=dict)
    found_at: str | None = None

    def graph_name(self, kit_name: str) -> str:
        return self.to_graph.get(kit_name, kit_name)

    def kit_name(self, graph_name: str) -> str:
        for kit, declared in self.to_graph.items():
            if declared == graph_name:
                return kit
        return graph_name

    def kit_names(self, graph_names: Iterable[str]) -> set[str]:
        return {self.kit_name(name) for name in graph_names}

    def for_graph(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """The same values keyed by the names the graph declares."""
        return {self.graph_name(name): value for name, value in values.items()}


SAME_NAMES = GraphNames()


def parse_map(raw: Any, where: str) -> GraphNames:
    """Check one map file's content and return its names."""
    if not isinstance(raw, dict) or raw.get("format") != MAP_FORMAT:
        raise NameMapError(f"{where}: not a name map (expected \"format\": \"{MAP_FORMAT}\")")
    names = raw.get("names")
    if not isinstance(names, dict) or not names:
        raise NameMapError(f"{where}: \"names\" must map kit names to graph names")
    bad = [f"{k!r}: {v!r}" for k, v in names.items()
           if not (isinstance(k, str) and isinstance(v, str) and NAME.fullmatch(k) and NAME.fullmatch(v))]
    if bad:
        raise NameMapError(f"{where}: not placeholder names: {', '.join(bad)}")
    taken = [v for v in set(names.values()) if list(names.values()).count(v) > 1]
    if taken:
        raise NameMapError(f"{where}: two kit names map to ${', $'.join(sorted(taken))}")
    return GraphNames(dict(names), where)


def _candidates(graph_path: Path) -> list[Path]:
    name = graph_path.with_suffix(MAP_SUFFIX).name
    folders = [graph_path.parent] + [Path(p) for p in os.environ.get(MAPS_ENV, "").split(os.pathsep) if p]
    return [folder / name for folder in folders + [KIT_MAPS]]


def load_names(graph_path: str | Path) -> GraphNames:
    """The name map for a graph: the first `<graph>.map.json` found, else the kit's names unchanged."""
    for candidate in _candidates(Path(graph_path)):
        if candidate.is_file():
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError) as err:
                raise NameMapError(f"{candidate}: cannot be read: {err}") from None
            return parse_map(raw, str(candidate))
    return SAME_NAMES
