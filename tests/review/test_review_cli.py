import json

from atomic_flix.cut.__main__ import main as cut_main
from atomic_flix.review.__main__ import main
from reviewclips import FPS, HEIGHT, WIDTH, busy_box, panning, save


def _edit_file(tmp_path):
    save(tmp_path / "pan.mp4", panning(3.0, 1.0))
    save(tmp_path / "sing.mp4", busy_box(3.0, (0.4, 0.55, 0.2, 0.15), busy=[(0.5, 2.5)]))
    edit = {"fps": FPS, "size": [WIDTH, HEIGHT], "start": 0.0, "end": 4.0,
            "cuts": [{"key": "N01", "at": 0.0}, {"key": "S02", "at": 2.0}],
            "sung": [[2.2, 4.0]],
            "takes": [{"key": "N01", "file": "pan.mp4", "map": [[0.0, 0.25]]},
                      {"key": "S02", "file": "sing.mp4", "map": [[2.0, 0.25]], "type": "vocal",
                       "mouth": [0.4, 0.55, 0.2, 0.15]}]}
    path = tmp_path / "edit.json"
    path.write_text(json.dumps(edit), encoding="utf-8")
    assert cut_main(["encode", str(path), str(tmp_path / "v01.mp4"), "--speed", "ultrafast"]) == 0
    return path


def test_sheets_and_frames_verbs(tmp_path, capsys):
    edit = _edit_file(tmp_path)
    assert main(["boards", str(edit), str(tmp_path / "v01.mp4"), str(tmp_path / "review")]) == 0
    assert (tmp_path / "review" / "MANIFEST.txt").is_file()
    assert main(["frames", str(edit), str(tmp_path / "v01.mp4"), "S02", str(tmp_path / "full"), "--at", "0.5"]) == 0
    assert (tmp_path / "full" / "S02-0.500.png").is_file()
    assert main(["frames", str(edit), str(tmp_path / "v01.mp4"), "S09", str(tmp_path / "full")]) == 1
    assert "no shot S09" in capsys.readouterr().err
