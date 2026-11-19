"""Checks on the plan: cuts, slices, steps, pins, the grid and the line table."""

from __future__ import annotations

from ..plan.cuts import PIN_EXIT
from ..setups import reads_as_jump, size_note
from ..plan.slices import HEAD, MAX_SECONDS, MIN_SECONDS, TAIL
from ..plan.vocab import camera_moves
from .book import Book
from .registry import rule
from .text import found

EPS = 1e-6
SHORTEST = 1.6
GATE_DB_BELOW_WORKING = 18.0


def _rd(book: Book):
    return book.rules_dir


def tasks(book: Book, kinds: tuple[str, ...] | None = None):
    for shot in book.shots:
        task = book.tasks.get(shot.key)
        if task and (kinds is None or shot.kind in kinds):
            yield shot, task


def _first_last(book: Book, shot, task) -> tuple[float | None, float | None]:
    timed = [book.lines[key] for key in shot.sings if key in book.lines and book.lines[key].timed]
    first = task.get("first_sound", min((line.start for line in timed), default=None))
    last = task.get("last_sound", max((line.end for line in timed), default=None))
    return first, last


def _shown(task) -> tuple[float, float]:
    return task["shown_at"][0] - task["slice_start"], task["shown_at"][1] - task["slice_start"]


@rule("P1")
def pinned_tail(book):
    for shot, task in tasks(book, ("vocal",)):
        _, last = _first_last(book, shot, task)
        if task.get("pin", "full") == "full" and last is not None:
            held = task["shown_at"][1] - last
            if held > PIN_EXIT + EPS:
                yield shot.key, f"pinned and on screen {held:.2f} s after her last sound"


@rule("P2")
def pin_under_moving_camera(book):
    for shot, task in tasks(book):
        cam_move = shot.cam_move or task.get("cam_move")
        if (task.get("pin") or "none") != "none" and camera_moves(cam_move, _rd(book)):
            yield shot.key, f"last frame pinned ({task.get('pin')}) under a moving camera ({cam_move!r})"


@rule("P3")
def locked_and_nothing_moves(book):
    for shot, task in tasks(book, ("cutaway",)):
        shown = task["shown_at"][1] - task["shown_at"][0]
        cam_move = shot.cam_move or task.get("cam_move")
        if shown <= 6.0 or camera_moves(cam_move, _rd(book)):
            continue
        said = " ".join([step[4] or "" for step in task.get("steps", [])] + list(shot.beats))
        if not found("motion", said, _rd(book)):
            yield shot.key, f"locked for {shown:.1f} s and nothing moves"


@rule("P4")
def pinned_listening(book):
    for shot, task in tasks(book, ("vocal",)):
        if (task.get("pin") or "full") == "none":
            continue
        shown = _shown(task)
        for start, end, part, _, _ in task.get("steps", []):
            if part != "rest":
                continue
            seen = min(end, shown[1]) - max(start, shown[0])
            if seen > 1.5 + EPS:
                yield shot.key, f"{start}-{end}s: {seen:.1f} s of silence shown in a pinned take"


@rule("E1")
def events_outside_the_cut(book):
    for shot, task in tasks(book):
        shown_end = _shown(task)[1]
        for index, (start, end, part, _, text) in enumerate(task.get("steps", [])):
            if index and part != "rest" and start > shown_end - 1.0 + EPS:
                yield shot.key, f"{start}-{end}s ({text or 'sung'}) starts after what the cut shows ({shown_end:.2f} s)"


@rule("L050")
def full_voice_heard(book):
    for shot, task in tasks(book, ("vocal",)):
        if not str(task.get("audio") or "").endswith("voice-soft.wav"):
            yield shot.key, f"hears {task.get('audio')!r}, not the soft copy"


def _crop(book: Book, shot) -> float | None:
    if shot.crop is not None:
        return shot.crop
    return (book.keyframes.get(shot.key) or {}).get("crop_keep")


@rule("C1")
def same_setup_same_size(book):
    vocal = [(index, shot) for index, shot in enumerate(book.shots) if shot.kind == "vocal"]
    for (i, left), (j, right) in zip(vocal, vocal[1:]):
        if j - i > 2 or not left.setup or left.setup != right.setup:
            continue
        a, b = _crop(book, left), _crop(book, right)
        if reads_as_jump(left.setup, a, right.setup, b):
            yield right.key, f"{left.key} and {right.key} on setup {left.setup} at {size_note(a, b)}"


@rule("L004")
def prop_not_registered(book):
    props = [name.lower() for name in book.film.get("props") or {}]
    for data in (book.film.get("props") or {}).values():
        props += [word.lower() for word in (data or {}).get("words") or []]
    if not props:
        return
    for shot in book.shots:
        main = shot.beats[0] if shot.beats else next(iter(shot.acts.values()), "")
        if not main or (shot.extra or {}).get("exception"):
            continue
        if found("handling", main, _rd(book)) and not any(prop in main.lower() for prop in props):
            yield shot.key, f"the main action handles something not in the prop list: {main!r}"


@rule("L020")
def gaze_missing(book):
    for shot in book.shots:
        if shot.has_person and not (shot.extra or {}).get("gaze"):
            yield shot.key, "no gaze or screen direction"


@rule("L057")
def small_face_repair(book):
    for shot in book.shots:
        extra = shot.extra or {}
        if extra.get("repair") in ("lips", "face") and float(extra.get("face_px", 0)) < 60:
            yield shot.key, f"a {extra['repair']} job on a {extra.get('face_px')} px face"


def _ratio(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and "/" in value:
        top, bottom = value.split("/", 1)
        return float(top) / float(bottom) if float(bottom) else None
    return float(value)


@rule("L060")
def bar_one_unconfirmed(book):
    if book.pulse is None or book.film.get("downbeat_slot") is not None or book.gate("bars"):
        return
    grounds = dict(book.pulse.grounds or {})
    clearance, agree = grounds.get("clearance"), _ratio(grounds.get("spans_backing"))
    if clearance is None or agree is None:
        yield None, "the bar's one has no evidence (margin, stretches) and no ear check"
    elif clearance < 0.3 or agree < 0.8:
        yield None, f"bar one margin {clearance:g}, stretches agree {agree:.0%}: confirm by ear and set downbeat_slot"


@rule("L061")
def untimed_or_unchecked_lines(book):
    checked = set(book.film.get("checked_lines") or [])
    for key, line in book.lines.items():
        if not line.timed:
            yield None, f"line {key} has no time"
        elif line.flags and line.provenance != "fixed" and key not in checked:
            yield None, f"line {key} is flagged ({'; '.join(line.flags)}) and not checked"


def _extra(shot, name: str) -> str:
    return str((shot.extra or {}).get(name, "")).strip().lower()


@rule("L072")
def chained_pieces(book):
    for shot in book.shots:
        pieces = _extra(shot, "pieces")
        if pieces and int(float(pieces)) > 1 and _extra(shot, "joins_are_cuts") not in ("yes", "true"):
            yield shot.key, f"built from {pieces} generations with joins not declared as cuts"


@rule("L074")
def guide_slowed(book):
    for shot in book.shots:
        retime = _extra(shot, "guide_retime")
        if retime and float(retime) < 1.0:
            yield shot.key, f"motion guide slowed to {retime}x"


@rule("L082")
def thin_parts_on_depth(book):
    for shot in book.shots:
        if "thin" in _extra(shot, "tags") and _extra(shot, "guide") == "depth":
            yield shot.key, "thin moving parts on a depth guide"


@rule("L083")
def depth_with_other_build(book):
    for shot in book.shots:
        if _extra(shot, "guide") == "depth" and _extra(shot, "build_differs") in ("yes", "true"):
            yield shot.key, "depth guide while the character's build differs from the performer's"


@rule("CUT1")
def cuts_in_order(book):
    cuts = book.cuts
    for left, right in zip(cuts, cuts[1:]):
        if right["at"] <= left["at"] + EPS:
            yield right["key"], f"cut at {right['at']:.2f} is not after {left['key']} at {left['at']:.2f}"
        elif right["at"] - left["at"] < SHORTEST - EPS:
            yield left["key"], f"on screen {right['at'] - left['at']:.2f} s, under {SHORTEST} s"
    if cuts and book.ends_at is not None and book.ends_at - cuts[-1]["at"] < SHORTEST - EPS:
        yield cuts[-1]["key"], f"on screen {book.ends_at - cuts[-1]['at']:.2f} s before the song ends"


@rule("CUT2")
def off_grid_without_reason(book):
    for cut in book.cuts:
        if cut.get("grid") == "off" and "person" not in (cut.get("note") or ""):
            yield cut["key"], f"cut at {cut['at']:.2f} is off the one and three ({cut.get('note') or 'no reason'})"


@rule("WIN1")
def window_bounds(book):
    for shot, task in tasks(book):
        seconds = task.get("seconds")
        if not isinstance(seconds, int) or not MIN_SECONDS <= seconds <= MAX_SECONDS:
            yield shot.key, f"render of {seconds} s (whole seconds, {MIN_SECONDS} to {MAX_SECONDS})"
            continue
        start, end = task["shown_at"]
        if task["slice_start"] > start - HEAD + EPS and task["slice_start"] > EPS:
            yield shot.key, f"render starts at {task['slice_start']:.2f}, under {HEAD} s before the cut"
        if task["slice_start"] + seconds < end + TAIL - EPS:
            yield shot.key, f"render ends at {task['slice_start'] + seconds:.2f}, before the shot's end plus {TAIL} s"


@rule("L1")
def run_up(book):
    for shot, task in tasks(book, ("vocal",)):
        first, _ = _first_last(book, shot, task)
        if first is None:
            continue
        lead = first - task["slice_start"]
        if not 0.5 - EPS <= lead <= 1.0 + EPS:
            yield shot.key, f"lead-in {lead:.2f} s before her first sound"


@rule("G1")
def gate_edge_in_sound(book):
    if book.sung_db is None:
        return
    limit = book.sung_db - GATE_DB_BELOW_WORKING
    for shot, task in tasks(book, ("vocal",)):
        edges, gate = task.get("gate_edges_db"), task.get("gate")
        if not edges or not gate:
            continue
        rivals = [line for key, line in book.lines.items() if key not in shot.sings and line.timed]
        for index, (level, edge) in enumerate(zip(edges, gate)):
            touches = any(abs(line.end - edge) <= 0.05 or abs(line.start - edge) <= 0.05
                          or line.start < edge < line.end for line in rivals)
            if level > limit and not touches:
                side = "start" if index == 0 else "end"
                yield shot.key, f"gate {side} at {edge:.2f} cuts into sound ({level:.1f} dB, working {book.sung_db:.1f})"


def _own_lines(book: Book, shot):
    return [book.lines[key] for key in shot.sings if key in book.lines and book.lines[key].timed]


@rule("T2")
def step_quotes_far_words(book):
    for shot, task in tasks(book, ("vocal",)):
        for step, keys in zip(task.get("steps", []), task.get("step_lines", [])):
            for key in keys:
                line = book.lines.get(key)
                if not line or not line.timed:
                    continue
                start, end = line.start - task["slice_start"], line.end - task["slice_start"]
                if start < step[0] - 0.5 - EPS or end > step[1] + 0.6 + EPS:
                    yield shot.key, f"{step[0]}-{step[1]}s quotes {key}, sung {start:.2f} to {end:.2f} s"


@rule("T4")
def silent_step_over_singing(book):
    for shot, task in tasks(book, ("vocal",)):
        own = _own_lines(book, shot)
        for start, end, part, _, _ in task.get("steps", []):
            if part != "rest":
                continue
            sung = sum(max(0.0, min(end, line.end - task["slice_start"]) - max(start, line.start - task["slice_start"]))
                       for line in own)
            if sung > 0.4 + EPS:
                yield shot.key, f"{start}-{end}s is written silent while she sings {sung:.2f} s in it"


@rule("I1")
def shared_opening_still(book):
    seen: dict[str, str] = {}
    for shot in book.shots:
        still = (book.tasks.get(shot.key) or {}).get("still") or shot.still_path
        if still in seen and (shot.extra or {}).get("picks_up_from") != seen[still]:
            yield shot.key, f"starts from {still}, the first frame of {seen[still]}"
        seen.setdefault(still, shot.key)


@rule("I2")
def input_missing(book):
    for shot, task in tasks(book):
        wanted = [task.get("still"), task.get("closing_still")]
        if shot.kind == "vocal":
            wanted.append(task.get("audio"))
        missing = [path for path in dict.fromkeys(wanted) if path and not book.exists(path)]
        if shot.kind == "vocal" and not task.get("audio"):
            missing.append("(no audio)")
        if missing:
            yield shot.key, f"missing: {', '.join(missing)}"
