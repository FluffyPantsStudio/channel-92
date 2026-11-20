"""`packet FILM GATE`: phone-ready files for one gate, in the order they are sent, with a manifest and a short card."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atomic_flix.cli import main
from atomic_flix.cut.media import probe
from atomic_flix.desk import DeskError, build_packet, tile_boxes
from atomic_flix.desk.pictures import SCREEN_LONG_SIDE
from atomic_flix.wav import read_wav
from deskfilm import GATES, PITCHES, SONG_S, ask_up_to, picture

pytestmark = pytest.mark.usefixtures("no_eval_hook")


@pytest.fixture
def film(desk_film) -> Path:
    return desk_film


def _manifest(folder: Path) -> dict:
    return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))


def _tree(root: Path) -> dict[str, int]:
    return {path.relative_to(root).as_posix(): path.stat().st_mtime_ns for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("gate", GATES)
def test_every_gate_packet_is_in_order_within_the_cap_with_a_short_card(film, gate):
    ask_up_to(film, gate)
    packet = build_packet(film, gate, max_mb=40)
    folder = film / "desk" / gate
    assert packet.folder == folder
    manifest = _manifest(folder)
    assert manifest["gate"] == gate and manifest["format"] == "atomic-flix/packet@1"
    files = manifest["files"]
    assert [item["order"] for item in files] == list(range(1, len(files) + 1))
    for item in files:
        path = folder / item["file"]
        assert path.is_file(), item
        assert item["bytes"] == path.stat().st_size <= 40 * 1024 * 1024
        assert item["caption"].strip()
        assert path.resolve().is_relative_to(film.resolve())
    card = (folder / "card.md").read_text(encoding="utf-8")
    assert len(card.split()) < 100, card
    assert card.count("?") == 1
    assert "yes" in card and "question:" in card
    assert (gate == "spend") == (files == [])


def test_concept_packet_is_the_timeline_strip_and_the_concept_text(film):
    ask_up_to(film, "concept")
    files = _manifest(build_packet(film, "concept").folder)["files"]
    kinds = [item["kind"] for item in files]
    assert kinds == ["image", "text"]
    folder = film / "desk" / "concept"
    strip = probe(folder / files[0]["file"])
    assert strip.width <= SCREEN_LONG_SIDE
    assert (folder / files[1]["file"]).read_text(encoding="utf-8") == PITCHES
    assert "story gap" in files[0]["caption"]


def test_song_packet_is_the_mix_with_the_click_as_aac_and_says_where_the_one_is(film):
    ask_up_to(film, "song")
    files = _manifest(build_packet(film, "song").folder)["files"]
    assert [item["kind"] for item in files] == ["audio", "image"]
    audio = film / "desk" / "song" / files[0]["file"]
    assert audio.suffix == ".m4a"
    assert "0.75 s" in files[0]["caption"] and "slot 1" in files[0]["caption"]
    assert len(read_wav(film / "audio" / "mix.wav")[0]) / 44100 == pytest.approx(SONG_S)


def test_a_file_that_cannot_meet_the_cap_is_refused_by_name(film):
    ask_up_to(film, "song")
    with pytest.raises(DeskError, match="song-click.m4a"):
        build_packet(film, "song", max_mb=0.01)


def test_looks_packet_shows_each_still_at_screen_size_then_its_tiles_at_native_pixels(film):
    from atomic_flix.cut.media import write_image
    write_image(film / "plan" / "look-sample.png", picture(800, 450, 2))
    ask_up_to(film, "looks")
    files = _manifest(build_packet(film, "looks").folder)["files"]
    kinds = [item["kind"] for item in files]
    assert kinds == ["image"] * 2 + ["image"] * 12 + ["image"]
    folder = film / "desk" / "looks"
    first = probe(folder / files[0]["file"])
    assert max(first.width, first.height) == SCREEN_LONG_SIDE        # the 2000 px still came down to screen size
    tiles = [probe(folder / item["file"]) for item in files[2:8]]
    boxes = tile_boxes(2000, 1125)
    assert [(t.width, t.height) for t in tiles] == [(r - l, b - t) for l, t, r, b in boxes]
    assert "look sample" in files[-1]["caption"]


@pytest.mark.parametrize("size", [(2000, 1125), (1125, 2000), (641, 359), (6, 4)])
def test_tiles_cover_the_whole_picture_at_native_pixels(size):
    width, height = size
    boxes = tile_boxes(width, height)
    assert len(boxes) == 6
    covered = [[False] * width for _ in range(height)]
    for left, top, right, bottom in boxes:
        assert 0 <= left < right <= width and 0 <= top < bottom <= height
        for y in range(top, bottom):
            for x in range(left, right):
                covered[y][x] = True
    assert all(all(row) for row in covered)
    assert boxes == tile_boxes(width, height)                       # fixed, no detection


def test_board_packet_is_numbered_sheets_of_at_most_six_shots(film):
    ask_up_to(film, "board")
    files = _manifest(build_packet(film, "board").folder)["files"]
    assert len(files) == 2
    assert "shots 1 to 6" in files[0]["caption"] and "shots 7 to 8" in files[1]["caption"]


def test_spend_card_carries_the_batch_from_the_budget(film):
    ask_up_to(film, "spend")
    card = (build_packet(film, "spend").folder / "card.md").read_text(encoding="utf-8")
    assert "8 render prompts" in card and "4 renders" in card and "1280x704" in card and "1.00 GPU hours" in card


def test_v1_packet_is_the_final_for_a_phone_then_the_review_sheets(film):
    (film / "cuts" / "v01-final.mp4").write_bytes((film / "cuts" / "v01.mp4").read_bytes())
    ask_up_to(film, "v1")
    files = _manifest(build_packet(film, "v1").folder)["files"]
    assert [item["kind"] for item in files] == ["video", "image", "image"]
    assert "v01-final.mp4" in files[0]["caption"]
    clip = probe(film / "desk" / "v1" / files[0]["file"])
    assert min(clip.width, clip.height) <= 720
    assert files[1]["caption"].startswith("sheet 1 of 2")


def test_the_packet_refuses_a_gate_not_yet_asked_and_an_unknown_gate(film):
    with pytest.raises(DeskError, match="not been asked"):
        build_packet(film, "concept")
    with pytest.raises(DeskError, match="no gate called"):
        build_packet(film, "colour")


def test_the_packet_never_writes_or_reads_outside_the_film_folder(film, tmp_path):
    ask_up_to(film, "looks", ["stills/S01.png", "../../inputs/mix.wav"])
    outside = {k: v for k, v in _tree(tmp_path).items() if not k.startswith("films/")}
    with pytest.raises(DeskError, match="outside the film folder"):
        build_packet(film, "looks")
    with pytest.raises(DeskError, match="outside the film folder"):
        build_packet(film, "looks", out=tmp_path / "elsewhere")
    after = {k: v for k, v in _tree(tmp_path).items() if not k.startswith("films/")}
    assert after == outside


def test_the_packet_verb_writes_the_folder_and_prints_the_send_order(film, capsys):
    ask_up_to(film, "concept")
    assert main(["packet", str(film), "concept"]) == 0
    out = capsys.readouterr().out
    assert "desk/concept" in out.replace("\\", "/") and "1." in out
    assert main(["packet", str(film), "song"]) == 2


def test_packet_prints_what_it_is_built_from_so_a_stale_ask_shows(film, capsys):
    ask_up_to(film, "concept")
    assert main(["packet", str(film), "concept"]) == 0
    out = capsys.readouterr().out
    assert "pitches.md, plan/structure.md" in out
    assert "\"Is this the film?\"" in out


def test_a_packet_after_asking_again_is_built_from_the_new_ask(film, capsys):
    ask_up_to(film, "concept")
    (film / "plot.md").write_text("# The plot\n\nThe moon goes home.\n", encoding="utf-8")
    assert main(["gate", str(film), "ask", "concept", "--again", "--shown", "plot.md", "--shown",
                 "plan/structure.md", "--question", "Is this the plot?"]) == 0
    packet = build_packet(film, "concept")
    assert packet.shown == ("plot.md", "plan/structure.md") and packet.question == "Is this the plot?"
    assert "Is this the plot?" in packet.card
    texts = [item for item in packet.files if item.kind == "text"]
    assert (packet.folder / texts[0].file).read_text(encoding="utf-8").startswith("# The plot")
