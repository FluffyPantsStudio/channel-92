"""The first film is found only through FLIX_FIRST_FILM (docs/first-film-replay.md); nothing private is hard-coded."""

import re
from pathlib import Path

import first_film_env

REPO = Path(__file__).resolve().parents[1]
DRIVE_PATH = re.compile(r"\b[A-Za-z]:[/\\][A-Za-z]")


def test_unset_means_no_first_film(monkeypatch):
    monkeypatch.delenv(first_film_env.ENV, raising=False)
    assert first_film_env.flix_root() is None
    assert first_film_env.film_folder() is None
    assert first_film_env.under_root("workflows") is None


def test_the_film_folder_sits_under_the_variable(monkeypatch, tmp_path):
    monkeypatch.setenv(first_film_env.ENV, str(tmp_path))
    assert first_film_env.film_folder() == tmp_path / "films" / first_film_env.FILM_SLUG
    assert first_film_env.under_root("baseline.json") == tmp_path / "baseline.json"


def test_make_fixtures_asks_for_the_film_when_the_variable_is_unset(monkeypatch, tmp_path, tool, capsys):
    monkeypatch.delenv(first_film_env.ENV, raising=False)
    fixtures = tool("make_fixtures")
    assert fixtures.first_film_src() is None
    assert fixtures.main(["first-film", "--out", str(tmp_path / "pack")]) == 1
    assert "FLIX_FIRST_FILM" in capsys.readouterr().err
    assert not (tmp_path / "pack").exists()


def test_no_drive_paths_in_tests_tools_or_docs():
    """A machine's own drive path never sits in the public tree (made-up program paths in tests excepted)."""
    allowed = {"tests/runner/test_runner_check.py", "tests/scenes/test_render.py", "tests/test_first_film_env.py",
               "docs/first-film-replay.md"}
    found = []
    for folder in ("tests", "tools", "docs"):
        for path in (REPO / folder).rglob("*"):
            relative = path.relative_to(REPO).as_posix()
            if (not path.is_file() or path.suffix not in (".py", ".md", ".txt", ".json") or relative in allowed
                    or relative.startswith("docs/private/") or "__pycache__" in path.parts):
                continue
            if DRIVE_PATH.search(path.read_text(encoding="utf-8", errors="replace")):
                found.append(relative)
    assert found == []
