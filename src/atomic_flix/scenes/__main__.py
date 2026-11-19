"""Command line for the scene toolkit.

  python -m atomic_flix.scenes check  SCENE.json
  python -m atomic_flix.scenes plan   SCENE.json > plan.json
  python -m atomic_flix.scenes capture SCENE.json OUT/ [--renderer raster|pathtrace] [--frames A:B] [--quick]
                                      [--spp N] [--size WxH] [--keep-exr]
  python -m atomic_flix.scenes blend  SCENE.json OUT/scene.blend
  python -m atomic_flix.scenes controls OUT/ --for ltx|scail|wan --size 1152x640

check, plan, capture and blend build from the pieces packaged with the kit. `--blocks DIR` uses your own block
folder instead (block.json plus build.py per folder, surfaces.json at its top); its build.py files run as Python
with your rights, so name only a folder you trust. A scene file can never point at a builder by itself.
"""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path

from .guides import make_guides, parse_size
from .library import Library
from .plan import compile_plan
from .capture import blend_scene, parse_frames, capture_scene
from .schema import SceneError, check_scene, load_scene


def _own_blocks(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--blocks", metavar="DIR", type=Path,
                     help="your own block folder in place of the packaged pieces (its build.py files run as Python)")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m atomic_flix.scenes", description="Blender building-block scenes")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="validate a scene and print what it resolves to")
    c.add_argument("scene")
    _own_blocks(c)
    p = sub.add_parser("plan", help="print the compiled op list")
    p.add_argument("scene")
    _own_blocks(p)
    r = sub.add_parser("capture", help="capture frames and layers with Blender")
    r.add_argument("scene")
    r.add_argument("out")
    _own_blocks(r)
    r.add_argument("--renderer", choices=["raster", "pathtrace"])
    r.add_argument("--frames", help="A:B, inclusive")
    r.add_argument("--quick", action="store_true", help="half size, 16 samples, every 4th frame")
    r.add_argument("--spp", type=int)
    r.add_argument("--size", help="WxH")
    r.add_argument("--keep-exr", action="store_true", help="keep Blender's multi-layer EXR per frame")
    b = sub.add_parser("blend", help="save the built scene as a .blend")
    b.add_argument("scene")
    b.add_argument("blend")
    _own_blocks(b)
    g = sub.add_parser("controls", help="control clips for a video model from a capture folder")
    g.add_argument("out")
    g.add_argument("--for", dest="model", required=True, choices=["ltx", "scail", "wan"])
    g.add_argument("--size", required=True, help="WxH, e.g. 1152x640")
    return ap


def _library(args: argparse.Namespace) -> Library:
    folder = getattr(args, "blocks", None)
    if folder is None:
        return Library.shipped()
    if not folder.is_dir():
        raise FileNotFoundError(f"--blocks: no folder at {folder}")
    return Library(folder)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        library = _library(args)
        if args.cmd == "check":
            r = check_scene(load_scene(args.scene), library)
            n = len(r["pieces"])
            print(f"{r['name']}: ok, {n} block entries, {r['size']['w']}x{r['size']['h']}, "
                  f"{r['size']['frames']} frames at {r['size']['fps']:g} fps, {r['capture']['renderer']}")
        elif args.cmd == "plan":
            print(json.dumps(compile_plan(load_scene(args.scene), library)))
        elif args.cmd == "capture":
            size = parse_size(args.size) if args.size else None
            info = capture_scene(args.scene, args.out, renderer=args.renderer, frames=parse_frames(args.frames),
                                quick=args.quick, samples=args.spp, size=size, keep_exr=args.keep_exr,
                                 library=library)
            print(f"{info['frames_rendered']} frames, {info['renderer']}: first {info['warmup_s']:.2f} s, then "
                  f"{info['warm_mean_render_s']:.3f} s capture + {info['mean_post_s']:.3f} s layers per frame "
                  f"({info.get('wall_fps', info['warm_fps']):.2f} frames per second by the clock)")
        elif args.cmd == "blend":
            print(blend_scene(args.scene, args.blend, library=library))
        else:
            rec = make_guides(args.out, args.model, parse_size(args.size))
            print(json.dumps(rec["files"], indent=1))
    except (SceneError, ValueError, FileNotFoundError, RuntimeError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
