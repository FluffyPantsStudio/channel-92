"""Integrated loudness and sample peak through ffmpeg's ebur128 filter, and the one plain gain that lays the song
back at the target without letting its sample peak pass -1 dBFS."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .media import ENCODER_EXE, input_args, run_ffmpeg

PEAK_CEILING_DB = -1.0
QUIET_WARNING_LUFS = -16.0
_INTEGRATED = re.compile(r"I:\s*(-?[\d.]+|-inf)\s*LUFS")
_PEAK = re.compile(r"Peak:\s*(-?[\d.]+|-inf)\s*dBFS")


@dataclass(frozen=True)
class Loudness:
    integrated: float
    peak: float


def _number(text: str) -> float:
    return float("-inf") if text == "-inf" else float(text)


def measure_loudness(path, *, start: float | None = None, seconds: float | None = None,
                     filters: str = "") -> Loudness:
    """Integrated LUFS and sample peak (dBFS) of a file's audio, optionally a stretch and after `filters`."""
    command = [ENCODER_EXE, "-nostdin", "-hide_banner", "-nostats"]
    if start is not None:
        command += ["-ss", f"{start:.6f}"]
    if seconds is not None:
        command += ["-t", f"{seconds:.6f}"]
    chain = ",".join(part for part in (filters, "ebur128=peak=sample") if part)
    command += [*input_args(path), "-vn", "-af", chain, "-f", "null", "-"]
    log = run_ffmpeg(command, f"measure the loudness of {path}").stderr
    summary = log[log.rfind("Summary:"):] if "Summary:" in log else log
    integrated = _INTEGRATED.findall(summary)
    peak = _PEAK.findall(summary)
    if not integrated or not peak:
        raise ValueError(f"no loudness summary for {path}")
    return Loudness(integrated=_number(integrated[-1]), peak=_number(peak[-1]))


def plain_gain(measured: Loudness, aim: float) -> tuple[float, list[str]]:
    """The gain in dB toward `target`, held so the sample peak stays at or under the ceiling; with warnings."""
    warnings = []
    if measured.integrated == float("-inf"):
        return 0.0, ["the song is silent; no gain applied"]
    gain = aim - measured.integrated
    headroom = PEAK_CEILING_DB - measured.peak
    if gain > headroom:
        gain = headroom
    result = measured.integrated + gain
    if result < QUIET_WARNING_LUFS:
        warnings.append(f"song at {result:.1f} LUFS after the gain, below -16 (target {aim:.1f}); its peak "
                        f"({measured.peak:.1f} dBFS) leaves no more room: master it louder")
    return gain, warnings
