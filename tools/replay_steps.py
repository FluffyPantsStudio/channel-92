"""Pieces of the first film's replay (see replay_first_film.py): turning our first film's files into a project,
placing its real takes on the song, reading the shipped v24 cut, and the GPU estimate for the new plan.

Read-only on the first film's folder. Every number the estimate uses is a named constant with its source.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from atomic_flix.cut.bars import beat_count
from atomic_flix.cut.edit import Cut, Edit, Placed, sung_intervals
from atomic_flix.cut.media import input_args
from atomic_flix.place import fit_by_sound, voiced_phrases
from atomic_flix.place.features import FEATURE_RATE, HOP_S, N_BANDS, resample, sound_features
from atomic_flix.programs import command_of
from atomic_flix.timing import Label, save_labels
from atomic_flix.wav import read_wav

BACKING = re.compile(r"\s*(\([^)]*\))\s*$")
LINE_ID = re.compile(r"\bL(\d{2})\b")
SEARCH_S = 4.0                 # a take is looked for this far either side of its window's start in the book


# --- inputs ----------------------------------------------------------------------------------------------------

def table_lines(build: Path) -> list[dict]:
    """The first film's hand-fixed line table (fixtures/first-film/build/lines.json), in its own shape."""
    return json.loads((build / "lines.json").read_text(encoding="utf-8"))["lines"]


def replay_lyric(text: str) -> str:
    """The film's lyric with a backing part at a line's end on a line of its own, as the hand-fixed table counts it
    ("Let's ride the magic tub (magical tub)" is two lines there: lead, then group)."""
    out = []
    for raw in text.splitlines():
        found = BACKING.search(raw)
        lead = raw[:found.start()].strip() if found else raw
        if found and lead and not raw.lstrip().startswith("("):
            out += [lead, found.group(1)]
        else:
            out.append(raw)
    return "\n".join(out) + "\n"


def replay_shots(text: str) -> str:
    """The shot list with the table's line ids (L01) as our timing stage numbers them (v01), in a vocal shot's
    header and in `act` fields only."""
    out = []
    for line in text.splitlines():
        head = re.match(r"^(\S+ vocal:|\s+act\s+)(.*)$", line)
        if head:
            line = head.group(1) + LINE_ID.sub(lambda m: f"v{m.group(1)}", head.group(2))
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def write_labels(words: Path, out: Path) -> None:
    """The first film's recognised words (fixture build/words.json) as our word-labels file."""
    data = json.loads(words.read_text(encoding="utf-8"))
    labels = [Label(w["w"], float(w["t0"]), float(w["t1"]), float(w.get("p", 1.0))) for w in data["words"]]
    save_labels(labels, out, model=str(data.get("model", "")))


def vocal_patches(lines: list[dict]) -> dict[str, list[float]]:
    return {f"v{row['id'][1:]}": [row["t0"], row["t1"]] for row in lines
            if row.get("t0") is not None and row.get("t1") is not None}


def link_or_copy(provenance: Path, aim: Path) -> None:
    aim.parent.mkdir(parents=True, exist_ok=True)
    if aim.exists():
        aim.unlink()
    try:
        os.link(provenance, aim)
    except OSError:
        shutil.copyfile(provenance, aim)


# --- the picked takes ------------------------------------------------------------------------------------------

def take_numbers(folder: Path) -> list[int]:
    return sorted(int(m.group(1)) for p in folder.glob("take-*.mp4") if (m := re.fullmatch(r"take-(\d+)\.mp4", p.name)))


def picked_take(takes: Path, key: str, picks: dict) -> tuple[Path, str]:
    """The book's pick for a shot, else its latest take (as the first film's build did)."""
    if key in picks:
        return takes / key / f"take-{picks[key]}.mp4", "book pick"
    numbers = take_numbers(takes / key)
    if not numbers:
        raise FileNotFoundError(f"no takes for {key}")
    return takes / key / f"take-{numbers[-1]}.mp4", "latest take"


def soundtrack(video: Path) -> np.ndarray | None:
    """A take's own sound, mono at 16 kHz, or None when it has none."""
    done = subprocess.run(command_of(["ffmpeg", "-v", "error", *input_args(video), "-vn", "-ac", "1",
                                      "-ar", str(FEATURE_RATE), "-f", "f32le", "-"]), capture_output=True)
    if done.returncode != 0 or not done.stdout:
        return None
    return np.frombuffer(done.stdout, dtype="<f4").astype(np.float64)


@dataclass(frozen=True)
class Lead:
    """The lead stem at 16 kHz and its sound features, for finding where a take's sound sits in the song."""

    samples: np.ndarray
    features: np.ndarray

    @classmethod
    def load(cls, path: Path) -> "Lead":
        samples, rate = read_wav(path)
        lead = resample(samples, rate, FEATURE_RATE)
        return cls(lead, sound_features(lead, FEATURE_RATE))

    def locate(self, clip: np.ndarray, near: float) -> float:
        """Song seconds where the render's sound starts, searched within SEARCH_S of `near`, by its voiced frames."""
        frames = sound_features(clip, FEATURE_RATE)
        vocal_on = frames[:, N_BANDS] == 0
        query = frames[vocal_on, :N_BANDS]
        rows = np.flatnonzero(vocal_on)
        first = max(0, int((near - SEARCH_S) / HOP_S))
        last = min(len(self.features) - len(frames), int((near + SEARCH_S) / HOP_S))
        best, best_at = -np.inf, near
        for start in range(first, max(first + 1, last)):
            score = float(np.einsum("ij,ij->", query, self.features[start + rows, :N_BANDS]))
            if score > best:
                best, best_at = score, start * HOP_S
        return best_at


def place_sung(lead: Lead, video: Path, window_start: float) -> dict:
    """Place a sung take by its sound: find it in the lead stem near its window, then fit it phrase by phrase on
    the lead silenced outside the span the take itself sounds in (the window it heard was gated so)."""
    clip = soundtrack(video)
    if clip is None:
        return {"how": "slice", "slice_start": window_start, "vocal_spans": [], "map": [[window_start, 0.0]],
                "added_rests": [], "offset": None, "note": "no soundtrack"}
    start = lead.locate(clip, window_start)
    first = int(round(start * FEATURE_RATE))
    sent = lead.samples[first:first + len(clip)].copy()
    vocal_spans = voiced_phrases(clip, FEATURE_RATE)
    if vocal_spans:
        times = np.arange(len(sent)) / FEATURE_RATE
        sent[(times < vocal_spans[0][0] - 0.07) | (times > vocal_spans[-1][1] + 0.25)] = 0.0
    fit = fit_by_sound(sent, FEATURE_RATE, clip[:len(sent)], FEATURE_RATE, vocal_spans=vocal_spans, slice_start=start)
    return {**fit, "window_in_book": window_start, "found_at": round(start, 3)}


# --- the shipped cut -------------------------------------------------------------------------------------------

def v24_edit(book: dict, takes: Path, fixture_beats: list[float], lines_table: list[dict], seconds: float) -> Edit:
    """The shipped v24 cut as an edit: the book's shown spans as the cuts, each shot's take at its book window."""
    picks = book.get("picks") or {}
    cuts, placed = [], {}
    for shot in book["shots"]:
        key = shot["id"]
        video, _ = picked_take(takes, key, picks)
        cuts.append(Cut(key=key, at=float(shot["show"][0])))
        kind = "vocal" if shot.get("kind") == "sung" else "cutaway"
        placed[key] = Placed(key=key, file=video, map=((float(shot.get("w0", shot["show"][0])), 0.0),), kind=kind,
                             cam_move=shot.get("cam_move"))
    voice_lines = {"lines": [{"start": row["t0"], "end": row["t1"], "gaps": row.get("pauses") or []}
                             for row in lines_table if row.get("t0") is not None]}
    return Edit(fps=24.0, size=(1920, 1080), song=None, start=0.0, end=seconds, cuts=tuple(cuts), takes=placed,
                pulse={"beats": list(fixture_beats), "downbeat_slot": 0}, sung=tuple(sung_intervals(voice_lines)))


def silent_tails(book: dict, lines_table: list[dict], shots_text: str) -> list[tuple[str, float]]:
    """Seconds each vocal shot of the shipped cut stays on screen after her last sound (rule P1 allows 1.0)."""
    finishes = {row["id"]: row["t1"] for row in lines_table if row.get("t1") is not None}
    sings = {m.group(1): m.group(2).split() for m in re.finditer(r"^(S\d+) vocal:\s*(.*)$", shots_text, re.M)}
    tails = []
    for shot in book["shots"]:
        key = shot["id"]
        own = [finishes[line] for line in sings.get(key, []) if line in finishes]
        if own:
            tails.append((key, round(float(shot["show"][1]) - max(own), 2)))
    return tails


def counts_of(times: list[float], beats: list[float], downbeat_slot: int) -> dict[str, int]:
    """How many cut times land on each count of the bar (1 to 4), or off the beat (more than 30 ms away)."""
    tally = {"1": 0, "2": 0, "3": 0, "4": 0, "off": 0}
    for at in times:
        count, _ = beat_count(at, beats, downbeat_slot)
        tally["off" if count is None else str(count)] += 1
    return tally
