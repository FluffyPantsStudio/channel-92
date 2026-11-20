"""The era intros: a silent clip that reveals the era's logo over the era's own background, made with ffmpeg alone.

Each intro is made at the film's frame size and frame rate, INTRO_SECONDS long, and kept in the film's folder as
`brand/intro-<era>-<W>x<H>-<fps>fps-v<INTRO_VERSION>-<logo hash>.mp4`, so it is made once per size, and made again
when the era's logo file or the intro's design (INTRO_VERSION) changes. It is drawn in the era's style already, so
`finish` joins it after the era look, never running it through ntsc-rs. The backgrounds, in the era's graphic
language:

    1950s  a monochrome test-pattern card (rings, a grid, a grey-step wedge) with a faint flicker
    1960s  bold flat colour blocks laid down one after another on cream
    1970s  warm brown to orange with stacked orange, amber and yellow stripes
    1980s  a neon grid floor under a purple to pink sky; the chrome logo slides in
    1990s  black with cyan and magenta bars; the logo arrives in a colour-split glitch
    2000s  clean digital blue with a glossy silver bevelled plate behind the channel's own mark
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..cut.media import ENCODER_EXE, FILE_ONLY, MediaError, run_ffmpeg
from ..eras import Era
from .intro import IntroError
from .logo import png_size

INTRO_VERSION = 1               # raise it whenever the intros' design changes, so kept intros are made again
LOGO_HASH_CHARS = 12
INTRO_SECONDS = 5.0
REVEAL_AT, REVEAL_FOR = 0.9, 1.2
LOGO_BOX = (0.62, 0.5)          # share of the frame's width and height the logo may fill


def logo_size(era: Era, size: tuple[int, int]) -> tuple[int, int]:
    """The logo's size in the intro: as large as fits LOGO_BOX, even on both sides."""
    width, height = size
    native_w, native_h = png_size(era.logo)
    scale = min(LOGO_BOX[0] * width / native_w, LOGO_BOX[1] * height / native_h)
    return max(2, int(native_w * scale) // 2 * 2), max(2, int(native_h * scale) // 2 * 2)


def _source(kind: str, size: tuple[int, int], fps: float, extra: str = "") -> str:
    width, height = size
    return f"{kind}=s={width}x{height}:r={fps:g}:d={INTRO_SECONDS:g}{extra}"


def _fifties(size, fps, box) -> tuple[str, str, str]:
    width, height = size
    lum = ("if(between(hypot(X-W/2,Y-H/2),0.40*H,0.425*H),235,"
           "if(lt(hypot(X-W/2,Y-H/2),0.40*H),60+60*lt(mod(hypot(X-W/2,Y-H/2),0.08*H),0.04*H),"
           "if(gt(Y,0.84*H),30+200*floor(X*8/W)/7,"
           "if(lt(mod(X,H/12),2)+lt(mod(Y,H/12),2),200,120))))")
    frames = round(INTRO_SECONDS * fps)
    background = (f"color=c=gray:s={width}x{height}:r={fps:g}:d={1 / fps:.6f},geq=lum='{lum}':cb=128:cr=128,"
                  f"loop=loop={frames - 1}:size=1,setpts=N/({fps:g}*TB)")
    after = "hue=s=0,noise=alls=8:allf=t,eq=brightness='0.02*sin(2*PI*t*6)':eval=frame,vignette=angle=0.5"
    return background, _centred(box), after


def _sixties(size, fps, box) -> tuple[str, str, str]:
    width, height = size
    blocks = [(0, 0, width // 3, height, "0x1f7a8c", 0.15), (width * 2 // 3, 0, width - width * 2 // 3,
                                                             height * 2 // 3, "0xd1462f", 0.4),
              (width // 3, height * 3 // 4, width // 3, height // 4, "0xe0a526", 0.65)]
    drawn = ",".join(f"drawbox=x={x}:y={y}:w={w}:h={h}:color={c}:t=fill:enable='gte(t,{at})'"
                     for x, y, w, h, c, at in blocks)
    return _source("color", size, fps, ":c=0xf4ead5") + "," + drawn, _centred(box), ""


def _seventies(size, fps, box) -> tuple[str, str, str]:
    width, height = size
    band = height // 14
    stripes = ",".join(f"drawbox=x=0:y={height // 2 + i * band}:w={width}:h={band}:color={c}:t=fill"
                       for i, c in enumerate(("0xe8702a", "0xf2a33a", "0xf6d06f")))
    background = (_source("gradients", size, fps, f":c0=0x3b200c:c1=0x9c4a1a:x0=0:y0=0:x1=0:y1={height}:speed=0")
                  + "," + stripes)
    return background, _centred(box), ""


def _eighties(size, fps, box) -> tuple[str, str, str]:
    width, height = size
    half = height // 2
    sky = _source("gradients", size, fps, f":c0=0x12002b:c1=0xff2e9f:x0=0:y0=0:x1=0:y1={half}:speed=0")
    floor = (f"color=c=0x0d0020:s={width}x{height - half}:r={fps:g}:d={INTRO_SECONDS:g},"
             f"drawgrid=x={max(4, width // 12) // 2}:w={max(4, width // 12)}:h={max(4, half // 6)}:t=2:c=0xff3cc8,"
             f"perspective=x0={width * 0.42:.0f}:y0=0:x1={width * 0.58:.0f}:y1=0:x2={-width * 0.6:.0f}:"
             f"y2={height - half}:x3={width * 1.6:.0f}:y3={height - half}:sense=destination")
    background = f"{sky}[sky];{floor}[floor];[sky][floor]overlay=0:{half}"
    x, y = box
    slide = f"x='min({x},{x}+(t-{REVEAL_AT + REVEAL_FOR})*{width})':y={y}"
    return background, slide, ""


def _nineties(size, fps, box) -> tuple[str, str, str]:
    width, height = size
    bars = (f"drawbox=x=0:y={height // 6}:w={width // 2}:h={height // 9}:color=0x00e6ff:t=fill,"
            f"drawbox=x={width // 2}:y={height * 3 // 4}:w={width // 2}:h={height // 9}:color=0xff00c8:t=fill")
    x, y = box
    jitter = f"x='{x}+if(lt(t,{REVEAL_AT + REVEAL_FOR}),{max(4, width // 40)}*sin(t*53)*gt(sin(t*17),0.2),0)':y={y}"
    glitch = (f"rgbashift=rh=-{max(2, width // 120)}:bh={max(2, width // 120)}:"
              f"enable='lt(t,{REVEAL_AT + REVEAL_FOR + 0.3})',noise=alls=12:allf=t")
    return _source("color", size, fps, ":c=0x050508") + "," + bars, jitter, glitch


def _two_thousands(size, fps, box) -> tuple[str, str, str]:
    width, height = size
    x, y = box
    plate_w, plate_h = width - 2 * x + 2 * (width // 20), height - 2 * y + 2 * (height // 14)
    px, py = (width - plate_w) // 2, (height - plate_h) // 2
    edge = max(2, height // 120)
    plate = (f"drawbox=x={px}:y={py}:w={plate_w}:h={plate_h}:color=0xd9dde3:t=fill,"
             f"drawbox=x={px}:y={py}:w={plate_w}:h={plate_h // 2}:color=white@0.45:t=fill,"
             f"drawbox=x={px}:y={py}:w={plate_w}:h={edge}:color=white:t=fill,"
             f"drawbox=x={px}:y={py + plate_h - edge}:w={plate_w}:h={edge}:color=0x6f7a8a:t=fill")
    background = (_source("gradients", size, fps, f":c0=0x0a3d91:c1=0x1e88e5:x0=0:y0=0:x1=0:y1={height}:speed=0")
                  + "," + plate)
    return background, _centred(box), ""


def _centred(box: tuple[int, int]) -> str:
    return f"x={box[0]}:y={box[1]}"


STYLES = {"1950s": _fifties, "1960s": _sixties, "1970s": _seventies, "1980s": _eighties, "1990s": _nineties,
          "2000s": _two_thousands}


def intro_graph(era: Era, size: tuple[int, int], fps: float) -> str:
    """The filter graph: the era's background, the logo fading in over it, the era's finish, a fade at each end."""
    width, height = size
    logo_w, logo_h = logo_size(era, size)
    box = ((width - logo_w) // 2, (height - logo_h) // 2)
    background, place, after = STYLES[era.id]((width, height), fps, box)
    ends = f"fade=t=in:st=0:d=0.3,fade=t=out:st={INTRO_SECONDS - 0.4:g}:d=0.4"
    tail = ",".join(part for part in (after, ends, "format=yuv420p") if part)
    return (f"{background}[bg];[0:v]scale={logo_w}:{logo_h}:flags=lanczos,format=rgba,"
            f"fade=t=in:st={REVEAL_AT:g}:d={REVEAL_FOR:g}:alpha=1[logo];"
            f"[bg][logo]overlay={place}:format=auto:shortest=1,{tail}[v]")


def build_era_intro(era: Era, size: tuple[int, int], fps: float, out: Path | str) -> Path:
    """Write ERA's intro at SIZE and FPS to OUT (silent, INTRO_SECONDS long). Returns OUT, written only on success."""
    out = Path(out)
    width, height = size
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise MediaError(f"an intro needs an even frame size, not {width}x{height}")
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.stem + ".partial" + out.suffix)
    frames = round(INTRO_SECONDS * fps)
    # The logo is the package's own PNG, looped by the image demuxer (which the forced png_pipe would not loop).
    command = [ENCODER_EXE, "-y", "-v", "error", "-nostdin", "-loop", "1", "-framerate", f"{fps:g}",
               "-t", f"{INTRO_SECONDS:g}", *FILE_ONLY, "-i", str(era.logo),
               "-filter_complex", intro_graph(era, size, fps),
               "-map", "[v]", "-an", "-frames:v", str(frames), "-r", f"{fps:g}", "-c:v", "libx264",
               "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(partial)]
    try:
        run_ffmpeg(command, f"make the {era.id} intro")
    except MediaError:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(out)
    return out


def era_intro(film_root: Path | str, era: Era, size: tuple[int, int], fps: float) -> Path:
    """The era's intro for a film of SIZE and FPS, made once and kept in the film's brand/ folder; IntroError when
    that folder leads outside the film folder."""
    width, height = size
    digest = hashlib.sha256(era.logo.read_bytes()).hexdigest()[:LOGO_HASH_CHARS]
    root = Path(film_root).resolve()
    kept = (root / "brand").resolve() / f"intro-{era.id}-{width}x{height}-{fps:g}fps-v{INTRO_VERSION}-{digest}.mp4"
    if not kept.is_relative_to(root):
        raise IntroError(f"{kept.parent} is outside the film folder; the era intro is kept only in the film's own "
                         "brand/ folder")
    return kept if kept.is_file() else build_era_intro(era, size, fps, kept)


__all__ = ["INTRO_SECONDS", "build_era_intro", "era_intro", "intro_graph", "logo_size"]
