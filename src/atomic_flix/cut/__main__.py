"""Command line for cutting.

    python -m atomic_flix.cut audit EDIT.json [--both-sides] [--json OUT]
    python -m atomic_flix.cut encode EDIT.json OUT.mp4 [--crf 16] [--speed slow]
    python -m atomic_flix.cut flash FILM.mp4 [--json OUT]

`encode` writes OUT.mp4 and OUT.audit.json beside it. Exit code 1 on any audit error or a failed flash check.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..formats import stamped
from .audit import audit_edit
from .edit import EditError, load_edit
from .flash import check_flashes
from .media import MediaError
from .render import CutError, render_cut


def _write_json(path: Path, data: dict, kind: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stamped(kind, data), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _audit(args) -> int:
    account = audit_edit(load_edit(args.edit), compare_frames=args.both_sides)
    print(account.text())
    if args.json:
        _write_json(Path(args.json), account.to_dict(), "audit")
    return 1 if account.errors else 0


def _encode(args) -> int:
    out = Path(args.out)
    result = render_cut(load_edit(args.edit), out, crf=args.crf, x264_speed=args.speed)
    print(result.audit.text())
    audio = result.audio
    if audio:
        print(f"song: {audio['measured_lufs']} LUFS, peak {audio['measured_peak_db']} dBFS, gain {audio['trim_db']:+} dB"
              f" -> {audio['lufs_after']} LUFS, peak {audio['peak_after_db']} dBFS")
    for warning in result.warnings:
        if warning not in result.audit.warnings:
            print(f"WARN  {warning}")
    _write_json(out.with_suffix(".audit.json"), {**result.audit.to_dict(), "audio": audio,
                                                 "warnings_all": result.warnings}, "audit")
    print(f"wrote {out}")
    return 0


def _flash(args) -> int:
    account = check_flashes(args.film)
    print(account.text())
    if args.json:
        _write_json(Path(args.json), account.to_dict(), "strobe")
    return 0 if account.passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m atomic_flix.cut", description="Cut on the bar, audit, flash check.")
    verbs = parser.add_subparsers(dest="verb", required=True)
    audit = verbs.add_parser("audit", help="list every cut: count, lengths, rates, held notes, jump cuts")
    audit.add_argument("edit")
    audit.add_argument("--both-sides", action="store_true", help="also compare the frames either side of each cut")
    audit.add_argument("--json")
    audit.set_defaults(run=_audit)
    encode = verbs.add_parser("encode", help="write the edit in one encode with the song at -14 LUFS")
    encode.add_argument("edit")
    encode.add_argument("out")
    encode.add_argument("--crf", type=int, default=16)
    encode.add_argument("--speed", default="slow")
    encode.set_defaults(run=_encode)
    flash = verbs.add_parser("flash", help="photosensitivity flash check of a film")
    flash.add_argument("film")
    flash.add_argument("--json")
    flash.set_defaults(run=_flash)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except (EditError, CutError, MediaError, FileNotFoundError) as problem:
        print(f"ERROR {problem}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
