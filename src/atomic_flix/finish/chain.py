"""The finishing chain: a graded cut in, the delivered film out, in this order:

    1. the logo, laid over the top right of every frame (`brand.logo_box`), then the era's ffmpeg pre-filter,
       into a lossless temporary file (FFV1)
    2. the era look: ntsc-rs on that temporary file, into another lossless one, with the year's preset (a year
       between two eras' first years blends their presets and filters, `eras.year_look`; docs/eras.md)
    3. the final encode, the only lossy one: back to the film's size, the era's post-filter, the cut's own sound
    4. the intro, when there is one, joined in front (it is made in the era's style already, so it never goes
       through ntsc-rs)

The source is only read. The lossless temporary files go to a temporary folder beside the output (never the system's
temporary folder, which may be small or shared), the clean one is deleted as soon as the look file exists, and the
folder is removed at the end: grain and tape artefacts exist only in the final.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..brand.intro import join_intro
from ..brand.logo import logo_box, png_size
from ..cut.media import ENCODER_EXE, SCALE_FLAGS, ClipInfo, MediaError, input_args, probe, run_ffmpeg
from ..eras import Era, YearLook, era_look
from .ntsc import run_ntsc_rs, scale_lines

LOSSLESS = ["-c:v", "ffv1", "-pix_fmt", "yuv420p"]
SAMPLE_SECONDS = 1.0
PRESET_NAME = "look-preset.json"


@dataclass(frozen=True)
class Treatment:
    """What the chain lays on: LOGO (a PNG or None), ERA (or None), the ntsc-rs to run it with (None: no look) and
    YEAR_LOOK, the preset and filters for the film's year (`eras.year_look`; None: ERA's own look exactly)."""

    logo: Path | None = None
    era: Era | None = None
    ntsc: Path | None = None
    year_look: YearLook | None = None

    @property
    def look(self) -> bool:
        return self.era is not None and self.ntsc is not None

    @property
    def style(self) -> YearLook | None:
        """The look laid on: YEAR_LOOK, else ERA's own; None without an era."""
        if self.era is None:
            return None
        return self.year_look or era_look(self.era)


@dataclass
class Finished:
    """What `finish_cut` wrote, whether the era look is on it, and a plain line for each step it ran."""

    out: Path
    look: bool
    notes: list[str] = field(default_factory=list)


def _logo_graph(logo: Path, size: tuple[int, int]) -> str:
    x, y, w, h = logo_box(*size, png_size(logo))
    # The overlay works in yuv420 itself: any other working format converts the whole frame and moves every pixel.
    return (f"[1:v]scale={w}:{h}:flags={SCALE_FLAGS},format=yuva420p[mark];"
            f"[base][mark]overlay={x}:{y}:format=yuv420:eof_action=repeat[marked]")


def stage_picture(source: Path, out: Path, info: ClipInfo, treatment: Treatment, lead: str = "") -> Path:
    """Step 1: SOURCE's picture with the logo and the era's pre-filter, lossless and silent, into OUT."""
    command = [ENCODER_EXE, "-y", "-v", "error", "-nostdin", *input_args(source)]
    graph = [f"[0:v]{lead + ',' if lead else ''}setsar=1,format=yuv420p[base]"]
    last = "base"
    if treatment.logo is not None:
        command += input_args(treatment.logo)
        graph.append(_logo_graph(treatment.logo, (info.width, info.height)))
        last = "marked"
    prefilter = treatment.style.prefilter if treatment.look else None
    graph.append(f"[{last}]{prefilter + ',' if prefilter else ''}format=yuv420p[picture]")
    command += ["-filter_complex", ";".join(graph), "-map", "[picture]", "-an", *LOSSLESS, str(out)]
    run_ffmpeg(command, f"lay the logo and pre-filter on {source.name}")
    return out


def _final_filter(info: ClipInfo, treatment: Treatment) -> str:
    post = treatment.style.postfilter if treatment.look else None
    return ",".join(part for part in (f"scale={info.width}:{info.height}:flags={SCALE_FLAGS}", "setsar=1", post,
                                      f"fps={info.fps:g}", "format=yuv420p") if part)


def encode_final(picture: Path, sound: Path, out: Path, info: ClipInfo, treatment: Treatment,
                 video: list[str]) -> Path:
    """Step 3: PICTURE at the film's size with SOUND's audio (copied as it is), encoded with VIDEO's options."""
    command = [ENCODER_EXE, "-y", "-v", "error", "-nostdin", *input_args(picture), *input_args(sound),
               "-filter_complex", f"[0:v]{_final_filter(info, treatment)}[v]", "-map", "[v]", "-map", "1:a?",
               "-c:a", "copy", *video, "-frames:v", str(info.frames), str(out)]
    run_ffmpeg(command, f"encode {out.name}")
    return out


def _x264(crf: int, speed: str) -> list[str]:
    return ["-c:v", "libx264", "-preset", speed, "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def _look(picture: Path, work: Path, info: ClipInfo, treatment: Treatment, notes: list[str]) -> Path:
    """Step 2: the era look on the clean PICTURE (deleted once the look file exists); PICTURE itself when no look.
    The look's preset is written into WORK (the year's blend, or the era's own) and goes with it."""
    if not treatment.look:
        notes.append("no era look")
        return picture
    style = treatment.style
    preset = work / PRESET_NAME
    preset.write_text(json.dumps(style.preset, indent=1), encoding="utf-8")
    lines = scale_lines(treatment.era.lines, info.width, info.height)
    looked = run_ntsc_rs(treatment.ntsc, picture, work / "look.mkv", preset, lines)
    picture.unlink(missing_ok=True)
    preset.unlink(missing_ok=True)
    notes.append(f"{style.describe()}, through ntsc-rs at {lines} lines ({treatment.era.lines} on the short side)")
    return looked


def finish_cut(source: Path, out: Path, treatment: Treatment, intro: Path | None = None, *, crf: int = 16,
               speed: str = "slow") -> Finished:
    """Run the chain on SOURCE into OUT (written only when every step succeeds). SOURCE is only read."""
    source, out = Path(source), Path(out)
    info = probe(source)
    partial = out.with_name(out.stem + ".partial" + out.suffix)
    notes = [f"logo: {treatment.logo.name if treatment.logo else 'none'}"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".finish-", dir=out.parent) as work:
        work = Path(work)
        picture = _look(stage_picture(source, work / "clean.mkv", info, treatment), work, info, treatment, notes)
        try:
            if intro is None:
                encode_final(picture, source, partial, info, treatment, _x264(crf, speed))
            else:
                body = encode_final(picture, source, work / "body.mkv", info, treatment, LOSSLESS)
                join_intro(intro, body, partial, crf=crf, x264_speed=speed)
                notes.append(f"the intro {Path(intro).name} joined in front")
        except MediaError:
            partial.unlink(missing_ok=True)
            raise
    partial.replace(out)
    return Finished(out=out, look=treatment.look, notes=notes)


def sample_still(still: Path, out: Path, size: tuple[int, int], fps: float, treatment: Treatment) -> Path:
    """One frame of the chain on STILL, filled to SIZE: what the era's look and logo do, to approve by eye."""
    width, height = size
    frames = max(2, round(SAMPLE_SECONDS * fps))
    info = ClipInfo(width=width, height=height, fps=fps, frames=frames)
    fill = (f"scale={width}:{height}:force_original_aspect_ratio=increase:flags={SCALE_FLAGS},crop={width}:{height},"
            f"loop=loop={frames - 1}:size=1,setpts=N/({fps:g}*TB)")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sample-", dir=out.parent) as work:
        work = Path(work)
        picture = _look(stage_picture(Path(still), work / "clean.mkv", info, treatment, lead=fill), work, info,
                        treatment, [])
        command = [ENCODER_EXE, "-y", "-v", "error", "-nostdin", *input_args(picture), "-vf",
                   f"select='eq(n,{frames // 2})',{_final_filter(info, treatment)}", "-frames:v", "1",
                   "-update", "1", str(out)]
        run_ffmpeg(command, f"take the sample frame from {Path(still).name}")
    return out


__all__ = ["Finished", "Treatment", "encode_final", "finish_cut", "sample_still", "stage_picture"]
