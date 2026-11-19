"""A stand-in for a video model behind the fake ComfyUI: a moving test picture of the asked size and length, with
the uploaded audio as its soundtrack (as LTX-2.3 carries the audio it was given), so a render can be placed by
sound, cut, reviewed and flash-checked without a GPU."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def _inputs(graph: dict, class_type: str) -> dict:
    for node in graph.values():
        if node.get("class_type") == class_type:
            return node.get("inputs", {})
    return {}


def make_clip(graph: dict, files: dict[str, bytes]) -> bytes:
    frames = int(_inputs(graph, "EmptyLTXVLatentVideo").get("length", 25))
    size = _inputs(graph, "ImageScale")
    width, height = int(size.get("width", 320)), int(size.get("height", 192))
    audio_name = _inputs(graph, "LoadAudio").get("audio")
    with tempfile.TemporaryDirectory() as scratch:
        folder = Path(scratch)
        command = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate=24"]
        if audio_name and audio_name in files:
            (folder / "sent.wav").write_bytes(files[audio_name])
            command += ["-i", str(folder / "sent.wav"), "-c:a", "aac", "-b:a", "192k"]
        else:
            command += ["-an"]
        command += ["-frames:v", str(frames), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    str(folder / "out.mp4")]
        subprocess.run(command, check=True, capture_output=True)
        return (folder / "out.mp4").read_bytes()
