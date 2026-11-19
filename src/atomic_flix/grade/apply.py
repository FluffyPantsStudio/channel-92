"""Write the graded film: decode the cut once as raw yuv420p, grade each frame by its shot's tables, encode once.

The picture never leaves the cut's YUV planes (no RGB round trip, no rescale), so nothing but the grade and the one
encode touches it. The cut's sound is copied through untouched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

import numpy as np

from ..cut.media import ERROR_TAIL, ENCODER_EXE, MediaError, probe
from .correct import IDENTITY, Correction, Look, grade_planes, luma_table, tint_tables
from .measure import ShotSpan


def _frame_owner(shots: Sequence[ShotSpan], count: int) -> np.ndarray:
    """For each frame of the cut, the index of its shot (-1 for a frame outside every shot)."""
    owner = np.full(count, -1, dtype=np.intp)
    for index, shot in enumerate(shots):
        owner[max(0, shot.frame_in):min(count, shot.end_frame)] = index
    return owner


def _encoder(out: Path, provenance: Path, size: tuple[int, int], fps: float, crf: int, x264_speed: str) -> list[str]:
    width, height = size
    return [ENCODER_EXE, "-y", "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "yuv420p",
            "-s", f"{width}x{height}", "-r", f"{fps:g}", "-i", "-", "-i", str(provenance),
            "-map", "0:v", "-map", "1:a?", "-c:a", "copy", "-c:v", "libx264", "-preset", x264_speed, "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]


def write_graded(cut: Path | str, out: Path | str, shots: Sequence[ShotSpan], corrections: Sequence[Correction],
                 look: Look, *, crf: int = 16, x264_speed: str = "slow") -> Path:
    cut, out = Path(cut), Path(out)
    info = probe(cut)
    width, height = info.width, info.height
    if width % 2 or height % 2:
        raise MediaError(f"{cut}: {width}x{height} is not an even size; yuv420p needs one")
    by_key = {c.key: c for c in corrections}
    tables = [luma_table(by_key.get(shot.key, IDENTITY), look) for shot in shots]
    gains = [by_key.get(shot.key, IDENTITY).gain for shot in shots]
    plain = luma_table(IDENTITY, look)
    tints = tint_tables(look)
    owner = _frame_owner(shots, info.frames + 1)
    luma_bytes, chroma_bytes = width * height, (width // 2) * (height // 2)
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.stem + ".partial" + out.suffix)
    decoder = subprocess.Popen([ENCODER_EXE, "-v", "error", "-nostdin", "-i", str(cut), "-fps_mode", "passthrough",
                                "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    encoder = subprocess.Popen(_encoder(partial, cut, (width, height), info.fps, crf, x264_speed), stdin=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    frame = 0
    try:
        while True:
            raw = decoder.stdout.read(luma_bytes + 2 * chroma_bytes)
            if len(raw) < luma_bytes + 2 * chroma_bytes:
                break
            data = np.frombuffer(raw, np.uint8)
            y = data[:luma_bytes].reshape(height, width)
            u = data[luma_bytes:luma_bytes + chroma_bytes].reshape(height // 2, width // 2)
            v = data[luma_bytes + chroma_bytes:].reshape(height // 2, width // 2)
            index = owner[frame] if frame < len(owner) else -1
            table, gain = (tables[index], gains[index]) if index >= 0 else (plain, 1.0)
            for plane in grade_planes(y, u, v, table, gain, tints):
                encoder.stdin.write(np.ascontiguousarray(plane).tobytes())
            frame += 1
    finally:
        decoder.stdout.close()
        decode_error = decoder.stderr.read().decode(errors="replace")
        decoder.stderr.close()
        decoder.wait()
        encoder.stdin.close()
        encode_error = encoder.stderr.read().decode(errors="replace")
        encoder.stderr.close()
        encoder.wait()
    if decoder.returncode != 0 or encoder.returncode != 0 or frame == 0:
        partial.unlink(missing_ok=True)
        raise MediaError(f"the graded film was not written: {(decode_error + encode_error).strip()[-ERROR_TAIL:]}")
    partial.replace(out)
    return out
