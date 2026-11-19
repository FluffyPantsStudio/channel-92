"""Film steps that listen: `time` (every sung line), `bars` (beats and the bar's one) and `place` (each render on the
song, by its sound)."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

import numpy as np

from ..barmap import pulse
from ..cut.media import ENCODER_EXE, ERROR_TAIL
from ..place import check_fit, fit_by_sound
from ..timing import load_labels, time_lines, write_timing
from ..wav import WavError, read_wav
from .common import Film, StepError, film_argument, parser, write_json

LABELS = "analysis/word-labels.json"
RENDER_NAME = "r[0-9][0-9][0-9].mp4"
NO_AUDIO = ("does not contain any stream", "matches no streams", "Output file does not contain")


def _wav(path: Path) -> tuple[np.ndarray, int]:
    try:
        return read_wav(path)
    except (OSError, WavError) as problem:
        raise StepError(f"cannot read {path}: {problem}") from None


def _mono(samples: np.ndarray) -> np.ndarray:
    return samples.mean(axis=1) if samples.ndim == 2 else samples


def _time(argv: Sequence[str]) -> int:
    p = parser("time", "Time every sung line from the voice stem's level and write analysis/voice-lines.json.\n"
                       "Word labels in analysis/word-labels.json (when present) only say which words are where.\n"
                       "film.json vocal_patches [start, end] win over what is measured.")
    film_argument(p)
    film = Film.open(p.parse_args(argv).film)
    voice = film.stem("voice")
    if voice is None:
        raise StepError("no voice stem; add the lead vocal as audio/voice.wav and name it in film.json stems.voice")
    lyric = film.path(film.data.get("lyric") or "lyric.txt")
    text = lyric.read_text(encoding="utf-8") if lyric.is_file() else ""
    if not text.strip():
        raise StepError(f"{film.folder.relative(lyric)} is empty: write the lyric as sung first")
    samples, rate = _wav(voice)
    choir_path = film.stem("choir")
    choir, choir_rate = _wav(choir_path) if choir_path else (None, None)
    labels = load_labels(film.path(LABELS)) if film.path(LABELS).is_file() else None
    timing = time_lines(text, samples, rate, labels=labels, choir=choir, choir_rate=choir_rate,
                        fixes=film.data.get("vocal_patches") or {})
    out = write_timing(timing, film.path("analysis/voice-lines.json"))
    flagged = 0
    for line in timing.lines:
        when = f"{line.start:7.2f} {line.end:7.2f}" if line.start is not None else "  no time       "
        flagged += bool(line.flags)
        print(f"{line.id}  {when}  {line.provenance:<6} {line.text[:40]:<40} {'; '.join(line.flags)}".rstrip())
    timed = sum(1 for line in timing.lines if line.start is not None)
    print(f"{timed} of {len(timing.lines)} lines timed, {flagged} flagged (working level {timing.sung_db:.1f} dB); "
          f"wrote {film.folder.relative(out)}")
    return 0


def _bars(argv: Sequence[str]) -> int:
    p = parser("bars", "Find every beat and the bar's one; write analysis/pulse.json and analysis/swells.json.\n"
                       "Beats come from the drum stem, else the band, else the mix. A downbeat_slot in film.json (what\n"
                       "the person counted by ear) overrides the guess. Check it by ear with tools/click.py.")
    film_argument(p)
    p.add_argument("--bpm", type=float, help="a tempo hint when the guess lands on half or double time")
    args = p.parse_args(argv)
    film = Film.open(args.film)
    loaded = {name: _wav(path) for name in ("drums", "band", "mix") if (path := film.stem(name)) is not None}
    if not loaded:
        raise StepError("bars needs a drum, band or mix stem in film.json stems")
    rates = {rate for _, rate in loaded.values()}
    if len(rates) != 1:
        raise StepError(f"the drum, band and mix stems must share one sample rate, not {sorted(rates)}")
    rate = rates.pop()
    stems = {name: _mono(samples) for name, (samples, _) in loaded.items()}
    voice_path = film.stem("voice")
    voice, voice_rate = _wav(voice_path) if voice_path else (None, None)
    found = pulse(stems.get("drums"), rate, band=stems.get("band"), mix=stems.get("mix"),
                  vocal=_mono(voice) if voice is not None else None, vocal_rate=voice_rate, hint_bpm=args.bpm,
                  downbeat_slot=film.data.get("downbeat_slot"))
    found.write(film.path("analysis"))
    data = found.to_dict()
    print(f"{data['bpm']:.2f} BPM, {len(data['beats'])} beats, the one on beats with index mod 4 = "
          f"{data['downbeat_slot']} ({data['ruling']})")
    if data.get("question"):
        print(data["question"])
    print("wrote analysis/pulse.json and analysis/swells.json")
    return 0


def _clip_audio(clip: Path, scratch: Path) -> tuple[np.ndarray, int] | None:
    """The render's own soundtrack as mono 16 kHz, or None when it has none."""
    out = scratch / f"{clip.stem}.wav"
    command = [ENCODER_EXE, "-y", "-v", "error", "-nostdin", "-i", str(clip), "-vn", "-ac", "1", "-ar", "16000",
               "-c:a", "pcm_s16le", str(out)]
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        if any(sign in done.stderr for sign in NO_AUDIO):
            return None
        raise StepError(f"ffmpeg could not read {clip}: {done.stderr.strip()[-ERROR_TAIL:]}")
    samples, rate = read_wav(out)
    return (samples, rate) if len(samples) else None


def place_clip(film: Film, task: dict, clip: Path, scratch: Path) -> dict:
    """The fit of one render: by sound for a vocal render with a soundtrack, else the slice at 1x."""
    slice_start = float(task["slice_start"])
    slice_fit = {"how": "slice", "slice_start": slice_start, "vocal_spans": [], "map": [[round(slice_start, 3), 0.0]],
                 "added_rests": [], "offset": None}
    if task.get("type") != "vocal":
        return {**slice_fit, "flags": []}
    sent_path = film.path(task.get("audio") or "")
    if not task.get("audio") or not sent_path.is_file():
        return {**slice_fit, "flags": [{"id": "no-sent-audio", "level": "WARN", "phrase": None,
                                        "message": f"the audio sent to the render is missing ({task.get('audio')})"}]}
    heard = _clip_audio(clip, scratch)
    if heard is None:
        return {**slice_fit, "flags": [{"id": "no-soundtrack", "level": "WARN", "phrase": None,
                                        "message": "the render has no soundtrack, so it cannot be placed by sound"}]}
    sent, sent_rate = read_wav(sent_path)
    vocal_spans = [(float(a), float(b)) for a, b, *_ in task.get("vocal_spans") or []] or None
    fit = fit_by_sound(_mono(sent), sent_rate, heard[0][:, 0], heard[1], vocal_spans=vocal_spans, slice_start=slice_start)
    return {**fit, "flags": check_fit(fit)}


def _place(argv: Sequence[str]) -> int:
    p = parser("place", "Place every render on the song and write renders/<key>/rNNN.fit.json beside it.\n"
                        "A vocal render is placed by comparing its soundtrack with the audio it was sent; any\n"
                        "other render runs at 1x from the start of its slice.")
    film_argument(p)
    p.add_argument("keys", nargs="*", help="only these shots")
    p.add_argument("--again", action="store_true", help="place renders that already have a fit file again")
    args = p.parse_args(argv)
    film = Film.open(args.film)
    tasks = film.tasks()
    wanted = args.keys or list(tasks)
    placed = 0
    with tempfile.TemporaryDirectory() as scratch:
        for key in wanted:
            if key not in tasks:
                raise StepError(f"{key} is not a shot of the plan")
            for clip in sorted(film.path(f"renders/{key}").glob(RENDER_NAME)):
                fit_path = clip.with_suffix(".fit.json")
                if fit_path.is_file() and not args.again:
                    continue
                fit = place_clip(film, tasks[key], clip, Path(scratch))
                write_json(fit_path, fit, "fit")
                placed += 1
                costs = [phrase["cost"] for phrase in fit.get("vocal_spans", [])]
                worst = f", worst phrase cost {max(costs):.3f}" if costs else ""
                print(f"{key} {clip.stem}: {fit['how']}{worst}"
                      + "".join(f"\n  WARN {flag['message']}" for flag in fit["flags"]))
    print(f"placed {placed} render(s)")
    return 0


COMMANDS = {
    "time": ("time every sung line from the voice stem (analysis/voice-lines.json)", _time),
    "bars": ("beats and the bar's one from the drum stem (analysis/pulse.json)", _bars),
    "place": ("place each render on the song by its sound (renders/<key>/rNNN.fit.json)", _place),
}
