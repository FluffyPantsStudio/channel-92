"""One synthetic film for the desk tests, built once and copied into each test's own folder."""

import shutil

import pytest

from deskfilm import make_film


@pytest.fixture(scope="session")
def desk_template(tmp_path_factory):
    base = tmp_path_factory.mktemp("desk-template")
    make_film(base)
    return base


@pytest.fixture
def desk_film(desk_template, tmp_path):
    for part in ("films", "inputs"):
        shutil.copytree(desk_template / part, tmp_path / part)
    return tmp_path / "films" / "moon-song"
