"""Write analysis/word-labels.json for a film by running a speech model on its voice stem.

usage: python tools/label_words.py FILM [--model large-v3] [--device cuda] [--device-index 0]

Needs `faster-whisper` (not a dependency of the kit: `pip install faster-whisper`). The labels only say which lyric
words were heard where; line starts still come from the voice stem's level (see timing/labels.py). The film's lyric
is given to the model as a prompt so that sung words are spelt as the lyric spells them.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from atomic_flix.timing.labels import Label, save_labels


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("film")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--device-index", type=int, default=0)
    ap.add_argument("--language", default="en")
    opts = ap.parse_args()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper is not installed: pip install faster-whisper", file=sys.stderr)
        return 2
    film = Path(opts.film)
    spec = json.loads((film / "film.json").read_text(encoding="utf-8"))
    voice = film / spec.get("audio", {}).get("voice", "audio/voice.wav")
    lyric = film / spec.get("lyric", "lyric.txt")
    prompt = " ".join(lyric.read_text(encoding="utf-8").split())[:600] if lyric.exists() else None
    model = WhisperModel(opts.model, device=opts.device, device_index=opts.device_index,
                         compute_type="float16" if opts.device == "cuda" else "int8")
    segments, _ = model.transcribe(str(voice), language=opts.language, word_timestamps=True,
                                   initial_prompt=prompt, vad_filter=False, condition_on_previous_text=False)
    labels = [Label(w.word.strip(), float(w.start), float(w.end), float(w.probability))
              for seg in segments for w in (seg.words or []) if w.word.strip()]
    out = film / "analysis" / "word-labels.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    save_labels(labels, out, model=f"faster-whisper {opts.model}")
    print(f"{len(labels)} words -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
