"""The kit is Channel 92: two commands for one main, and never another company's channel name anywhere."""

import sys
from pathlib import Path

import pytest

from atomic_flix.cli import main, overview

REPO = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "out", "fixtures", "__pycache__", "dist", "build", ".pytest_cache"}
NEVER = ("AM" + "TV", "Music " + "Television")      # written in two parts so this file does not hold them


def _config() -> dict:
    if sys.version_info < (3, 11):
        pytest.skip("tomllib needs Python 3.11")
    import tomllib

    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


def test_both_commands_run_the_same_main():
    scripts = _config()["project"]["scripts"]
    assert scripts == {"channel92": "atomic_flix.cli:main", "atomic-flix": "atomic_flix.cli:main"}


def test_the_project_says_what_the_kit_is_and_where_it_lives():
    project = _config()["project"]
    assert project["description"] == "Channel 92: a free kit for cinematic music films."
    assert all("FluffyPantsStudio/channel-92" in url for url in project["urls"].values())


def test_the_overview_names_the_kit(capsys):
    assert main(["--help"]) == 0
    text = capsys.readouterr().out
    assert text == overview() + "\n"
    assert "Channel 92" in text and "channel92" in text and "atomic-flix" in text


def test_no_file_names_another_companys_channel():
    found = []
    for path in REPO.rglob("*"):
        if not path.is_file() or SKIP_DIRS & set(path.relative_to(REPO).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8").lower()
        except (UnicodeDecodeError, OSError):
            continue
        found += [f"{path.relative_to(REPO)}: {word}" for word in NEVER if word.lower() in text]
    assert found == []
