"""Sample graphs for the runner's tests, shaped like our ComfyUI "Export (API)" files."""

from __future__ import annotations

import json
from pathlib import Path

SUNG_GRAPH = {
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "$wording", "clip": ["3", 0]}},
    "10": {"class_type": "LoadImage", "inputs": {"image": "$opening_still"}},
    "11": {"class_type": "ImageScale", "inputs": {"image": ["10", 0], "width": "$width", "height": "$height"}},
    "20": {"class_type": "LoadAudio", "inputs": {"audio": "$audio"}},
    "21": {"class_type": "TrimAudioDuration", "inputs": {"audio": ["20", 0], "duration": "$seconds"}},
    "31": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"length": "$frames", "batch_size": 1}},
    "37": {"class_type": "RandomNoise", "inputs": {"noise_seed": "$seed"}},
    "52": {"class_type": "SaveVideo", "inputs": {"video": ["51", 0], "filename_prefix": "flix/$save_as"}},
}

SILENT_GRAPH = {key: node for key, node in SUNG_GRAPH.items() if key not in ("20", "21")}


def write_graph(folder: Path, name: str, graph: dict, meta: dict | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(json.dumps(graph), encoding="utf-8")
    if meta is not None:
        path.with_suffix(".meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return path
