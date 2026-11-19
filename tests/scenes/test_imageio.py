"""PNG and OpenEXR files written and read with numpy and zlib only."""

import struct
import zlib

import numpy as np
import pytest

from atomic_flix.scenes import imageio


def _chunks(data: bytes):
    pos = 8
    while pos < len(data):
        (extent,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + extent]
        (crc,) = struct.unpack(">I", data[pos + 8 + extent:pos + 12 + extent])
        assert crc == zlib.crc32(kind + body)
        yield kind, body
        pos += 12 + extent


@pytest.mark.parametrize("shape,dtype", [((5, 7), np.uint8), ((5, 7, 3), np.uint8), ((4, 6, 4), np.uint8),
                                         ((5, 7), np.uint16), ((3, 4, 3), np.uint16)])
def test_png_round_trip(tmp_path, shape, dtype):
    rng = np.random.default_rng(0)
    arr = rng.integers(0, np.iinfo(dtype).max, size=shape, dtype=dtype)
    p = tmp_path / "a.png"
    imageio.write_png(p, arr)
    data = p.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    kinds = [k for k, _ in _chunks(data)]
    assert kinds[0] == b"IHDR" and kinds[-1] == b"IEND"
    back = imageio.read_png(p)
    assert back.dtype == dtype
    assert np.array_equal(back, arr)


def test_png_reader_undoes_every_filter(tmp_path):
    """Hand-build a PNG whose rows use filters 0..4 and check the reader gets the pixels back."""
    rng = np.random.default_rng(1)
    img = rng.integers(0, 256, size=(5, 6, 3), dtype=np.uint8)
    bpp = 3
    raw = img.reshape(5, -1).astype(np.int32)
    rows = []
    for y in range(5):
        cur = raw[y]
        prev = raw[y - 1] if y else np.zeros_like(cur)
        left = np.concatenate([np.zeros(bpp, np.int32), cur[:-bpp]])
        upleft = np.concatenate([np.zeros(bpp, np.int32), prev[:-bpp]])
        kind = y % 5
        if kind == 0:
            out = cur
        elif kind == 1:
            out = cur - left
        elif kind == 2:
            out = cur - prev
        elif kind == 3:
            out = cur - (left + prev) // 2
        else:
            p = left + prev - upleft
            pa, pb, pc = np.abs(p - left), np.abs(p - prev), np.abs(p - upleft)
            pred = np.where((pa <= pb) & (pa <= pc), left, np.where(pb <= pc, prev, upleft))
            out = cur - pred
        rows.append(bytes([kind]) + (out % 256).astype(np.uint8).tobytes())

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    ihdr = struct.pack(">IIBBBBB", 6, 5, 8, 2, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")
    p = tmp_path / "f.png"
    p.write_bytes(data)
    assert np.array_equal(imageio.read_png(p), img)


def test_png_rejects_bad_input(tmp_path):
    with pytest.raises(ValueError):
        imageio.write_png(tmp_path / "x.png", np.zeros((2, 2), np.float32))
    with pytest.raises(ValueError):
        imageio.write_png(tmp_path / "x.png", np.zeros((2, 2, 2), np.uint8))


@pytest.mark.parametrize("compression", ["none", "zips", "zip"])
def test_exr_round_trip_float(tmp_path, compression):
    rng = np.random.default_rng(2)
    chans = {"Z": rng.random((37, 23), dtype=np.float32) * 100,
             "N.X": rng.standard_normal((37, 23)).astype(np.float32)}
    p = tmp_path / "a.exr"
    imageio.write_exr(p, chans, compression=compression)
    back = imageio.read_exr(p)
    assert set(back) == set(chans)
    for k in chans:
        assert back[k].dtype == np.float32
        assert np.array_equal(back[k], chans[k])


def test_exr_half_channels(tmp_path):
    z = np.linspace(0, 10, 12, dtype=np.float32).reshape(3, 4)
    p = tmp_path / "h.exr"
    imageio.write_exr(p, {"Y": z}, half=True)
    back = imageio.read_exr(p)["Y"]
    assert np.allclose(back, z.astype(np.float16).astype(np.float32))


def test_exr_multipart_like_blender(tmp_path):
    rng = np.random.default_rng(3)
    parts = {
        "ViewLayer.Combined": {"ViewLayer.Combined.R": rng.random((20, 18), dtype=np.float32),
                               "ViewLayer.Combined.A": np.ones((20, 18), np.float32)},
        "ViewLayer.Depth": {"ViewLayer.Depth.Z": rng.random((20, 18), dtype=np.float32) * 9},
    }
    p = tmp_path / "m.exr"
    imageio.write_exr_parts(p, parts, compression="zip")
    raw = p.read_bytes()
    (version,) = struct.unpack("<i", raw[4:8])
    assert version & 0x1000  # multipart flag, as Blender writes
    back = imageio.read_exr(p)
    for part in parts.values():
        for k, v in part.items():
            assert np.array_equal(back[k], v)


def test_exr_reads_only_requested_channels(tmp_path):
    p = tmp_path / "a.exr"
    imageio.write_exr(p, {"A": np.zeros((2, 2), np.float32), "B": np.ones((2, 2), np.float32)})
    assert set(imageio.read_exr(p, want=lambda name: name == "B")) == {"B"}


def test_exr_rejects_a_png(tmp_path):
    p = tmp_path / "x.png"
    imageio.write_png(p, np.zeros((2, 2), np.uint8))
    with pytest.raises(ValueError, match="OpenEXR"):
        imageio.read_exr(p)
