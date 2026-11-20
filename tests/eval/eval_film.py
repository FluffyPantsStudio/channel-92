"""A synthetic film for the eval of the eval: three shots, every gate up to 5 passed, a batch shot, a cut audited,
graded and flash-checked, and one clean cold review round, so the film stands before gate 6 with nothing wrong.

Every name and line here is invented for the test. `inject` breaks exactly one rule, by the method it is checked with.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np

from atomic_flix.formats import stamped
from atomic_flix.gates import RELAYED, Answer, GateBook
from atomic_flix.plan.__main__ import main as plan_main
from atomic_flix.project import BatchApproval, SongPrint, Standing, create_project, save_standing
from atomic_flix.runner.jobs import DONE, JobStore
from atomic_flix.wav import save_wav

SHOTS = """\
N01 cutaway
  figures: no
  scene: dunes
  beat: sand drifts slowly through the light

S01 vocal: v01
  crop: 1.0
  scene: dunes
  place: a pale dune under a low sun
  gaze: at us
  act v01: she sways gently with the music

N02 cutaway
  figures: no
  beat: clouds drift slowly across the evening sky
"""

PASS_ALL = {"hands": "PASS", "mouth": "PASS", "identity": "PASS", "gaze": "PASS", "build": "PASS", "flat": "PASS"}
GATE_WORDS = {"concept": "the dune one", "song": "yes, that is the song and the one is right",
              "looks": "yes, that is her", "board": "render it", "spend": "yes, run this batch"}
DAY = "2026-11-18T"
JUDGED_AT = DAY + "11:00:00+00:00"
SENT_AT = datetime.fromisoformat(DAY + "12:00:00+00:00").timestamp()
REVIEWED_AT = DAY + "16:00:00+00:00"
SIZE = [1280, 704]
LAMP = "refs/lamp.png"


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data, indent=1)
    path.write_text(text, encoding="utf-8", newline="\n")


def _audio(root: Path) -> str:
    rate = 48000
    t = np.arange(int(22 * rate)) / rate
    voice = np.where((t >= 10.4) & (t < 13.6), 0.2 * np.sin(2 * np.pi * 220 * t), 0.0)
    save_wav(root / "audio" / "voice.wav", voice, rate)
    save_wav(root / "audio" / "mix.wav", voice * 0.5, rate)
    return hashlib.sha256((root / "audio" / "mix.wav").read_bytes()).hexdigest()


def _film_json(root: Path) -> None:
    film = {"name": "Dune Test", "star": {"name": "Mira", "who": "a singer with short silver hair"},
            "wardrobe": {"main": "wearing a white jacket over a black top"}, "tone": "serious and soulful",
            "stems": {"mix": "audio/mix.wav", "voice": "audio/voice.wav"}, "lineup_rows": "shots.txt",
            "downbeat_slot": 0, "ends_at": 22.0, "look": "photo", "frame": SIZE, "never": ["umbrella"],
            "props": {"lamp": {"ref": LAMP, "words": ["lantern"]}},
            "characters": {"Mira": {"identity": "refs/front.png", "hero": "refs/front.png", "body": "refs/body.png"}},
            "batch": {"takes": 1, "cards": 1},
            "setup": {"aspect": "16:9", "tier": "standard", "aspect_by": "Test Person"}}
    _write(root / "film.json", stamped("film", film))


def _analysis(root: Path) -> None:
    _write(root / "analysis" / "voice-lines.json", {"sung_db": -14.0, "lines": [
        {"id": "v01", "part": "lead", "text": "Slow light on the water.", "start": 10.4, "end": 13.6, "gaps": [],
         "provenance": "level", "flags": []}]})
    beats = [round(k * 0.5, 3) for k in range(45)]
    _write(root / "analysis" / "pulse.json", {"bpm": 120, "beats": beats, "downbeat_slot": 0,
                                              "grounds": {"clearance": 0.8, "spans_backing": "9/10"}})


def _stills(root: Path) -> None:
    for key in ("N01", "S01", "N02"):
        (root / "stills" / f"{key}.png").write_bytes(b"png placeholder")
        record = {"size": SIZE, "refs": [LAMP],
                  "judge": {"verdict": "PASS", "full_size": True, "items": PASS_ALL, "at": JUDGED_AT}}
        if key == "S01":
            record.update({"figures": ["Mira"], "refs": ["refs/front.png", "refs/body.png", LAMP, "stills/N01.png"]})
        _write(root / "stills" / f"{key}.json", record)


def _gates(song: SongPrint) -> Standing:
    book = GateBook.empty()
    for minute, (gate, words) in enumerate(GATE_WORDS.items()):
        asked = f"{DAY}10:{minute * 2:02d}:00+00:00"
        answered = f"{DAY}10:{minute * 2 + 1:02d}:00+00:00"
        book = book.ask(gate, [f"shown for {gate}"], at=asked)
        book = book.answer(gate, Answer(words=words, by="Test Person", provenance=RELAYED, at=answered))
    book = book.reviewed("cuts/v01-toned.mp4", "cold-reader-1", [], at=REVIEWED_AT)
    spend_at = book.record("spend").latest.at
    return Standing(film="Dune Test", created=DAY + "09:00:00+00:00", gates=book, song=song,
                    batch=BatchApproval(takes=3, size=tuple(SIZE), busy_s=100000.0, at=spend_at, drawn=3))


def _jobs(root: Path, spend_at: str) -> None:
    store = JobStore(root)
    for number, key in enumerate(("N01", "S01", "N02")):
        vocal = key.startswith("S")
        fields = {"film": "dune-test", "graph": "graphs/sung.json" if vocal else "graphs/plate.json",
                  "wording": (root / "plan" / f"{key}.prompt.txt").read_text(encoding="utf-8").strip(),
                  "inputs": {"opening_still": f"stills/{key}.png"}, "vocal": vocal,
                  "kind": "vocal" if vocal else "cutaway", "approval": spend_at, "seconds": 5}
        job = store.create(key, fields)
        store.update(job, state=DONE, submitted_at=SENT_AT + number, busy_s=60.0, host="127.0.0.1:8188")


def _cut(root: Path) -> None:
    _write(root / "cuts" / "v01.audit.json", stamped("audit", {
        "cuts": [], "errors": [], "warnings": [],
        "audio": {"target_lufs": -14.0, "lufs_after": -14.1, "peak_after_db": -1.6}}))
    _write(root / "cuts" / "v01-toned.tone.json", stamped("tone", {
        "grain": None, "spread_before": {"black": 0.02, "white": 0.03, "colour": 0.05},
        "spread_after": {"black": 0.01, "white": 0.015, "colour": 0.02}, "shots": []}))
    _write(root / "cuts" / "v01-toned-strobe.json", stamped("strobe", {
        "passed": True, "flash_count": 0, "worst_count": 0, "worst_at": None, "flashes": [], "failing": []}))
    for name in ("v01.mp4", "v01-toned.mp4"):
        (root / "cuts" / name).write_bytes(b"synthetic cut " + name.encode())


def build_film(parent: Path) -> Path:
    """The clean film, standing before gate 6."""
    folder = create_project(parent, "dune-test", "Dune Test", created=DAY + "09:00:00+00:00")
    root = folder.root
    sha = _audio(root)
    _film_json(root)
    _write(root / "shots.txt", SHOTS)
    _analysis(root)
    _stills(root)
    assert plan_main([str(root)]) == 0
    standing = _gates(SongPrint(file="audio/mix.wav", sha256=sha, size=(root / "audio" / "mix.wav").stat().st_size))
    save_standing(folder, standing)
    _jobs(root, standing.batch.at)
    _cut(root)
    return root


# One violation per method --------------------------------------------------------------------------------------

def _edit_json(path: Path, change) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    _write(path, data)


def _job(root: Path, key: str) -> Path:
    return root / "renders" / key / "r001.job.json"


def lint_hands(root: Path) -> None:
    """auto (lint): the planned prompt of the sung shot names her hands."""
    prompt = root / "plan" / "S01.prompt.txt"
    _write(prompt, prompt.read_text(encoding="utf-8").rstrip() + " Her hands stay down at her sides.\n")


def ledger_reviewer_twice(root: Path) -> None:
    """ledger: a second review round by the reviewer of the first."""
    def change(data):
        rounds = data["gates"]["review"]["rounds"]
        rounds.append({**rounds[0], "at": DAY + "17:00:00+00:00"})
    _edit_json(root / "standing.json", change)


def ledger_unapproved_job(root: Path) -> None:
    """ledger: a render planned under no gate-5 yes."""
    _edit_json(_job(root, "N02"), lambda data: data.update(approval="2026-01-01T00:00:00+00:00"))


def scene_master_unused(root: Path) -> None:
    """scene: the sung shot's still was not made from the scene's master."""
    _edit_json(root / "stills" / "S01.json", lambda data: data["refs"].remove("stills/N01.png"))


def scene_other_prop(root: Path) -> None:
    """scene: the sung shot uses another reference for the lamp."""
    _edit_json(root / "stills" / "S01.json", lambda data: data.update(props={"lamp": "refs/lamp-two.png"}))


def scene_other_aspect(root: Path) -> None:
    """scene: the sung shot's still is square while the scene's master is wide."""
    _edit_json(root / "stills" / "S01.json", lambda data: data.update(size=[1024, 1024]))


def scene_other_look(root: Path) -> None:
    """scene (a warning): the two shots of the scene state different looks."""
    _edit_json(root / "stills" / "N01.json", lambda data: data.update(look="cold night"))
    _edit_json(root / "stills" / "S01.json", lambda data: data.update(look="warm dusk"))


def sent_grain(root: Path) -> None:
    """sent prompt: the wording actually sent for N02 asked for film grain (the plan's prompt is clean)."""
    _edit_json(_job(root, "N02"), lambda data: data.update(wording=data["wording"] + " Fine film grain."))


def sent_never(root: Path) -> None:
    """sent prompt: the wording sent for N01 names an object on the film's never list."""
    _edit_json(_job(root, "N01"), lambda data: data.update(wording=data["wording"] + " An umbrella leans nearby."))


def cut_flash(root: Path) -> None:
    """cut: the graded film failed the flash check."""
    _edit_json(root / "cuts" / "v01-toned-strobe.json",
               lambda data: data.update(passed=False, failing=[[3.0, 4.5]], worst_count=5))


def cut_ungraded(root: Path) -> None:
    """cut: the newest cut was never graded."""
    (root / "cuts" / "v01-toned.tone.json").unlink()


def _edit_gate(root: Path, gate: str, change) -> None:
    def edit(data):
        change(next(record for record in data["gates"]["gates"] if record["gate"] == gate), data)
    _edit_json(root / "standing.json", edit)


def ledger_judged_late(root: Path) -> None:
    """ledger: the sung shot's first frame was judged after its render was sent."""
    _edit_json(root / "stills" / "S01.json", lambda data: data["judge"].update(at=DAY + "13:00:00+00:00"))


def ledger_sent_without_time(root: Path) -> None:
    """ledger: a sent render carries no time, so the judge's look cannot be shown to come first."""
    _edit_json(_job(root, "N01"), lambda data: data.update(submitted_at=None))


def ledger_out_of_order(root: Path) -> None:
    """ledger: gate 3 was asked before gate 2 had its yes."""
    _edit_gate(root, "looks", lambda record, data: record.update(asked_at=DAY + "10:02:30+00:00"))


def ledger_machine_answer(root: Path) -> None:
    """ledger: gate 1's answer is signed by a model."""
    _edit_gate(root, "concept", lambda record, data: record["answers"][0].update(by="assistant"))


def ledger_unsaid_arrival(root: Path) -> None:
    """ledger (a warning): gate 4's answer does not say how it arrived."""
    _edit_gate(root, "board", lambda record, data: record["answers"][0].update(provenance="person"))


def ledger_reused_answer(root: Path) -> None:
    """ledger: gate 4 holds gate 3's answer, the same words at the same moment."""
    def change(record, data):
        looks = next(r for r in data["gates"]["gates"] if r["gate"] == "looks")["answers"][0]
        record["answers"][0].update(words=looks["words"], at=looks["at"])
    _edit_gate(root, "board", change)


def ledger_rounds_open(root: Path) -> None:
    """ledger: the latest cold review round still names an error."""
    def change(data):
        rounds = data["gates"]["review"]["rounds"]
        rounds.append({**rounds[0], "reviewer": "cold-reader-2", "errors": ["S01 jumps at the cut"],
                       "at": DAY + "17:00:00+00:00"})
    _edit_json(root / "standing.json", change)


def ledger_job_without_approval(root: Path) -> None:
    """ledger: a render carries no gate-5 approval at all."""
    _edit_json(_job(root, "S01"), lambda data: data.pop("approval"))


def cut_audit_error(root: Path) -> None:
    """cut: the newest cut's audit names an error."""
    _edit_json(root / "cuts" / "v01.audit.json", lambda data: data.update(errors=["S01 plays slower than 1x"]))


def cut_audit_warning(root: Path) -> None:
    """cut (a warning): the newest cut's audit names a cut off the bar's one and three."""
    _edit_json(root / "cuts" / "v01.audit.json",
               lambda data: data.update(warnings=["cut to S01 at 10.000 s lands on count 2"]))


def cut_too_quiet(root: Path) -> None:
    """cut (a warning): the song was laid back too quiet."""
    _edit_json(root / "cuts" / "v01.audit.json", lambda data: data["audio"].update(lufs_after=-18.5))


def cut_spread_widened(root: Path) -> None:
    """cut (a warning): the grade widened the spread of black across shots."""
    _edit_json(root / "cuts" / "v01-toned.tone.json", lambda data: data["spread_after"].update(black=0.05))


def cut_grain(root: Path) -> None:
    """cut: grain was graded into the master."""
    _edit_json(root / "cuts" / "v01-toned.tone.json", lambda data: data.update(grain={"amount": 0.2}))


def sent_outside_input(root: Path) -> None:
    """sent prompt: a render uploaded a still from outside the film folder."""
    _edit_json(_job(root, "N02"), lambda data: data["inputs"].update(opening_still="../elsewhere/N02.png"))


def sent_equipment(root: Path) -> None:
    """sent prompt: the wording sent for S01 names a tripod."""
    _edit_json(_job(root, "S01"), lambda data: data.update(wording=data["wording"] + " A tripod stands nearby."))


INJECTIONS = {
    "ledger-judge": (ledger_judged_late, "LG-JUDGE", "shot:S01"),
    "ledger-judge-no-time": (ledger_sent_without_time, "LG-JUDGE", "shot:N01"),
    "ledger-order": (ledger_out_of_order, "LG-ORDER", "film"),
    "ledger-person": (ledger_machine_answer, "LG-PERSON", "film"),
    "ledger-arrival": (ledger_unsaid_arrival, "LG-ARRIVAL", "film"),
    "ledger-reuse": (ledger_reused_answer, "LG-REUSE", "film"),
    "ledger-no-approval": (ledger_job_without_approval, "LG-BATCH", "film"),
    "ledger-rounds": (ledger_rounds_open, "LG-ROUNDS", "film"),
    "cut-audit": (cut_audit_error, "CT-AUDIT", "film"),
    "cut-loud": (cut_too_quiet, "CT-LOUD", "film"),
    "cut-audit-warning": (cut_audit_warning, "CT-AUDIT-W", "film"),
    "cut-spread": (cut_spread_widened, "CT-SPREAD", "film"),
    "cut-grain": (cut_grain, "CT-GRAIN", "film"),
    "sent-paths": (sent_outside_input, "SP-PATHS", "shot:N02"),
    "sent-equipment": (sent_equipment, "SP-EQUIP", "shot:S01"),
    "scene-look": (scene_other_look, "SC-LOOK", "scene:dunes"),
    "auto": (lint_hands, "H1", "shot:S01"),
    "ledger": (ledger_reviewer_twice, "LG-FRESH", "film"),
    "ledger-batch": (ledger_unapproved_job, "LG-BATCH", "film"),
    "scene": (scene_master_unused, "SC-MASTER", "scene:dunes"),
    "scene-prop": (scene_other_prop, "SC-PROPS", "scene:dunes"),
    "scene-aspect": (scene_other_aspect, "SC-ASPECT", "scene:dunes"),
    "sent-prompt": (sent_grain, "SP-GRAIN", "shot:N02"),
    "sent-never": (sent_never, "SP-NEVER", "shot:N01"),
    "cut": (cut_flash, "CT-FLASH", "film"),
    "cut-ungraded": (cut_ungraded, "CT-GRADE", "film"),
}
