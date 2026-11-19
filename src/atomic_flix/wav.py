"""Read and write WAV files with numpy only.

Reading accepts integer PCM (8, 16, 24, 32 bit) and 32/64-bit float, plain or
WAVE_FORMAT_EXTENSIBLE. Samples come back as float64 in [-1, 1], shaped
(frames, channels). Writing produces 16-bit PCM.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

FORMAT_PCM = 1
FORMAT_FLOAT = 3
FORMAT_EXTENSIBLE = 0xFFFE


class WavError(ValueError):
    """The file is not a WAV this module can read."""


def _chunks(blob: bytes):
    pos = 12
    while pos + 8 <= len(blob):
        tag = blob[pos:pos + 4]
        size = struct.unpack("<I", blob[pos + 4:pos + 8])[0]
        yield tag, blob[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)


def _decode(payload: bytes, tag: int, bits: int) -> np.ndarray:
    if tag == FORMAT_FLOAT and bits in (32, 64):
        return np.frombuffer(payload, dtype=f"<f{bits // 8}").astype(np.float64)
    if tag != FORMAT_PCM:
        raise WavError(f"unsupported sample format {tag} with {bits} bits")
    if bits == 8:
        return (np.frombuffer(payload, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    if bits == 16:
        return np.frombuffer(payload, dtype="<i2").astype(np.float64) / 32768.0
    if bits == 24:
        raw = np.frombuffer(payload[: len(payload) // 3 * 3], dtype=np.uint8).reshape(-1, 3)
        ints = raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8) | (raw[:, 2].astype(np.int32) << 16)
        ints = np.where(ints >= 1 << 23, ints - (1 << 24), ints)
        return ints.astype(np.float64) / float(1 << 23)
    if bits == 32:
        return np.frombuffer(payload, dtype="<i4").astype(np.float64) / float(1 << 31)
    raise WavError(f"unsupported PCM bit depth {bits}")


def read_wav(path) -> tuple[np.ndarray, int]:
    """Return (samples, rate); samples are float64 shaped (frames, channels)."""
    blob = Path(path).read_bytes()
    if len(blob) < 12 or blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise WavError(f"{path}: not a RIFF/WAVE file")
    fmt = None
    payload = None
    for tag, body in _chunks(blob):
        if tag == b"fmt ":
            fmt = body
        elif tag == b"data":
            payload = body
    if fmt is None or payload is None:
        raise WavError(f"{path}: missing fmt or data chunk")
    tag, channels, rate = struct.unpack("<HHI", fmt[:8])
    bits = struct.unpack("<H", fmt[14:16])[0]
    if tag == FORMAT_EXTENSIBLE:
        if len(fmt) < 26:
            raise WavError(f"{path}: short extensible fmt chunk")
        tag = struct.unpack("<H", fmt[24:26])[0]
    if channels < 1:
        raise WavError(f"{path}: no channels")
    frame_bytes = channels * bits // 8
    payload = payload[: len(payload) // frame_bytes * frame_bytes]
    samples = _decode(payload, tag, bits)
    return samples.reshape(-1, channels), int(rate)


def save_wav(path, samples, rate: int) -> Path:
    """Write float samples (frames,) or (frames, channels) as 16-bit PCM."""
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim == 1:
        data = data[:, None]
    if data.ndim != 2:
        raise ValueError("samples must be 1-D or (frames, channels)")
    ints = np.clip(np.round(data * 32768.0), -32768, 32767).astype("<i2")
    payload = ints.tobytes()
    channels = data.shape[1]
    block = channels * 2
    fmt = struct.pack("<HHIIHH", FORMAT_PCM, channels, int(rate), int(rate) * block, block, 16)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(payload)) + payload
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return out
