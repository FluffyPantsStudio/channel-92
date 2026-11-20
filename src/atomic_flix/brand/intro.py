"""The optional intro: a clip joined in front of a finished cut, written to a file of its own.

The intro is scaled to fit the cut's frame and padded with black to fill it, at the cut's frame rate. Its sound is
laid out like the cut's (rate and channels); an intro without sound gets silence of its own length, so the joined
file's sound runs exactly as long as both pictures. The cut itself is only read.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..cut.media import (ENCODER_EXE, ERROR_TAIL, FFPROBE, SCALE_FLAGS, MediaError, input_args, probe, run_ffmpeg,
                         source_args)
from ..programs import command_of

AUDIO_BITRATE = "320k"


class IntroError(ValueError):
    """The intro cannot be joined as given."""


@dataclass(frozen=True)
class Sound:
    rate: int
    channels: int
    layout: str


def _sound_of(path: Path) -> Sound | None:
    """The first audio stream's layout, or None when the file has no sound."""
    command = [FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_entries",
               "stream=sample_rate,channels,channel_layout", "-of", "json", *source_args(path), str(path)]
    done = subprocess.run(command_of(command), capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise MediaError(f"ffprobe could not read {path}: {done.stderr.strip()[-ERROR_TAIL:]}")
    streams = json.loads(done.stdout or "{}").get("streams") or []
    if not streams:
        return None
    stream = streams[0]
    channels = int(stream.get("channels") or 2)
    layout = stream.get("channel_layout") or ("mono" if channels == 1 else "stereo")
    return Sound(rate=int(stream["sample_rate"]), channels=channels, layout=layout)


def _graph(size: tuple[int, int], fps: float, seconds: float, cut_sound: Sound | None,
           intro_sound: Sound | None) -> tuple[str, list[str]]:
    width, height = size
    parts = [f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease:flags={SCALE_FLAGS},"
             f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps:g},format=yuv420p,"
             f"trim=duration={seconds:.6f}[iv]",
             "[1:v]setsar=1,format=yuv420p[cv]"]
    if cut_sound is None:
        parts.append("[iv][cv]concat=n=2:v=1:a=0[v]")
        return ";".join(parts), ["-map", "[v]"]
    layout = f"aformat=sample_rates={cut_sound.rate}:channel_layouts={cut_sound.layout}"
    if intro_sound is None:
        parts.append(f"anullsrc=r={cut_sound.rate}:cl={cut_sound.layout}:d={seconds:.6f}[ia]")
    else:
        parts.append(f"[0:a]aresample={cut_sound.rate},{layout},atrim=duration={seconds:.6f},"
                     f"apad=whole_dur={seconds:.6f}[ia]")
    parts.append(f"[1:a]{layout}[ca]")
    parts.append("[iv][ia][cv][ca]concat=n=2:v=1:a=1[v][a]")
    return ";".join(parts), ["-map", "[v]", "-map", "[a]", "-c:a", "aac", "-b:a", AUDIO_BITRATE]


def join_intro(intro: Path | str, cut: Path | str, out: Path | str, *, crf: int = 16,
               x264_speed: str = "medium") -> Path:
    """Write OUT: INTRO, fitted to CUT's frame and sound, then CUT. Returns OUT (written only on success)."""
    intro, cut, out = Path(intro), Path(cut), Path(out)
    if not intro.is_file():
        raise IntroError(f"no intro clip at {intro}")
    film = probe(cut)
    seconds = probe(intro).seconds
    if seconds <= 0:
        raise IntroError(f"{intro} has no length")
    graph, maps = _graph((film.width, film.height), film.fps, seconds, _sound_of(cut), _sound_of(intro))
    partial = out.with_name(out.stem + ".partial" + out.suffix)
    command = [ENCODER_EXE, "-y", "-v", "error", "-nostdin", *input_args(intro), *input_args(cut),
               "-filter_complex", graph, *maps, "-c:v", "libx264", "-preset", x264_speed, "-crf", str(crf),
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(partial)]
    try:
        run_ffmpeg(command, f"join the intro {intro.name} to {cut.name}")
    except MediaError:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(out)
    return out
