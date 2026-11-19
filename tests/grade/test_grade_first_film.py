"""Regression on two shots of the first film (run with `pytest -m first_film`): N06, a dim shot of the tub, and S06,
a bright sung close-up, cut straight after it in v24. Read-only: the excerpt is decoded into the test's own folder."""

import subprocess

import pytest

from atomic_flix.cut.media import probe
from atomic_flix.grade import ShotSpan, grade_cut
from atomic_flix.grade.correct import COLOUR_GAIN, MAX_LEVEL_MOVE
from first_film_env import UNSET, film_folder

FILM = film_folder()
V24 = FILM / "v24-cut.mp4" if FILM is not None else None
N06 = (52.11, 55.36)      # book.json `show` of N06; S06 follows to 62.91
S06_END = 62.91

pytestmark = pytest.mark.first_film


@pytest.fixture(scope="module")
def excerpt(tmp_path_factory):
    if V24 is None:
        pytest.skip(UNSET)
    if not V24.is_file():
        pytest.skip("the first film's v24 cut is not on this machine")
    out = tmp_path_factory.mktemp("grade") / "n06-s06.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{N06[0]}", "-i", str(V24), "-t", f"{S06_END - N06[0]:.2f}",
                    "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "10", str(out)], check=True)
    return out


def test_two_first_film_shots_come_closer_without_a_big_move(excerpt, tmp_path):
    info = probe(excerpt)
    split = int(round((N06[1] - N06[0]) * info.fps))
    shots = [ShotSpan("N06", 0, split), ShotSpan("S06", split, info.frames)]
    result = grade_cut(excerpt, tmp_path / "toned.mp4", shots, info.fps, x264_speed="ultrafast")
    before, after = result.spread_before, result.spread_after
    assert before["white"] > 0.1                               # the two shots really differ: N06 is dim
    assert after["white"] < 0.6 * before["white"]
    assert after["black"] <= before["black"]
    for correction in result.corrections:
        assert abs(correction.new_black - correction.black) <= MAX_LEVEL_MOVE + 1e-9
        assert abs(correction.new_white - correction.white) <= MAX_LEVEL_MOVE + 1e-9
        assert COLOUR_GAIN[0] <= correction.gain <= COLOUR_GAIN[1]
    n06_after = next(item for item in result.after if item.key == "N06")
    assert n06_after.white < 0.85                               # a dim shot stays dimmer than the close-up
