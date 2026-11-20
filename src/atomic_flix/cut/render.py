"""Turn an edit into a finished clip with exactly one encode.

Every take is decoded once, already filled and centre-cropped to the film's frame and pixel format (scaled with
SCALE_FLAGS). The map chooses which take frames appear and in what order; those raw frames stream into a single
H.264 encoder. For sound, the song is laid under the picture at a single fixed gain aimed at -14 LUFS, never letting
its sample peak climb over -1 dBFS, with a fade at each end. Audio inside the takes is discarded.

Before anything is encoded the audit is run, and an audit error (slowed playback, a take's opening two frames on
screen, a jump cut) stops the render.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .audit import HIDDEN_HEAD_FRAMES, AuditReport, audit_edit, take_indices
from .edit import Edit, Placed
from .loudness import Loudness, measure_loudness, plain_gain
from ..programs import command_of
from .media import ERROR_TAIL, ENCODER_EXE, SCALE_FLAGS, STDIN_ONLY, ClipInfo, MediaError, input_args, probe

AUDIO_RATE = 48000
AUDIO_BITRATE = "320k"


class CutError(RuntimeError):
    """The edit breaks a cutting rule; the message lists every error."""


@dataclass
class CutResult:
    out: Path
    audit: AuditReport
    audio: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _picture_filters(placed: Placed, size: tuple[int, int], first_index: int) -> str:
    width, height = size
    parts = []
    if first_index > 0:
        parts.append(f"trim=start_frame={first_index},setpts=PTS-STARTPTS")
    if placed.crop:
        x, y, w, h = placed.crop
        parts.append(f"crop={w}:{h}:{x}:{y}")
    parts += [f"scale={width}:{height}:force_original_aspect_ratio=increase:flags={SCALE_FLAGS}",
              f"crop={width}:{height}", "setsar=1"]
    return ",".join(parts)


def _decode_command(placed: Placed, size: tuple[int, int], first_index: int, count: int) -> list[str]:
    return [ENCODER_EXE, "-v", "error", "-nostdin", *input_args(placed.file),
            "-vf", _picture_filters(placed, size, first_index), "-frames:v", str(count),
            "-fps_mode", "passthrough", "-sws_flags", SCALE_FLAGS, "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"]


def _audio_filters(edit: Edit, trim_db: float | None) -> str:
    seconds = edit.end - edit.start
    parts = [f"aresample={AUDIO_RATE}"]
    if trim_db is not None:
        parts.append(f"volume={trim_db:.3f}dB")
    if edit.fade_in > 0:
        parts.append(f"afade=t=in:st=0:d={edit.fade_in:.3f}")
    if edit.fade_out > 0:
        parts.append(f"afade=t=out:st={max(0.0, seconds - edit.fade_out):.3f}:d={edit.fade_out:.3f}")
    return ",".join(parts)


def _encode_command(edit: Edit, out: Path, trim_db: float | None, crf: int, x264_speed: str) -> list[str]:
    width, height = edit.size
    seconds = edit.end - edit.start
    command = [ENCODER_EXE, "-y", "-v", "error", "-nostdin", *STDIN_ONLY, "-f", "rawvideo", "-pix_fmt", "yuv420p",
               "-s", f"{width}x{height}", "-r", f"{edit.fps:g}", "-i", "-"]
    if edit.song:
        command += ["-ss", f"{edit.start:.6f}", "-t", f"{seconds:.6f}", *input_args(edit.song),
                    "-map", "0:v", "-map", "1:a", "-af", _audio_filters(edit, trim_db),
                    "-c:a", "aac", "-b:a", AUDIO_BITRATE]
    else:
        command += ["-an"]
    command += ["-c:v", "libx264", "-preset", x264_speed, "-crf", str(crf), "-pix_fmt", "yuv420p",
                "-frames:v", str(edit.frame_count), "-t", f"{seconds:.6f}", "-movflags", "+faststart", str(out)]
    return command


def _song_gain(edit: Edit) -> tuple[float | None, dict, list[str]]:
    if not edit.song:
        return None, {}, ["no song given: the cut has no sound"]
    seconds = edit.end - edit.start
    before: Loudness = measure_loudness(edit.song, start=edit.start, seconds=seconds,
                                        filters=_audio_filters(edit, None))
    gain, warnings = plain_gain(before, edit.target_lufs)
    audio = {"target_lufs": edit.target_lufs, "measured_lufs": round(before.integrated, 2),
             "measured_peak_db": round(before.peak, 2), "trim_db": round(gain, 3),
             "lufs_after": round(before.integrated + gain, 2), "peak_after_db": round(before.peak + gain, 2)}
    return gain, audio, warnings


def _emit_shot(encoder: subprocess.Popen, placed: Placed, info: ClipInfo, indices: np.ndarray,
               size: tuple[int, int]) -> None:
    """Pipe the frames a shot shows into the encoder, holding the last frame if the take runs out."""
    width, height = size
    frame_bytes = width * height * 3 // 2
    wanted = np.maximum(indices, HIDDEN_HEAD_FRAMES)
    first = int(wanted[0])
    last = min(int(wanted[-1]), info.frames - 1)
    if first > info.frames - 1:
        first = last = info.frames - 1
    decoder = subprocess.Popen(command_of(_decode_command(placed, size, first, last - first + 1)),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    current_index, current = first - 1, None
    try:
        for index in wanted:
            while current_index < index:
                raw = decoder.stdout.read(frame_bytes)
                if len(raw) < frame_bytes:
                    break
                current, current_index = raw, current_index + 1
            if current is None:
                raise MediaError(f"no frames decoded from {placed.file}")
            encoder.stdin.write(current)
    finally:
        decoder.stdout.close()
        error = decoder.stderr.read().decode(errors="replace")
        decoder.wait()
    if decoder.returncode not in (0, None) and current is None:
        raise MediaError(f"ffmpeg could not decode {placed.file}: {error.strip()[-ERROR_TAIL:]}")


def ffmpeg_command_for_test(edit: Edit, out) -> tuple[list[str], list[str]]:
    """The decode command of the first shot and the encode command, as the render would run them."""
    shot = edit.shots()[0]
    placed = edit.takes[shot.key]
    return _decode_command(placed, edit.size, 2, 1), _encode_command(edit, Path(out), 0.0, 16, "slow")


def render_cut(edit: Edit, out, *, crf: int = 16, x264_speed: str = "slow", strict: bool = True,
               compare_frames: bool = True) -> CutResult:
    """Audit, then render the edit to `out` (written only when ffmpeg succeeds)."""
    out = Path(out)
    infos = {key: probe(placed.file) for key, placed in edit.takes.items()}
    audit = audit_edit(edit, take_info=infos, compare_frames=compare_frames)
    if strict and audit.errors:
        raise CutError("the cut breaks the cutting rules:\n" + "\n".join(audit.errors))
    gain, audio, warnings = _song_gain(edit)
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.stem + ".partial" + out.suffix)
    with tempfile.TemporaryFile() as log:
        encoder = subprocess.Popen(command_of(_encode_command(edit, partial, gain, crf, x264_speed)),
                                   stdin=subprocess.PIPE,
                                   stderr=log)
        try:
            for shot in edit.shots():
                placed = edit.takes[shot.key]
                info = infos[shot.key]
                _emit_shot(encoder, placed, info, take_indices(edit, shot, placed, info.fps), edit.size)
        except BrokenPipeError:
            pass
        finally:
            if encoder.stdin and not encoder.stdin.closed:
                try:
                    encoder.stdin.close()
                except BrokenPipeError:
                    pass
            encoder.wait()
        if encoder.returncode != 0:
            log.seek(0)
            partial.unlink(missing_ok=True)
            raise MediaError(f"ffmpeg could not encode the cut: {log.read().decode(errors='replace')[-ERROR_TAIL:]}")
    partial.replace(out)
    return CutResult(out=out, audit=audit, audio=audio, warnings=warnings + audit.warnings)
