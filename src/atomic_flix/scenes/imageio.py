"""PNG and OpenEXR with numpy and zlib only, so the pass files can be read and written inside Blender and out.

PNG: 8 and 16-bit, grey, grey+alpha, RGB and RGBA, non-interlaced; every row filter is read, rows are written
unfiltered. OpenEXR: scanline images (single or multi-part, as Blender writes multi-layer files), uncompressed or
zlib ("ZIPS" one line per block, "ZIP" sixteen), half and float channels.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Callable, Mapping

import numpy as np

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_PNG_COLOUR = {1: 0, 2: 4, 3: 2, 4: 6}            # channels -> PNG colour type
_PNG_CHANNELS = {0: 1, 4: 2, 2: 3, 6: 4}


# ---------------------------------------------------------------- PNG

def _png_chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def write_png(path: str | Path, arr: np.ndarray, level: int = 3) -> Path:
    arr = np.asarray(arr)
    if arr.dtype not in (np.uint8, np.uint16):
        raise ValueError(f"PNG needs uint8 or uint16 pixels, got {arr.dtype}")
    if arr.ndim == 2:
        arr = arr[..., None]
    if arr.ndim != 3 or arr.shape[2] not in _PNG_COLOUR:
        raise ValueError(f"PNG needs HxW or HxWx(1..4) pixels, got shape {arr.shape}")
    h, w, c = arr.shape
    if c == 2:
        raise ValueError("two-channel images are not written; use grey or RGB")
    depth = 8 if arr.dtype == np.uint8 else 16
    rows = arr.astype(">u2") if depth == 16 else arr
    raw = np.empty((h, 1 + w * c * (depth // 8)), np.uint8)
    raw[:, 0] = 0
    raw[:, 1:] = np.frombuffer(np.ascontiguousarray(rows).tobytes(), np.uint8).reshape(h, -1)
    ihdr = struct.pack(">IIBBBBB", w, h, depth, _PNG_COLOUR[c], 0, 0, 0)
    data = PNG_MAGIC + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(raw.tobytes(), level)) \
        + _png_chunk(b"IEND", b"")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _unfilter(data: np.ndarray, h: int, stride: int, bpp: int) -> np.ndarray:
    rows = data.reshape(h, stride + 1)
    kinds = rows[:, 0]
    out = np.zeros((h, stride), np.uint8)
    prev = np.zeros(stride, np.int32)
    for y in range(h):
        cur = rows[y, 1:].astype(np.int32)
        kind = kinds[y]
        if kind == 0:
            line = cur
        elif kind == 1:
            line = cur.reshape(-1, bpp).cumsum(axis=0).reshape(-1) % 256
        elif kind == 2:
            line = (cur + prev) % 256
        elif kind in (3, 4):
            line = np.zeros(stride, np.int32)
            for x in range(stride):
                left = line[x - bpp] if x >= bpp else 0
                up = prev[x]
                if kind == 3:
                    pred = (left + up) // 2
                else:
                    upleft = prev[x - bpp] if x >= bpp else 0
                    p = left + up - upleft
                    pa, pb, pc = abs(p - left), abs(p - up), abs(p - upleft)
                    pred = left if pa <= pb and pa <= pc else (up if pb <= pc else upleft)
                line[x] = (cur[x] + pred) % 256
        else:
            raise ValueError(f"bad PNG row filter {kind}")
        out[y] = line
        prev = line.astype(np.int32)
    return out


def read_png(path: str | Path) -> np.ndarray:
    data = Path(path).read_bytes()
    if data[:8] != PNG_MAGIC:
        raise ValueError(f"{path}: not a PNG file")
    pos, idat, hdr = 8, [], None
    while pos < len(data):
        (extent,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + extent]
        pos += 12 + extent
        if kind == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if hdr is None:
        raise ValueError(f"{path}: PNG without a header")
    w, h, depth, colour, _, _, interlace = hdr
    if interlace or colour not in _PNG_CHANNELS or depth not in (8, 16):
        raise ValueError(f"{path}: unsupported PNG (depth {depth}, colour type {colour}, interlace {interlace})")
    c = _PNG_CHANNELS[colour]
    bpp = c * depth // 8
    raw = np.frombuffer(zlib.decompress(b"".join(idat)), np.uint8)
    px = _unfilter(raw, h, w * bpp, bpp)
    if depth == 16:
        img = px.reshape(h, -1).view(">u2").astype(np.uint16).reshape(h, w, c)
    else:
        img = px.reshape(h, w, c)
    return img[..., 0] if c == 1 else img


# ---------------------------------------------------------------- OpenEXR

EXR_MAGIC = 20000630
EXR_ZLIB_LEVEL = 3   # pass files are written every frame: favour speed over a few per cent of size
_PIXEL = {0: np.dtype("<u4"), 1: np.dtype("<f2"), 2: np.dtype("<f4")}
_COMPRESSION = {"none": (0, 1), "zips": (2, 1), "zip": (3, 16)}
_LINES = {0: 1, 2: 1, 3: 16}


def _cstr(data: bytes, pos: int) -> tuple[str, int]:
    end = data.index(b"\0", pos)
    return data[pos:end].decode("latin-1"), end + 1


def _read_header(data: bytes, pos: int) -> tuple[dict, int]:
    attrs: dict = {}
    while True:
        name, pos = _cstr(data, pos)
        if not name:
            return attrs, pos
        kind, pos = _cstr(data, pos)
        (size,) = struct.unpack("<i", data[pos:pos + 4])
        pos += 4
        value = data[pos:pos + size]
        pos += size
        if kind == "chlist":
            chans, q = [], 0
            while value[q] != 0:
                cname, q = _cstr(value, q)
                (ptype,) = struct.unpack("<i", value[q:q + 4])
                xs, ys = struct.unpack("<ii", value[q + 8:q + 16])
                if (xs, ys) != (1, 1):
                    raise ValueError("sub-sampled EXR channels are not supported")
                chans.append((cname, ptype))
                q += 16
            attrs[name] = sorted(chans)
        elif kind == "box2i":
            attrs[name] = struct.unpack("<iiii", value)
        elif kind in ("compression", "lineOrder"):
            attrs[name] = value[0]
        elif kind == "int":
            attrs[name] = struct.unpack("<i", value)[0]
        elif kind == "string":
            attrs[name] = value.decode("latin-1")


def _unpredict(raw: bytes) -> bytes:
    """Undo the zlib codec's byte predictor and interleave."""
    d = np.frombuffer(raw, np.uint8).copy()
    if len(d) == 0:
        return raw
    d[1:] -= np.uint8(128)
    t = np.cumsum(d, dtype=np.uint8)  # t[i] = t[i-1] + raw[i] - 128; uint8 arithmetic wraps by itself
    half = (len(t) + 1) // 2
    out = np.empty_like(t)
    out[0::2] = t[:half]
    out[1::2] = t[half:]
    return out.tobytes()


def _predict(raw: bytes) -> bytes:
    t = np.frombuffer(raw, np.uint8)
    inter = np.concatenate([t[0::2], t[1::2]])
    out = inter.copy()
    out[1:] = inter[1:] - inter[:-1] + np.uint8(128)
    return out.tobytes()


def read_exr(path: str | Path, want: Callable[[str], bool] | None = None) -> dict[str, np.ndarray]:
    """All channels (or those `want` accepts) as float32 HxW arrays, keyed by their full channel name."""
    data = Path(path).read_bytes()
    if len(data) < 8 or struct.unpack("<i", data[:4])[0] != EXR_MAGIC:
        raise ValueError(f"{path}: not an OpenEXR file")
    (version,) = struct.unpack("<i", data[4:8])
    if version & 0x200:
        raise ValueError(f"{path}: tiled OpenEXR is not supported")
    multipart = bool(version & 0x1000)
    pos, headers = 8, []
    while True:
        hdr, pos = _read_header(data, pos)
        headers.append(hdr)
        if not multipart or data[pos] == 0:
            break
    if multipart:
        pos += 1
    tables = []
    for hdr in headers:
        x0, y0, x1, y1 = hdr["dataWindow"]
        lines = _LINES.get(hdr.get("compression", 0))
        if lines is None:
            raise ValueError(f"{path}: EXR compression {hdr.get('compression')} is not supported (use ZIP)")
        count = hdr.get("chunkCount", -(-(y1 - y0 + 1) // lines))
        tables.append(struct.unpack(f"<{count}Q", data[pos:pos + 8 * count]))
        pos += 8 * count
    out: dict[str, np.ndarray] = {}
    for part, (hdr, offsets) in enumerate(zip(headers, tables)):
        chans = [(n, t) for n, t in hdr["channels"]]
        if want is not None and not any(want(n) for n, _ in chans):
            continue
        x0, y0, x1, y1 = hdr["dataWindow"]
        w, h = x1 - x0 + 1, y1 - y0 + 1
        compression = hdr.get("compression", 0)
        planes = {n: np.zeros((h, w), np.float32) for n, _ in chans}
        for off in offsets:
            p = off + (4 if multipart else 0)
            y, size = struct.unpack("<ii", data[p:p + 8])
            block = data[p + 8:p + 8 + size]
            nlines = min(_LINES[compression], y1 - y + 1)
            expected = sum(_PIXEL[t].itemsize for _, t in chans) * w * nlines
            if compression and size < expected:
                block = _unpredict(zlib.decompress(block))
            q = 0
            for line in range(nlines):
                for name, ptype in chans:
                    dt = _PIXEL[ptype]
                    planes[name][y - y0 + line] = np.frombuffer(block, dt, w, q)
                    q += dt.itemsize * w
        for name, plane in planes.items():
            if want is None or want(name):
                out[name] = plane
    return out


def _attr(name: str, kind: str, value: bytes) -> bytes:
    return name.encode() + b"\0" + kind.encode() + b"\0" + struct.pack("<i", len(value)) + value


def _header_bytes(chans: list[tuple[str, int]], w: int, h: int, code: int, part_name: str | None, chunks: int) -> bytes:
    chlist = b"".join(n.encode() + b"\0" + struct.pack("<iBBBBii", t, 0, 0, 0, 0, 1, 1) for n, t in chans) + b"\0"
    box = struct.pack("<iiii", 0, 0, w - 1, h - 1)
    out = [_attr("channels", "chlist", chlist), _attr("compression", "compression", bytes([code])),
           _attr("dataWindow", "box2i", box), _attr("displayWindow", "box2i", box),
           _attr("lineOrder", "lineOrder", b"\0"), _attr("pixelAspectRatio", "float", struct.pack("<f", 1.0)),
           _attr("screenWindowCenter", "v2f", struct.pack("<ff", 0, 0)),
           _attr("screenWindowWidth", "float", struct.pack("<f", 1.0))]
    if part_name is not None:
        out += [_attr("name", "string", part_name.encode()), _attr("type", "string", b"scanlineimage"),
                _attr("chunkCount", "int", struct.pack("<i", chunks))]
    return b"".join(out) + b"\0"


def _strips(planes: list[tuple[np.ndarray, np.dtype]], h: int, lines: int, code: int) -> list[tuple[int, bytes]]:
    pieces = []
    for y in range(0, h, lines):
        raw = b"".join(np.ascontiguousarray(p[line].astype(dt)).tobytes()
                       for line in range(y, min(h, y + lines)) for p, dt in planes)
        if code:
            packed = zlib.compress(_predict(raw), EXR_ZLIB_LEVEL)
            raw = packed if len(packed) < len(raw) else raw
        pieces.append((y, raw))
    return pieces


def write_exr_parts(path: str | Path, parts: Mapping[str, Mapping[str, np.ndarray]],
                    compression: str = "zip", half: bool = False) -> Path:
    """Write channels as an OpenEXR file; more than one part gives a multi-part file like Blender's."""
    if compression not in _COMPRESSION:
        raise ValueError(f"compression must be one of {sorted(_COMPRESSION)}")
    code, lines = _COMPRESSION[compression]
    ptype = 1 if half else 2
    multipart = len(parts) > 1
    headers, part_blocks = [], []
    for part_name, chans in parts.items():
        names = sorted(chans)
        h, w = np.asarray(chans[names[0]]).shape
        planes = [(np.asarray(chans[n], np.float32), _PIXEL[ptype]) for n in names]
        pieces = _strips(planes, h, lines, code)
        headers.append(_header_bytes([(n, ptype) for n in names], w, h, code,
                                     part_name if multipart else None, len(pieces)))
        part_blocks.append(pieces)
    version = 2 | (0x1000 if multipart else 0)
    head = struct.pack("<ii", EXR_MAGIC, version) + b"".join(headers) + (b"\0" if multipart else b"")
    table_size = 8 * sum(len(b) for b in part_blocks)
    pos = len(head) + table_size
    tables, body = [], []
    for index, pieces in enumerate(part_blocks):
        for y, raw in pieces:
            chunk = (struct.pack("<i", index) if multipart else b"") + struct.pack("<ii", y, len(raw)) + raw
            tables.append(struct.pack("<Q", pos))
            body.append(chunk)
            pos += len(chunk)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(head + b"".join(tables) + b"".join(body))
    return path


def write_exr(path: str | Path, channels: Mapping[str, np.ndarray], compression: str = "zip",
              half: bool = False) -> Path:
    return write_exr_parts(path, {"": channels}, compression=compression, half=half)
