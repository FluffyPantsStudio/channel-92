import json
import subprocess

import numpy as np

from atomic_flix.cut.__main__ import main
from atomic_flix.cut.audit import audit_edit
from atomic_flix.cut.edit import Cut, Edit, Placed
from atomic_flix.cut.media import probe, write_video
from cutclips import FPS, HEIGHT, WIDTH, flashing_frames, make_take, make_tone


def _colour_bars(path, pattern: str, seconds: float = 3.0):
    """A generated colour-bar clip from ffmpeg's own test sources."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"{pattern}=size={WIDTH}x{HEIGHT}:rate={FPS}:duration={seconds}",
                    "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_render_from_an_edit_file_of_colour_bar_takes(tmp_path):
    _colour_bars(tmp_path / "bars.mp4", "smptebars")
    _colour_bars(tmp_path / "moving.mp4", "testsrc2")
    make_tone(tmp_path / "song.wav", seconds=6.0)
    (tmp_path / "pulse.json").write_text(json.dumps({"beats": [0.5 * i for i in range(12)], "downbeat_slot": 0}),
                                         encoding="utf-8")
    edit = {"fps": FPS, "size": [WIDTH, HEIGHT], "song": "song.wav", "start": 0.0, "end": 4.0,
            "pulse": "pulse.json", "cuts": [{"key": "A", "at": 0.0, "grid": "one"}, {"key": "B", "at": 2.0, "grid": "one"}],
            "takes": [{"key": "A", "file": "bars.mp4", "map": [[0.0, 0.25]]},
                      {"key": "B", "file": "moving.mp4", "map": [[2.0, 0.25], [4.0, 2.75]]}]}
    (tmp_path / "edit.json").write_text(json.dumps(edit), encoding="utf-8")
    out = tmp_path / "cut" / "v01.mp4"
    assert main(["encode", str(tmp_path / "edit.json"), str(out), "--speed", "ultrafast"]) == 0
    assert probe(out).frames == 96
    audit = json.loads(out.with_suffix(".audit.json").read_text(encoding="utf-8"))
    assert [row["count"] for row in audit["cuts"]] == [1, 1]
    assert audit["cuts"][1]["fastest_rate"] == 1.25
    assert audit["audio"]["trim_db"] > 0


def test_audit_verb_exits_1_on_errors(tmp_path, capsys):
    make_take(tmp_path / "a.mp4")
    edit = {"fps": FPS, "size": [WIDTH, HEIGHT], "start": 0.0, "end": 2.0, "cuts": [{"key": "A", "at": 0.0}],
            "takes": [{"key": "A", "file": "a.mp4", "map": [[0.0, 0.5], [2.0, 1.5]]}]}
    (tmp_path / "edit.json").write_text(json.dumps(edit), encoding="utf-8")
    assert main(["audit", str(tmp_path / "edit.json"), "--json", str(tmp_path / "audit.json")]) == 1
    assert "slower" in capsys.readouterr().out


def test_flash_verb_exit_codes(tmp_path):
    fast = write_video(tmp_path / "fast.mp4", flashing_frames(2.0, 10.0), 24, crf=10)
    slow = write_video(tmp_path / "slow.mp4", flashing_frames(2.0, 4.0), 24, crf=10)
    assert main(["flash", str(fast), "--json", str(tmp_path / "f.json")]) == 1
    assert json.loads((tmp_path / "f.json").read_text(encoding="utf-8"))["failing"]
    assert main(["flash", str(slow)]) == 0


def test_look_alike_neighbours_are_warned(tmp_path):
    field = np.zeros((96, HEIGHT, WIDTH, 3), np.uint8)
    field[:, :, : WIDTH // 2] = 90
    field[:, :, WIDTH // 2:] = 160
    a = write_video(tmp_path / "a.mp4", field, FPS, crf=10)
    b = write_video(tmp_path / "b.mp4", field + 3, FPS, crf=10)
    edit = Edit(fps=FPS, size=(WIDTH, HEIGHT), song=None, start=0.0, end=4.0, cuts=(Cut("A", 0.0), Cut("B", 2.0)),
                takes={"A": Placed("A", a, ((0.0, 0.5),)), "B": Placed("B", b, ((2.0, 0.5),))})
    account = audit_edit(edit, compare_frames=True)
    assert any("look alike" in w for w in account.warnings)
    assert account.rows[1]["difference_from_previous"] < 0.05
