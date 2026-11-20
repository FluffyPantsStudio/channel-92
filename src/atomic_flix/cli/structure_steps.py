"""`structure`: the song's shape before the concept: sections sung and instrumental, story gaps and pacing, written
as analysis/structure.json and the page plan/structure.md that gate 1 shows beside the concept."""

from __future__ import annotations

from typing import Sequence

from ..formats import FormatError, check_format
from ..structure import STORY_GAP_S, StructureInputs, build_structure, reading, structure_page, timed_lines
from .common import Film, StepError, film_argument, parser, read_json, write_json
from ..project.layout import PULSE_FILE as PULSE
from ..project.layout import STRUCTURE_FILE as STRUCTURE_JSON
from ..project.layout import STRUCTURE_PAGE_FILE as STRUCTURE_PAGE
from .sound_steps import VOICE_LINES, _wav, lyric_text, measure_lines, measure_pulse

SWELLS = "analysis/swells.json"


def _read(film: Film, relative: str, kind: str) -> dict:
    data = read_json(film.path(relative))
    try:
        check_format(kind, data, relative)
    except FormatError as problem:
        raise StepError(str(problem)) from None
    return data


def _lines(film: Film, said: list[str]) -> tuple[tuple, tuple[str, ...]]:
    """The timed lead lines: read from voice-lines.json, or timed now with the `time` machinery when it is missing."""
    text = lyric_text(film)
    if not text.strip():
        return (), ("no lyric.txt: the sung stretches come from the vocal gaps alone",)
    if film.path(VOICE_LINES).is_file():
        data = _read(film, VOICE_LINES, "voice-lines")
        said.append(f"read {VOICE_LINES}")
    else:
        timing, _ = measure_lines(film)
        data = timing.to_dict()
        said.append(f"ran `time`: wrote {VOICE_LINES} (`atomic-flix time` prints its line table and flags)")
    return timed_lines(text, data)


def _pulse(film: Film, said: list[str]) -> tuple[tuple[float, ...] | None, str | None, tuple[dict, ...], list[str]]:
    """The bar's ones, the ruling and the swells: read from pulse.json, or found now with the `bars` machinery."""
    if film.path(PULSE).is_file():
        data = _read(film, PULSE, "pulse")
        said.append(f"read {PULSE}")
    else:
        try:
            data = measure_pulse(film).to_dict()
        except StepError as problem:
            return None, None, (), [f"no pulse ({problem}): edges are not snapped to the bar"]
        said.append(f"ran `bars`: wrote {PULSE} and {SWELLS} (check the bar's one by ear before gate 2)")
    swells = tuple(_read(film, SWELLS, "swells").get("swells") or ()) if film.path(SWELLS).is_file() else ()
    notes = [] if data.get("ones") else ["the pulse has no bar's one (`bars` could not choose and film.json has no "
                                         "downbeat_slot): edges are not snapped to the bar"]
    return (tuple(data["ones"]) if data.get("ones") else None), data.get("ruling"), swells, notes


def _rest(film: Film):
    for name in ("band", "mix"):
        path = film.stem(name)
        if path is not None:
            samples, rate = _wav(path)
            return samples, rate, name
    return None, None, "band"


def _summary(data: dict) -> list[str]:
    rows = [f"  {s['id']} {s['label']:<24} {s['kind']:<12} {s['start']:7.2f} {s['end']:7.2f}" for s in data["sections"]]
    gaps = data["pacing"]["story_gaps"]
    rows.append(f"story gaps ({data['pacing']['story_gap_threshold_s']:g} s or more): "
                + (", ".join(f"{g['start']:.1f} to {g['end']:.1f}" for g in gaps) or "none"))
    return rows


def _structure(argv: Sequence[str]) -> int:
    p = parser("structure", "The song's shape for the story, the first analysis, before gate 1: sections in time\n"
                            "order (from the lyric's [Section] lines, instrumental stretches where the lead stem is\n"
                            "silent), each on the bar, with how much is sung, how loud the band is and the swells;\n"
                            "then the story gaps (instrumental stretches the pictures must carry) and the pacing.\n"
                            "Writes analysis/structure.json and plan/structure.md, shown at gate 1 with the concept.\n"
                            "Runs `time` and `bars` first when their files are missing. Measured, not heard: a\n"
                            "person confirms the sections by ear at gate 2.")
    film_argument(p)
    p.add_argument("--gap", type=float, default=STORY_GAP_S,
                   help=f"shortest instrumental stretch counted as a story gap, seconds (default {STORY_GAP_S:g})")
    args = p.parse_args(argv)
    film = Film.open(args.film)
    lead_path = film.stem("voice")
    if lead_path is None:
        raise StepError("structure needs the lead vocal stem (audio/voice.wav, named in film.json stems.voice)")
    lead, lead_rate = _wav(lead_path)
    rest, rest_rate, rest_name = _rest(film)
    said: list[str] = []
    lines, line_notes = _lines(film, said)
    ones, ruling, swells, pulse_notes = _pulse(film, said)
    inputs = StructureInputs(lead=lead, lead_rate=lead_rate, rest=rest, rest_rate=rest_rate, rest_name=rest_name,
                             lines=lines, ones=ones, ruling=ruling, swells=swells,
                             notes=tuple(line_notes) + tuple(pulse_notes))
    data = build_structure(inputs, gap_s=args.gap)
    write_json(film.path(STRUCTURE_JSON), data, "structure")
    page = film.path(STRUCTURE_PAGE)
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(structure_page(data, film.data.get("name") or film.root.name), encoding="utf-8", newline="\n")
    print("\n".join(said + ["", reading(data), ""] + _summary(data)))
    print(f"wrote {STRUCTURE_JSON} and {STRUCTURE_PAGE} (show the page at gate 1 with the concept)")
    return 0


COMMANDS = {
    "structure": ("the song's sections, story gaps and pacing, before gate 1 (plan/structure.md)", _structure),
}
