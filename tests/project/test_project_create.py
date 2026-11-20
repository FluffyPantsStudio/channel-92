"""A new film folder from the template, and its state file."""

import json

import pytest

from atomic_flix.project import (
    FOLDERS,
    FilmFolder,
    ProjectError,
    create_project,
    load_standing,
    where_it_stands,
)

CREATED = "2026-11-20T09:00:00+00:00"


def test_creates_every_folder_and_starter_file(tmp_path):
    film = create_project(tmp_path, "glass-harbour", "Glass Harbour", created=CREATED)
    assert isinstance(film, FilmFolder)
    assert film.root == tmp_path / "glass-harbour"
    for name, _purpose in FOLDERS:
        assert (film.root / name).is_dir(), name
    for path in (film.film, film.lyric, film.notes, film.standing, film.job_log):
        assert path.is_file(), path
    assert film.job_log.read_text(encoding="utf-8") == ""


def test_film_file_is_utf8_json_in_the_spec_shape(tmp_path):
    film = create_project(tmp_path, "la-tarara", "La Tarara, cascabeles", created=CREATED)
    data = json.loads(film.film.read_text(encoding="utf-8"))
    assert data["name"] == "La Tarara, cascabeles"
    assert data["stems"]["mix"] == "audio/mix.wav"
    assert data["lyric"] == "lyric.txt"
    assert data["lineup"] == [] and data["picks"] == {}
    assert data["downbeat_slot"] is None


def test_notes_open_with_the_film_name(tmp_path):
    film = create_project(tmp_path, "glass-harbour", "Glass Harbour", created=CREATED)
    text = film.notes.read_text(encoding="utf-8")
    assert text.startswith("# Glass Harbour")
    assert "word for word" in text


def test_state_file_says_the_concept_gate_is_next(tmp_path):
    film = create_project(tmp_path, "glass-harbour", "Glass Harbour", created=CREATED)
    standing = load_standing(film)
    assert standing.film == "Glass Harbour"
    assert standing.created == CREATED
    assert standing.gates.next_gate().id == "concept"
    assert standing.song is None
    summary = where_it_stands(film)
    assert "gate 1 of 6" in summary
    assert "concept" in summary
    assert "Is this the film?" in summary


@pytest.mark.parametrize("slug", ["Glass Harbour", "glass_harbour", "-x", "x-", "", "a/b", ".."])
def test_bad_slugs_are_refused(tmp_path, slug):
    with pytest.raises(ProjectError):
        create_project(tmp_path, slug, "A Film", created=CREATED)


def test_an_existing_folder_with_files_is_never_overwritten(tmp_path):
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "keep.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(ProjectError, match="not empty"):
        create_project(tmp_path, "taken", "Taken", created=CREATED)
    assert (tmp_path / "taken" / "keep.txt").read_text(encoding="utf-8") == "mine"


def test_an_empty_existing_folder_is_used(tmp_path):
    (tmp_path / "empty").mkdir()
    film = create_project(tmp_path, "empty", "Empty", created=CREATED)
    assert film.standing.is_file()


def test_film_folder_paths(tmp_path):
    film = FilmFolder(tmp_path)
    assert film.take_file("S02", 7) == tmp_path / "renders" / "S02" / "r007.mp4"
    assert film.still("S02") == tmp_path / "stills" / "S02.png"
    assert film.cut(1) == tmp_path / "cuts" / "v01.mp4"
