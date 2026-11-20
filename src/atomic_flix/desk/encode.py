"""Files for a phone, each under the packet's size cap: JPEG and PNG pictures, the song as AAC, the film at 720p.

A file is brought under the cap only down to a floor (JPEG quality, audio and video bitrate); a file that cannot meet
the cap above its floor is refused by name, never shrunk further.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..cut.media import ENCODER_EXE, MediaError, input_args, probe, run_ffmpeg, write_image
from ..wav import save_wav
from .reply import DeskError

JPEG_QUALITIES = (2, 4, 7)          # ffmpeg's JPEG scale, best first; 7 is the floor
AUDIO_KBPS = (128, 96, 64)          # mono AAC, best first; 64 is the floor
PHONE_SHORT_SIDE = 720
VIDEO_MAX_KBPS = 2500
VIDEO_FLOOR_KBPS = 350
SOUND_KBPS = 128
CAP_SHARE = 0.92                    # aim under the cap: container overhead and rate control drift
MB = 1024 * 1024


def cap_bytes(max_mb: float) -> int:
    if not max_mb or max_mb <= 0:
        raise DeskError(f"--max-mb must be above 0, not {max_mb}")
    return int(max_mb * MB)


def _over(path: Path, cap: int) -> bool:
    return path.stat().st_size > cap


def _refuse(path: Path, cap: int, floor: str) -> DeskError:
    size = path.stat().st_size / MB if path.is_file() else 0.0
    path.unlink(missing_ok=True)
    return DeskError(f"{path.name} cannot meet the {cap / MB:.2f} MB cap above its floor ({floor}; it came to "
                     f"{size:.2f} MB): raise --max-mb, nothing was shrunk further")


def picture_file(path: Path, picture: np.ndarray, cap: int) -> Path:
    """Write PICTURE as JPEG (best quality that fits) or PNG (lossless, as is), under CAP bytes."""
    if path.suffix.lower() == ".png":
        write_image(path, picture)
        if _over(path, cap):
            raise _refuse(path, cap, "PNG is lossless")
        return path
    for quality in JPEG_QUALITIES:
        write_image(path, picture, jpeg_q=quality)
        if not _over(path, cap):
            return path
    raise _refuse(path, cap, f"JPEG quality {JPEG_QUALITIES[-1]}")


def text_file(path: Path, text: str, cap: int) -> Path:
    path.write_text(text, encoding="utf-8", newline="\n")
    if _over(path, cap):
        raise _refuse(path, cap, "text is not shrunk")
    return path


def audio_file(path: Path, samples: np.ndarray, rate: int, cap: int, work: Path) -> Path:
    """Mono SAMPLES as AAC in an .m4a, at the best bitrate that fits under CAP."""
    seconds = len(samples) / rate
    wav = save_wav(work / f"{path.stem}.wav", samples, rate)
    try:
        for kbps in AUDIO_KBPS:
            if kbps * 1000 * seconds / 8 > cap * CAP_SHARE and kbps != AUDIO_KBPS[-1]:
                continue
            run_ffmpeg([ENCODER_EXE, "-y", "-v", "error", *input_args(wav), "-c:a", "aac", "-b:a", f"{kbps}k",
                        "-movflags", "+faststart", str(path)], f"encode {path.name}")
            if not _over(path, cap):
                return path
        raise _refuse(path, cap, f"AAC at {AUDIO_KBPS[-1]} kbps")
    finally:
        wav.unlink(missing_ok=True)


def _scale(width: int, height: int) -> str:
    if width >= height:
        return f"scale=-2:{min(PHONE_SHORT_SIDE, height - height % 2)}"
    return f"scale={min(PHONE_SHORT_SIDE, width - width % 2)}:-2"


def _video_kbps(seconds: float, cap: int) -> int:
    return int(min(VIDEO_MAX_KBPS, cap * CAP_SHARE * 8 / max(seconds, 0.1) / 1000 - SOUND_KBPS))


def video_file(path: Path, source: Path, cap: int) -> Path:
    """SOURCE re-encoded for a phone: the short side at most 720, H.264 and AAC, under CAP bytes."""
    try:
        clip = probe(source)
    except MediaError as problem:
        raise DeskError(str(problem)) from None
    kbps = _video_kbps(clip.seconds, cap)
    for _ in range(2):
        if kbps < VIDEO_FLOOR_KBPS:
            break
        run_ffmpeg([ENCODER_EXE, "-y", "-v", "error", *input_args(source), "-map", "0:v:0", "-map", "0:a:0?",
                    "-vf", _scale(clip.width, clip.height), "-c:v", "libx264", "-preset", "veryfast",
                    "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.5)}k", "-bufsize", f"{kbps * 2}k",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", f"{SOUND_KBPS}k", "-movflags", "+faststart",
                    str(path)], f"encode {path.name}")
        if not _over(path, cap):
            return path
        kbps = int(kbps * 0.8)
    if not path.is_file():
        need = (VIDEO_FLOOR_KBPS + SOUND_KBPS) * 1000 * clip.seconds / 8 / CAP_SHARE / MB
        raise DeskError(f"{path.name}: {clip.seconds:.0f} s at the {VIDEO_FLOOR_KBPS} kbps floor needs about "
                        f"{need:.1f} MB, over the {cap / MB:.2f} MB cap: raise --max-mb, nothing was shrunk further")
    raise _refuse(path, cap, f"H.264 at {VIDEO_FLOOR_KBPS} kbps")
