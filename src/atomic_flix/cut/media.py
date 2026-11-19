"""ffmpeg and ffprobe through subprocess: probe a clip, read its frames into numpy, write frames and pictures.

Every rescale in the kit goes through `SCALE_FLAGS` (accurate rounding, full chroma, bit-exact), so a picture is not
darkened or shifted by a conversion.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np

SCALE_FLAGS = "bicubic+accurate_rnd+full_chroma_int+bitexact"
ENCODER_EXE = "ffmpeg"
FFPROBE = "ffprobe"
ERROR_TAIL = 600
SEEK_AFTER_FRAMES = 120   # past this many frames, seek near the start frame instead of decoding from the top


class MediaError(RuntimeError):
    """ffmpeg or ffprobe failed, or a file is not a readable picture or clip."""


@dataclass(frozen=True)
class ClipInfo:
    width: int
    height: int
    fps: float
    frames: int

    @property
    def seconds(self) -> float:
        return self.frames / self.fps if self.fps else 0.0


def _rate(text: str | None) -> float:
    if not text or text in ("0/0", "0"):
        return 0.0
    return float(Fraction(text))


def probe(path) -> ClipInfo:
    """Size, frame rate and frame count of a clip's first video stream (a still counts as one frame)."""
    command = [FFPROBE, "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,duration",
               "-show_entries", "format=duration", "-of", "json", str(path)]
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise MediaError(f"ffprobe could not read {path}: {done.stderr.strip()[-ERROR_TAIL:]}")
    data = json.loads(done.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise MediaError(f"{path}: no video stream")
    stream = streams[0]
    fps = _rate(stream.get("avg_frame_rate")) or _rate(stream.get("r_frame_rate"))
    frames = int(stream["nb_frames"]) if str(stream.get("nb_frames", "")).isdigit() else 0
    if frames == 0:
        duration = stream.get("duration") or (data.get("format") or {}).get("duration")
        frames = int(round(float(duration) * fps)) if duration and fps else 1
    return ClipInfo(width=int(stream["width"]), height=int(stream["height"]), fps=fps, frames=frames)


def _decode_command(path, size, grey, start_frame, count, fps, extra_filters) -> list[str]:
    filters = list(extra_filters)
    seek: list[str] = []
    skip = int(start_frame)
    if skip > SEEK_AFTER_FRAMES:
        # Seek to half a frame before a frame one second early, then count the rest exactly with trim: the first
        # frame after an accurate seek is the first whose time is at or past the seek point.
        rate = probe(path).fps
        if rate:
            lead = int(round(rate))
            seek = ["-ss", f"{(skip - lead - 0.5) / rate:.6f}"]
            skip = lead
    if skip:
        filters.insert(0, f"trim=start_frame={skip},setpts=PTS-STARTPTS")
    if fps:
        filters.append(f"fps={fps}")
    if size:
        filters.append(f"scale={size[0]}:{size[1]}:flags={SCALE_FLAGS}")
    command = [ENCODER_EXE, "-v", "error", "-nostdin", *seek, "-i", str(path)]
    if filters:
        command += ["-vf", ",".join(filters)]
    if count is not None:
        command += ["-frames:v", str(int(count))]
    command += ["-fps_mode", "passthrough", "-sws_flags", SCALE_FLAGS,
                "-f", "rawvideo", "-pix_fmt", "gray" if grey else "rgb24", "-"]
    return command


def _output_size(path, size, extra_filters) -> tuple[int, int]:
    if size:
        return int(size[0]), int(size[1])
    if extra_filters:
        raise MediaError("give an output size when filters change the picture")
    info = probe(path)
    return info.width, info.height


def iter_frames(path, *, size=None, grey: bool = False, start_frame: int = 0, count: int | None = None,
                fps: float | None = None, wanted: Iterable[int] | None = None,
                extra_filters: Iterable[str] = ()) -> Iterator[tuple[int, np.ndarray]]:
    """Decode a clip once, yielding (frame index, frame). With `wanted`, only those indices are yielded.

    Indices count from `start_frame`. Frames are uint8, (h, w) grey or (h, w, 3) RGB.
    """
    extra = tuple(extra_filters)
    width, height = _output_size(path, size, extra)
    depth = 1 if grey else 3
    frame_bytes = width * height * depth
    keep = None if wanted is None else set(int(i) for i in wanted)
    last_wanted = max(keep) if keep else None
    command = _decode_command(path, (width, height) if (size or extra) else None, grey, start_frame, count, fps,
                              extra)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    index = int(start_frame)
    stopped_early = False
    try:
        while True:
            raw = process.stdout.read(frame_bytes)
            if len(raw) < frame_bytes:
                break
            if keep is None or index in keep:
                frame = np.frombuffer(raw, np.uint8).reshape((height, width) if grey else (height, width, 3))
                yield index, frame
            index += 1
            if last_wanted is not None and index > last_wanted:
                stopped_early = True
                break
    finally:
        if stopped_early or process.poll() is None:
            process.kill()
        _, err = process.communicate()
    if not stopped_early and process.returncode not in (0, None) and index == start_frame:
        raise MediaError(f"ffmpeg could not read {path}: {err.decode(errors='replace').strip()[-ERROR_TAIL:]}")


def read_frames(path, *, size=None, grey: bool = False, start_frame: int = 0, count: int | None = None,
                fps: float | None = None, extra_filters: Iterable[str] = ()) -> np.ndarray:
    """All decoded frames as one array: (n, h, w) grey or (n, h, w, 3) RGB."""
    frames = [frame for _, frame in iter_frames(path, size=size, grey=grey, start_frame=start_frame, count=count,
                                                fps=fps, extra_filters=extra_filters)]
    if not frames:
        raise MediaError(f"{path}: no frames decoded")
    return np.stack(frames)


def write_video(path, frames: np.ndarray, fps: float, *, crf: int = 16, x264_speed: str = "medium") -> Path:
    """Encode RGB frames (n, h, w, 3) to an H.264 clip in one encode."""
    data = np.ascontiguousarray(frames, dtype=np.uint8)
    count, height, width, _ = data.shape
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    command = [ENCODER_EXE, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
               "-r", str(fps), "-i", "-", "-sws_flags", SCALE_FLAGS, "-c:v", "libx264", "-preset", x264_speed,
               "-crf", str(crf), "-pix_fmt", "yuv420p", str(out)]
    done = subprocess.run(command, input=data.tobytes(), capture_output=True)
    if done.returncode != 0:
        raise MediaError(f"ffmpeg could not write {out}: {done.stderr.decode(errors='replace')[-ERROR_TAIL:]}")
    return out


def write_image(path, picture: np.ndarray, *, jpeg_q: int = 2) -> Path:
    """Write one RGB picture (h, w, 3) as JPEG or PNG, chosen by the file's extension."""
    data = np.ascontiguousarray(picture, dtype=np.uint8)
    height, width = data.shape[:2]
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    command = [ENCODER_EXE, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
               "-i", "-", "-frames:v", "1", "-sws_flags", SCALE_FLAGS]
    if out.suffix.lower() in (".jpg", ".jpeg"):
        command += ["-q:v", str(jpeg_q), "-pix_fmt", "yuvj444p"]
    command += ["-update", "1", str(out)]
    done = subprocess.run(command, input=data.tobytes(), capture_output=True)
    if done.returncode != 0:
        raise MediaError(f"ffmpeg could not write {out}: {done.stderr.decode(errors='replace')[-ERROR_TAIL:]}")
    return out


def run_ffmpeg(command: list[str], what: str) -> subprocess.CompletedProcess:
    """Run an ffmpeg command, raising MediaError with the tail of its log on failure."""
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise MediaError(f"ffmpeg failed to {what}: {done.stderr.strip()[-ERROR_TAIL:]}")
    return done
