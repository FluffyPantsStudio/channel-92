"""Run Blender headless on a scene and keep the time each frame took.

Blender is only ever a subprocess here. Its path comes from FLIX_BLENDER, else the usual Blender 5.2 install
folder, else `blender` on PATH.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from statistics import mean
from typing import Sequence

from .library import Library
from .plan import write_job
from ..formats import stamped
from ..programs import command_of, find_program

RUN_SCRIPT = Path(__file__).resolve().parent / "blender_run.py"
DEFAULT_BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")


def find_blender() -> Path:
    env = os.environ.get("FLIX_BLENDER")
    if env:
        if not Path(env).exists():
            raise FileNotFoundError(f"FLIX_BLENDER points at {env}, which does not exist")
        return Path(env)
    if DEFAULT_BLENDER.exists():
        return DEFAULT_BLENDER
    found = find_program("blender")       # the real PATH only, never the current directory (programs.py)
    if found:
        return found
    raise FileNotFoundError("Blender not found: set FLIX_BLENDER to blender.exe")


def blender_command(app_exe: Path, job_path: Path) -> list[str]:
    return [str(app_exe), "-b", "--factory-startup", "--python-exit-code", "1", "-P", str(RUN_SCRIPT),
            "--", str(job_path)]


def parse_frames(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    a, _, b = text.partition(":")
    first, last = int(a), int(b or a)
    if first < 1 or last < first:
        raise ValueError(f"frames {text!r}: expected A:B with 1 <= A <= B")
    return first, last


def summarise(frames: Sequence[dict], renderer: str, w: int, h: int, wall_s: float | None = None) -> dict:
    """Seconds per frame. The first frame carries shader compiling and scene sync, so 'warm' leaves it out.
    warm_fps counts capture plus pass writing as if done one after the other; wall_fps is what the clock saw
    (layers are split on a second thread while the next frame renders)."""
    frame_secs = [fr["render_s"] for fr in frames]
    total_s = [fr["render_s"] + fr.get("post_s", 0.0) for fr in frames]
    warm_render = frame_secs[1:] or frame_secs
    warm_total = total_s[1:] or total_s
    out = {"renderer": renderer, "w": w, "h": h, "frames_rendered": len(frames), "warmup_s": frame_secs[0],
           "mean_render_s": mean(frame_secs), "warm_mean_render_s": mean(warm_render),
           "mean_post_s": mean(fr.get("post_s", 0.0) for fr in frames), "mean_total_s": mean(total_s),
           "warm_fps": 1.0 / mean(warm_total) if mean(warm_total) > 0 else float("inf")}
    if wall_s:
        out["wall_s"] = wall_s
        out["wall_fps"] = len(frames) / wall_s
    return out


def run_blender(job_path: str | Path, app_exe: Path | None = None) -> str:
    app_exe = app_exe or find_blender()
    cmd = blender_command(app_exe, Path(job_path))
    proc = subprocess.run(command_of(cmd), capture_output=True, text=True, encoding="utf-8", errors="replace")
    log = proc.stdout + proc.stderr
    Path(job_path).with_name("blender.log").write_text(log, encoding="utf-8")
    if proc.returncode != 0:
        tail = "\n".join(log.splitlines()[-25:])
        raise RuntimeError(f"Blender failed (exit {proc.returncode}); see {Path(job_path).with_name('blender.log')}\n"
                           f"{tail}")
    return log


def capture_scene(scene_path: str | Path, write_to: str | Path, renderer: str | None = None,
                 frames: Sequence[int] | None = None, quick: bool = False, samples: int | None = None,
                 size: Sequence[int] | None = None, keep_exr: bool = False, app_exe: Path | None = None,
                 library: Library | None = None) -> dict:
    """Compile, capture and time a scene; returns the summary that is also merged into OUT/capture.json."""
    job_path = write_job(scene_path, write_to, renderer=renderer, frames=frames, quick=quick, samples=samples,
                         size=size, keep_exr=keep_exr, library=library)
    run_blender(job_path, app_exe)
    out = Path(write_to)
    info = json.loads((out / "capture.json").read_text(encoding="utf-8"))
    summary = summarise(info["frames"], info["renderer"], info["w"], info["h"], info.get("wall_s"))
    info.update(summary)
    (out / "capture.json").write_text(json.dumps(stamped("capture", info), indent=1) + "\n", encoding="utf-8")
    return info


def blend_scene(scene_path: str | Path, blend_path: str | Path, write_to: str | Path | None = None,
                app_exe: Path | None = None, library: Library | None = None) -> Path:
    """Build the scene in Blender and save it as a .blend for a person to open."""
    blend_path = Path(blend_path).resolve()
    out = Path(write_to) if write_to else blend_path.parent
    run_blender(write_job(scene_path, out, blend=blend_path, library=library), app_exe)
    return blend_path
