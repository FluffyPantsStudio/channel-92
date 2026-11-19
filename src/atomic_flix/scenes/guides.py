"""Control clips for our ComfyUI video graphs, made from a scene's capture layers (no depth or pose estimation).

  python -m atomic_flix.scenes controls OUT/ --for ltx --size 1152x640

Writes into OUT/controls/: depth-<model>.mp4 (inverse depth, near white, range fixed for the whole shot, sky black),
canny-<model>.mp4 (Canny on the shaded), edges-<model>.mp4 (depth discontinuities, which see thin parts the
shaded's Canny can miss in low contrast), pose-<model>.mp4 (the figure's body points as coloured sticks, when
the scene has one), first-<model>.png and last-<model>.png (shaded ends for end-frame graphs) and guides-<model>.json.

Frames are fitted to the guide size by scaling to cover and cropping the middle. Sizes follow each model's rule and
a size that breaks it is an error, never changed quietly: LTX-2.3 with the union control halves the frame inside
the graph and needs even latents there, so both sides must be multiples of 128 (1152x640, 1280x768; 1280x704
fails); SCAIL-2 and Wan snap to 32.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import numpy as np

from . import path as camera_path
from .imageio import read_exr, write_png
from ..formats import tag
from ..sizes import CONTROL_VIDEO_STEP, GRAPH_STEP, FrameSizeError, check_multiple

SIZE_RULES = {"ltx": CONTROL_VIDEO_STEP, "scail": GRAPH_STEP, "wan": GRAPH_STEP}
SWS = "bicubic+accurate_rnd+full_chroma_int+bitexact"

# body point order and the coloured sticks between them; face points are left out
POSE_POINTS = ["nose", "neck", "r_shoulder", "r_elbow", "r_wrist", "l_shoulder", "l_elbow", "l_wrist",
               "r_hip", "r_knee", "r_ankle", "l_hip", "l_knee", "l_ankle"]
POSE_STICKS = [("neck", "r_shoulder"), ("neck", "l_shoulder"), ("r_shoulder", "r_elbow"), ("r_elbow", "r_wrist"),
               ("l_shoulder", "l_elbow"), ("l_elbow", "l_wrist"), ("neck", "r_hip"), ("r_hip", "r_knee"),
               ("r_knee", "r_ankle"), ("neck", "l_hip"), ("l_hip", "l_knee"), ("l_knee", "l_ankle"),
               ("neck", "nose")]
POSE_COLOURS = [(255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0), (85, 255, 0), (0, 255, 0),
                (0, 255, 85), (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255), (0, 0, 255),
                (85, 0, 255), (170, 0, 255), (255, 0, 255), (255, 0, 170), (255, 0, 85)]


class GuideSizeError(FrameSizeError):
    pass


def parse_size(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*x\s*(\d+)\s*", text)
    if not m:
        raise ValueError(f"size {text!r}: expected WIDTHxHEIGHT such as 1152x640")
    return int(m.group(1)), int(m.group(2))


def check_guide_size(model: str, w: int, h: int) -> None:
    if model not in SIZE_RULES:
        raise ValueError(f"unknown model {model!r}; guides are made for {sorted(SIZE_RULES)}")
    step = SIZE_RULES[model]
    why = " (the graph halves the frame and needs even latents)" if model == "ltx" else ""
    try:
        check_multiple(w, h, step, why)
    except FrameSizeError as problem:
        raise GuideSizeError(f"{w}x{h} does not suit {model}: both sides must be multiples of {step}{why} "
                             f"({problem})") from None


# ---------------------------------------------------------------- fitting

def cover_transform(src_w: int, src_h: int, dst_w: int, dst_h: int) -> tuple[float, float, float]:
    """Scale s and crop offsets (ox, oy): a source pixel position p lands at p * s - offset."""
    s = max(dst_w / src_w, dst_h / src_h)
    return s, (src_w * s - dst_w) / 2, (src_h * s - dst_h) / 2


def resize_cover(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """Bilinear scale-to-cover and centre crop of an HxW or HxWxC array (kept in its dtype)."""
    src_h, src_w = img.shape[:2]
    s, ox, oy = cover_transform(src_w, src_h, w, h)
    xs = np.clip((np.arange(w) + 0.5 + ox) / s - 0.5, 0, src_w - 1)
    ys = np.clip((np.arange(h) + 0.5 + oy) / s - 0.5, 0, src_h - 1)
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    x1, y1 = np.minimum(x0 + 1, src_w - 1), np.minimum(y0 + 1, src_h - 1)
    fx, fy = xs - x0, ys - y0
    a = img.astype(np.float64)
    if a.ndim == 3:
        fx, fy = fx[None, :, None], fy[:, None, None]
    else:
        fx, fy = fx[None, :], fy[:, None]
    top = a[y0][:, x0] * (1 - fx) + a[y0][:, x1] * fx
    bottom = a[y1][:, x0] * (1 - fx) + a[y1][:, x1] * fx
    out = top * (1 - fy) + bottom * fy
    if np.issubdtype(img.dtype, np.integer):
        return np.clip(np.rint(out), 0, np.iinfo(img.dtype).max).astype(img.dtype)
    return out.astype(img.dtype)


# ---------------------------------------------------------------- depth

def depth_range(frames: Iterable[np.ndarray], far: float, near_pct: float = 99.5) -> tuple[float, float]:
    """One inverse-depth range for the whole shot: lo is the sky (1 / far), hi the near end of the nearest
    frame, so a push brightens what comes closer instead of re-stretching every frame."""
    hi = 0.0
    for z in frames:
        hi = max(hi, float(np.percentile(1.0 / np.maximum(z, 1e-6), near_pct)))
    lo = 1.0 / far
    return lo, max(hi, lo * 1.0001)


def depth_to_guide(z: np.ndarray, lo: float, hi: float) -> np.ndarray:
    inv = 1.0 / np.maximum(z.astype(np.float64), 1e-6)
    return np.clip(np.rint((inv - lo) / (hi - lo) * 255), 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- edges

def _blur(img: np.ndarray, sigma: float) -> np.ndarray:
    r = max(1, int(round(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.pad(img, r, mode="edge")
    tmp = sum(k[i] * pad[:, i:i + img.shape[1]] for i in range(2 * r + 1))
    return sum(k[i] * tmp[i:i + img.shape[0]] for i in range(2 * r + 1))


def _sobel(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p = np.pad(img, 1, mode="edge")
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    return gx / 8.0, gy / 8.0


_NEIGHBOURS = np.array([(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])


def _hysteresis(firm: np.ndarray, weak: np.ndarray) -> np.ndarray:
    """Grow strong edges along 8-connected weak ones, one ring at a time from the newest pixels only."""
    h, w = firm.shape
    keep = firm.ravel().copy()
    weak_flat = weak.ravel()
    ys, xs = np.divmod(np.flatnonzero(keep), w)
    while len(ys):
        ny = ys[:, None] + _NEIGHBOURS[:, 0]
        nx = xs[:, None] + _NEIGHBOURS[:, 1]
        inside = (ny >= 0) & (ny < h) & (nx >= 0) & (nx < w)
        idx = (ny * w + nx)[inside]
        idx = np.unique(idx[weak_flat[idx] & ~keep[idx]])
        keep[idx] = True
        ys, xs = np.divmod(idx, w)
    return keep.reshape(h, w)


def canny(img: np.ndarray, low: float = 0.04, high: float = 0.1, sigma: float = 1.2) -> np.ndarray:
    """Canny edges, white on black. img is grey or RGB, uint8 or float in [0, 1]; thresholds are gradient steps in
    [0, 1] intensity per pixel."""
    a = img.astype(np.float64)
    if np.issubdtype(img.dtype, np.integer):
        a /= 255.0
    if a.ndim == 3:
        a = a[..., :3] @ np.array([0.299, 0.587, 0.114])
    gx, gy = _sobel(_blur(a, sigma))
    mag = np.hypot(gx, gy)
    angle = (np.rad2deg(np.arctan2(gy, gx)) + 180.0) % 180.0
    sector = (np.round(angle / 45.0).astype(int)) % 4          # 0: horizontal gradient, 1: 45, 2: vertical, 3: 135
    p = np.pad(mag, 1)
    h, w = mag.shape
    shifts = {0: ((0, 1), (0, -1)), 1: ((1, 1), (-1, -1)), 2: ((1, 0), (-1, 0)), 3: ((1, -1), (-1, 1))}
    keep = np.zeros_like(mag, bool)
    for s, ((ay, ax), (by, bx)) in shifts.items():
        n1 = p[1 + ay:1 + ay + h, 1 + ax:1 + ax + w]
        n2 = p[1 + by:1 + by + h, 1 + bx:1 + bx + w]
        keep |= (sector == s) & (mag >= n1) & (mag > n2)
    thin = np.where(keep, mag, 0.0)
    edges = _hysteresis(thin >= high, thin >= low)
    return np.where(edges, 255, 0).astype(np.uint8)


def depth_edges(z: np.ndarray, ratio: float = 0.08) -> np.ndarray:
    """White where neighbouring depths differ by more than `ratio` of the nearer one (silhouettes and steps)."""
    lz = np.log(np.maximum(z.astype(np.float64), 1e-6))
    step = np.log1p(ratio)
    edge = np.zeros(z.shape, bool)
    dx = np.abs(np.diff(lz, axis=1)) > step
    dy = np.abs(np.diff(lz, axis=0)) > step
    edge[:, :-1] |= dx
    edge[:, 1:] |= dx
    edge[:-1] |= dy
    edge[1:] |= dy
    return np.where(edge, 255, 0).astype(np.uint8)


# ---------------------------------------------------------------- pose

def project_joints(joints: dict, record: dict, src_w: int, src_h: int, w: int, h: int) -> dict[str, list[float]]:
    """Body points to guide pixels; points behind the viewpoint are dropped."""
    s, ox, oy = cover_transform(src_w, src_h, w, h)
    out = {}
    for name, point in joints.items():
        uv = camera_path.to_screen(record, point)
        if uv is not None:
            out[name] = [uv[0] * s - ox, uv[1] * s - oy]
    return out


def _stroke(img: np.ndarray, a, b, width: float, colour) -> None:
    h, w = img.shape[:2]
    pad = width + 1
    x0, x1 = int(max(0, min(a[0], b[0]) - pad)), int(min(w, max(a[0], b[0]) + pad + 1))
    y0, y1 = int(max(0, min(a[1], b[1]) - pad)), int(min(h, max(a[1], b[1]) + pad + 1))
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1] + 0.5
    d = np.array(b, float) - np.array(a, float)
    length2 = float(d @ d) or 1e-9
    t = np.clip(((xx - a[0]) * d[0] + (yy - a[1]) * d[1]) / length2, 0, 1)
    dist = np.hypot(xx - (a[0] + t * d[0]), yy - (a[1] + t * d[1]))
    img[y0:y1, x0:x1][dist <= width / 2] = colour


def draw_pose(ties: dict, w: int, h: int, stick: float | None = None) -> np.ndarray:
    """Coloured sticks (60 % brightness) and joint dots on black, in the usual body-pose drawing colours."""
    img = np.zeros((h, w, 3), np.uint8)
    stick = stick or max(3.0, 4.0 * min(w, h) / 512)
    for i, (a, b) in enumerate(POSE_STICKS):
        if a in ties and b in ties:
            colour = tuple(int(c * 0.6) for c in POSE_COLOURS[i])
            _stroke(img, ties[a], ties[b], stick, colour)
    for name, p in ties.items():
        if name in POSE_POINTS:
            _stroke(img, p, p, stick, POSE_COLOURS[POSE_POINTS.index(name)])
    return img


# ---------------------------------------------------------------- video in and out

def _encoder() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise FileNotFoundError("ffmpeg is not on PATH")
    return exe


class VideoWriter:
    """H.264 yuv420p from HxWx3 (or HxW grey) uint8 frames, one encode; the size comes from the first frame."""

    def __init__(self, path: str | Path, fps: float, crf: int = 12) -> None:
        self.path = Path(path)
        self.fps = fps
        self.crf = crf
        self.proc: subprocess.Popen | None = None

    def write(self, frame: np.ndarray) -> None:
        rgb = np.repeat(frame[..., None], 3, axis=2) if frame.ndim == 2 else frame
        if self.proc is None:
            h, w = rgb.shape[:2]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            cmd = [_encoder(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                   "-r", str(self.fps), "-i", "-", "-sws_flags", SWS, "-c:v", "libx264", "-crf", str(self.crf),
                   "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(self.path)]
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        self.proc.stdin.write(np.ascontiguousarray(rgb, np.uint8).tobytes())

    def close(self) -> Path:
        if self.proc is None:
            raise ValueError(f"{self.path}: no frames were written")
        self.proc.stdin.close()
        code = self.proc.wait()
        if code:
            raise RuntimeError(f"ffmpeg failed writing {self.path} (exit {code})")
        return self.path


def write_video(frames: Iterable[np.ndarray], path: str | Path, fps: float, crf: int = 12) -> Path:
    writer = VideoWriter(path, fps, crf)
    for frame in frames:
        writer.write(frame)
    return writer.close()


def read_frames(provenance: str | Path, w: int, h: int, start: int | None = None) -> Iterator[np.ndarray]:
    """Decode a video, or an image sequence such as shaded/%04d.png starting at frame `start`, to RGB frames scaled
    to cover w x h and centre-cropped."""
    args = [_encoder(), "-loglevel", "error"]
    if start is not None:
        args += ["-start_number", str(start), "-f", "image2"]
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase:flags={SWS},crop={w}:{h}"
    args += ["-i", str(provenance), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    size = w * h * 3
    finished = False
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                finished = True
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        if not finished:
            proc.kill()  # the reader stopped early: stop ffmpeg instead of letting it fail on a closed pipe
        proc.stdout.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        proc.stderr.close()
        code = proc.wait()
    if code:
        raise RuntimeError(f"ffmpeg failed reading {provenance} (exit {code}): {err.strip()[-400:]}")


# ---------------------------------------------------------------- whole folder

def _rig(out: Path) -> dict | None:
    plan_path = out / "plan.json"
    if not plan_path.exists():
        return None
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    return next((op for op in plan["ops"] if op["op"] == "rig"), None)


def make_guides(write_to: str | Path, model: str, size: Sequence[int]) -> dict:
    """Write every guide this capture supports (see the module docstring); returns the guides record."""
    out = Path(write_to)
    w, h = int(size[0]), int(size[1])
    check_guide_size(model, w, h)
    cam = json.loads((out / "viewpoint.json").read_text(encoding="utf-8"))
    shaded = sorted((out / "shaded").glob("*.png"))
    if not shaded:
        raise FileNotFoundError(f"{out / 'shaded'} has no frames; capture the scene first")
    numbers = [int(p.stem) for p in shaded]
    if numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        raise ValueError("guides need consecutive frames; capture without --quick or a frame step")
    gdir = out / "controls"
    fps = cam["fps"]
    files: dict[str, str] = {}
    record = {"format": tag("controls"), "model": model, "size": [w, h], "frames": len(shaded),
              "first_number": numbers[0], "fps": fps, "files": files}

    depth_files = [out / "depth" / f"{n:04d}.exr" for n in numbers]
    if all(p.exists() for p in depth_files):
        lo, hi = depth_range((read_exr(p)["Z"] for p in depth_files), cam["far"])
        record["depth"] = {"kind": "inverse", "far_m": cam["far"], "near_m": 1.0 / hi, "white": "near"}
        depth_out = VideoWriter(gdir / f"depth-{model}.mp4", fps)
        edges_out = VideoWriter(gdir / f"edges-{model}.mp4", fps)
        for p in depth_files:
            z = read_exr(p)["Z"]
            depth_out.write(resize_cover(depth_to_guide(z, lo, hi), w, h))
            edges_out.write(resize_cover(depth_edges(z), w, h))
        depth_out.close()
        edges_out.close()
        files["depth"] = f"controls/depth-{model}.mp4"
        files["edges"] = f"controls/edges-{model}.mp4"

    frames = list(read_frames(out / "shaded" / "%04d.png", w, h, start=numbers[0]))
    write_video((canny(f) for f in frames), gdir / f"canny-{model}.mp4", fps)
    files["canny"] = f"controls/canny-{model}.mp4"
    write_png(gdir / f"first-{model}.png", frames[0])
    write_png(gdir / f"last-{model}.png", frames[-1])
    files["first"], files["last"] = f"controls/first-{model}.png", f"controls/last-{model}.png"

    rig = _rig(out)
    if rig is not None:
        by_f = {rec["f"]: rec for rec in cam["frames"]}
        pose = []
        for n in numbers:
            joints = rig["frames"][min(n, len(rig["frames"])) - 1]
            pose.append(draw_pose(project_joints(joints, by_f[n], cam["w"], cam["h"], w, h), w, h))
        write_video(pose, gdir / f"pose-{model}.mp4", fps)
        files["pose"] = f"controls/pose-{model}.mp4"

    (gdir / f"controls-{model}.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return record
