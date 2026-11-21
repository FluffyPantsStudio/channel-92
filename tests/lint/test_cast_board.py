"""The review board: every view of a character on one picture, like a studio reference board."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from atomic_flix.cast_board import CANVAS, BoardError, make_board
from sheet_samples import write_sheet


def test_a_complete_sheet_makes_one_board_the_size_of_a_reference_sheet(tmp_path):
    person = {"views": write_sheet(tmp_path, "Nova")}
    aim = make_board(tmp_path, "nova", person)
    assert aim == tmp_path / "refs" / "boards" / "nova-board.png"
    with Image.open(aim) as board:
        assert board.size == CANVAS
        assert len(np.unique(np.asarray(board.convert("L")))) > 3         # the frame, the cells and the figures


def test_expressions_get_a_row_of_their_own(tmp_path):
    person = {"views": write_sheet(tmp_path, "Nova")}
    plain = make_board(tmp_path, "plain", person)
    faces = [person["views"]["front"]] * 3
    with_faces = make_board(tmp_path, "faces", person, faces)
    with Image.open(plain) as a, Image.open(with_faces) as b:
        assert np.asarray(a).tobytes() != np.asarray(b).tobytes()


def test_a_missing_view_is_named_and_no_board_is_written(tmp_path):
    views = write_sheet(tmp_path, "Nova")
    (tmp_path / views["body_back"]).unlink()
    with pytest.raises(BoardError, match="no picture yet for body_back"):
        make_board(tmp_path, "nova", {"views": views})
    assert not (tmp_path / "refs" / "boards").exists()


def test_a_view_that_is_not_a_picture_is_named_not_a_traceback(tmp_path):
    views = write_sheet(tmp_path, "Nova")
    (tmp_path / views["profile"]).write_bytes(b"not a picture")
    with pytest.raises(BoardError, match="cannot be read as a picture"):
        make_board(tmp_path, "nova", {"views": views})
