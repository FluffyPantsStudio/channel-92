import json

import pytest

from atomic_flix.cut.edit import EditError, edit_from_project
from cutclips import make_take


def _film_folder(tmp_path, with_fit=True):
    film = {"name": "Test", "fps": 24, "frame": [192, 108], "final_size": [192, 108],
            "stems": {"mix": "audio/mix.wav", "voice": "audio/voice.wav"}, "downbeat_slot": 2,
            "lineup": [{"key": "S02", "type": "vocal", "setup": "moon", "mouth": [0.4, 0.3, 0.2, 0.1]},
                         {"key": "N08", "type": "cutaway"}],
            "picks": {"S02": 16, "N08": 3}, "shift": {"S02": 0.03}, "crops": {}}
    (tmp_path / "film.json").write_text(json.dumps(film), encoding="utf-8")
    (tmp_path / "plan").mkdir()
    (tmp_path / "plan" / "cuts.json").write_text(json.dumps({"cuts": [{"key": "S02", "at": 10.0, "grid": "one"},
                                                                      {"key": "N08", "at": 12.0, "grid": "three"}]}),
                                                 encoding="utf-8")
    (tmp_path / "analysis").mkdir()
    (tmp_path / "analysis" / "pulse.json").write_text(json.dumps({"beats": [0.5 * i for i in range(60)],
                                                                  "downbeat_slot": 0}), encoding="utf-8")
    for key, number, start in (("S02", 16, 0.4), ("N08", 3, 0.3)):
        folder = tmp_path / "renders" / key
        folder.mkdir(parents=True)
        make_take(folder / f"r{number:03d}.mp4", count=72)
        if with_fit:
            fit = {"how": "sound", "map": [[10.0 if key == "S02" else 12.0, start]]}
            (folder / f"r{number:03d}.fit.json").write_text(json.dumps(fit), encoding="utf-8")
    return tmp_path


def test_edit_from_project_reads_picks_maps_and_pulse(tmp_path):
    edit = edit_from_project(_film_folder(tmp_path))
    assert edit.start == 10.0
    assert edit.end == pytest.approx(12.0 + 3.0 - 0.3)
    s02 = edit.takes["S02"]
    assert s02.file == tmp_path / "renders" / "S02" / "r016.mp4"
    assert s02.take_time(10.0) == pytest.approx(0.43)
    assert s02.setup == "moon" and s02.kind == "vocal" and s02.mouth == (0.4, 0.3, 0.2, 0.1)
    assert edit.pulse["downbeat_slot"] == 2
    assert edit.song == tmp_path / "audio" / "mix.wav"


def test_edit_from_project_needs_each_picks_placement(tmp_path):
    with pytest.raises(EditError, match="no placement"):
        edit_from_project(_film_folder(tmp_path, with_fit=False))
