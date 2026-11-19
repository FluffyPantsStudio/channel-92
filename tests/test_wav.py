import struct

import numpy as np
import pytest

from atomic_flix.wav import WavError, read_wav, save_wav


def _riff(fmt_tag, channels, rate, bits, payload, extensible_tag=None):
    block = channels * bits // 8
    if extensible_tag is None:
        fmt = struct.pack("<HHIIHH", fmt_tag, channels, rate, rate * block, block, bits)
    else:
        guid = struct.pack("<H", extensible_tag) + b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"
        fmt = struct.pack("<HHIIHHHHI", 0xFFFE, channels, rate, rate * block, block, bits, 22, bits, 0) + guid
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"LIST" + struct.pack("<I", 4) + b"INFO"  # an extra chunk the reader must skip
    body += b"data" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_roundtrip_16_bit_mono(tmp_path):
    rate = 22050
    sig = 0.5 * np.sin(2 * np.pi * 440 * np.arange(rate) / rate)
    path = tmp_path / "a.wav"
    save_wav(path, sig, rate)
    back, back_rate = read_wav(path)
    assert back_rate == rate
    assert back.shape == (rate, 1)
    assert np.max(np.abs(back[:, 0] - sig)) < 1e-4


def test_roundtrip_stereo_shape(tmp_path):
    sig = np.zeros((100, 2))
    sig[:, 1] = 0.25
    path = tmp_path / "s.wav"
    save_wav(path, sig, 48000)
    back, rate = read_wav(path)
    assert rate == 48000 and back.shape == (100, 2)
    assert abs(back[0, 1] - 0.25) < 1e-4


def test_write_clips_out_of_range(tmp_path):
    path = tmp_path / "c.wav"
    save_wav(path, np.array([2.0, -2.0]), 8000)
    back, _ = read_wav(path)
    assert back[0, 0] == pytest.approx(32767 / 32768, abs=1e-6)
    assert back[1, 0] == -1.0


def test_reads_24_bit_pcm(tmp_path):
    values = [0, 4194304, -8388608]  # 0, +0.5, -1.0
    payload = b"".join(v.to_bytes(3, "little", signed=True) for v in values)
    path = tmp_path / "p24.wav"
    path.write_bytes(_riff(1, 1, 44100, 24, payload))
    back, _ = read_wav(path)
    assert np.allclose(back[:, 0], [0.0, 0.5, -1.0])


def test_reads_float32_and_extensible(tmp_path):
    payload = np.array([0.25, -0.75], dtype="<f4").tobytes()
    plain = tmp_path / "f.wav"
    plain.write_bytes(_riff(3, 1, 44100, 32, payload))
    ext = tmp_path / "fx.wav"
    ext.write_bytes(_riff(None, 1, 44100, 32, payload, extensible_tag=3))
    for path in (plain, ext):
        back, _ = read_wav(path)
        assert np.allclose(back[:, 0], [0.25, -0.75])


def test_rejects_non_wav(tmp_path):
    path = tmp_path / "x.wav"
    path.write_bytes(b"not a wave file at all")
    with pytest.raises(WavError):
        read_wav(path)
