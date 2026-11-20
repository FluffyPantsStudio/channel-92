"""`finish`: the graded cut (else the cut) becomes cuts/vNN-final.mp4: the logo, then the era look (an ffmpeg
pre-filter, then ntsc-rs on a clean temporary file, re-encoded once), then the optional intro in front. The masters
are never touched. Tested against a stand-in ntsc-rs-cli (tests/finish/ntsc_stub.py)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from atomic_flix.brand.era_intro import INTRO_SECONDS
from atomic_flix.brand.logo import logo_box
from atomic_flix.cli import main
from atomic_flix.cut.media import probe, read_frames
from atomic_flix.eras import look_for_year
from atomic_flix.finish import ntsc
from atomic_flix.looks import load_preset
from ntsc_stub import calls, preset_given, write_stub

FPS, WIDTH, HEIGHT, SECONDS = 24, 320, 240, 2


def _clip(path: Path, colour: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"color=c={colour}:s={WIDTH}x{HEIGHT}:r={FPS}:d={SECONDS}", "-f", "lavfi", "-i",
                    f"sine=frequency=440:sample_rate=48000:duration={SECONDS}", "-ac", "2", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


@pytest.fixture
def film(tmp_path, monkeypatch) -> Path:
    monkeypatch.delenv(ntsc.ENV, raising=False)
    monkeypatch.setenv("CHANNEL92_HOME", str(tmp_path / "kit-home"))      # no ntsc-rs this machine's setup installed
    folder = tmp_path / "films" / "finish-test"
    assert main(["new", str(folder), "--aspect", "4:3", "--by", "Test", "--words", "square", "--year", "1987"]) == 0
    data = json.loads((folder / "film.json").read_text(encoding="utf-8"))
    data.update({"final_size": [WIDTH, HEIGHT], "fps": FPS})
    (folder / "film.json").write_text(json.dumps(data), encoding="utf-8")
    _clip(folder / "cuts" / "v01.mp4", "0x3060a0")
    (folder / "cuts" / "v01.edit.json").write_text("{}", encoding="utf-8")
    return folder


@pytest.fixture
def stub(tmp_path) -> Path:
    return write_stub(tmp_path / "stub")


def _brand(folder: Path, **brand) -> None:
    data = json.loads((folder / "film.json").read_text(encoding="utf-8"))
    (folder / "film.json").write_text(json.dumps({**data, "brand": brand}), encoding="utf-8")


def _set_year(folder: Path, year) -> None:
    data = json.loads((folder / "film.json").read_text(encoding="utf-8"))
    setup = {k: v for k, v in data["setup"].items() if k != "year"}
    data["setup"] = {**setup, **({"year": year} if year else {})}
    (folder / "film.json").write_text(json.dumps(data), encoding="utf-8")


def _finish(film: Path, *extra) -> int:
    return main(["finish", str(film), "--speed", "ultrafast", *map(str, extra)])


def _box_change(frames_a: np.ndarray, frames_b: np.ndarray) -> tuple[float, float]:
    x, y, w, h = logo_box(WIDTH, HEIGHT)
    diff = np.abs(frames_a.astype(int) - frames_b.astype(int)).max(axis=3)
    inside = diff[:, y:y + h, x:x + w].mean()
    outside = np.delete(diff, np.s_[0:y + h + 16], axis=1).mean()
    return inside, outside


def test_finish_runs_ntsc_rs_with_the_years_preset_on_a_clean_temporary_file(film, stub, capsys):
    assert _finish(film, "--ntsc-rs", stub) == 0
    made = calls(stub.parent)
    assert len(made) == 1 and made[0]["input_was_there"]
    args = made[0]["args"]
    source, out = Path(args[args.index("-i") + 1]), Path(args[args.index("-o") + 1])
    preset = Path(args[args.index("-p") + 1])
    assert preset.parent == source.parent and not preset.exists()      # written to the work folder, gone with it
    assert preset_given(stub.parent) == look_for_year(1987) != load_preset("1980s")   # 1987: 70 % of the way on
    assert "-y" in args and args[args.index("-c") + 1] == "ffv1" and out.suffix == ".mkv"
    assert args[args.index("--scale") + 1] == "480"
    assert source.parent.parent == film / "cuts" and out.parent == source.parent    # beside the output, not in TEMP
    assert not source.exists() and not out.exists() and not source.parent.exists()   # temporary, cleaned away
    final = probe(film / "cuts" / "v01-final.mp4")
    assert (final.width, final.height, final.frames) == (WIDTH, HEIGHT, SECONDS * FPS)
    text = capsys.readouterr().out
    assert "1980s" in text and "v01-final.mp4" in text


def test_the_masters_stay_clean_and_the_graded_cut_is_the_source(film, stub):
    _clip(film / "cuts" / "v01-toned.mp4", "0xa04030")
    before = {name: (film / "cuts" / name).read_bytes() for name in ("v01.mp4", "v01-toned.mp4")}
    assert _finish(film, "--ntsc-rs", stub, "--no-logo") == 0
    assert {name: (film / "cuts" / name).read_bytes() for name in before} == before
    given = read_frames(next(stub.parent.glob("input-0.*")), count=1)[0].astype(int)
    assert given[..., 0].mean() > given[..., 2].mean() + 40          # red: the graded cut, not the blue cut


def test_the_order_is_logo_then_look_then_intro(film, stub, monkeypatch):
    monkeypatch.setenv("NTSC_STUB_NEGATE", "1")
    _brand(film, intro="era")
    assert _finish(film, "--ntsc-rs", stub, "--no-logo") == 0
    plain_input = read_frames(next(stub.parent.glob("input-0.*")))
    (stub.parent / "calls.jsonl").unlink()
    assert _finish(film, "--ntsc-rs", stub) == 0
    made = calls(stub.parent)
    assert len(made) == 1                                       # the intro never goes through ntsc-rs
    branded_input = read_frames(next(stub.parent.glob("input-0.*")))
    inside, outside = _box_change(branded_input, plain_input)
    assert inside > 20 and outside < 2                          # the logo was on before the look
    final = film / "cuts" / "v01-final.mp4"
    intro_frames = round(INTRO_SECONDS * FPS)
    assert probe(final).frames == intro_frames + SECONDS * FPS     # the intro is in front
    body = read_frames(final, start_frame=intro_frames + 10, count=1)[0].astype(int)
    negative = 255 - read_frames(film / "cuts" / "v01.mp4", start_frame=10, count=1)[0].astype(int)
    assert np.abs(body - negative)[HEIGHT // 2:].mean() < 12       # the film after the intro is ntsc-rs's output
    assert (film / "brand").is_dir() and any((film / "brand").glob("intro-1980s-*.mp4"))


def test_without_ntsc_rs_the_film_is_finished_without_the_look_and_says_where_to_get_it(film, monkeypatch,
                                                                                         capsys):
    monkeypatch.setattr(ntsc, "_which", lambda name: None)
    assert _finish(film) == 0
    text = capsys.readouterr().out
    line = next(line for line in text.splitlines() if "ntsc-rs" in line)
    assert "https://github.com/ntsc-rs/ntsc-rs/releases" in line and line.count(". ") == 0
    assert "--ntsc-rs" in line and ntsc.ENV in line
    final = probe(film / "cuts" / "v01-final.mp4")
    assert final.frames == SECONDS * FPS


def test_a_given_path_that_is_not_there_stops_finish(film, tmp_path, capsys):
    assert _finish(film, "--ntsc-rs", tmp_path / "nowhere" / "ntsc-rs-cli.exe") == 2
    assert "nowhere" in capsys.readouterr().err and not (film / "cuts" / "v01-final.mp4").exists()


def test_an_environment_path_that_is_not_there_stops_finish(film, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(ntsc.ENV, str(tmp_path / "gone" / "ntsc-rs-cli.exe"))
    assert _finish(film) == 2
    assert ntsc.ENV in capsys.readouterr().err and not (film / "cuts" / "v01-final.mp4").exists()


def test_an_ntsc_rs_inside_the_film_folder_is_refused(film, capsys):
    planted = write_stub(film / "tools")
    assert _finish(film, "--ntsc-rs", planted) == 2
    assert "film folder" in capsys.readouterr().err and calls(planted.parent) == []


def test_a_portrait_film_keeps_480_lines_on_its_short_side(film, stub):
    data = json.loads((film / "film.json").read_text(encoding="utf-8"))
    data.update({"final_size": [180, 320]})
    (film / "film.json").write_text(json.dumps(data), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x3060a0:s=180x320:r={FPS}:d=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(film / "cuts" / "v01.mp4")], check=True)
    assert _finish(film, "--ntsc-rs", stub, "--no-logo") == 0
    args = calls(stub.parent)[0]["args"]
    assert args[args.index("--scale") + 1] == str(round(480 * 320 / 180))      # 853 lines: 480 across
    final = probe(film / "cuts" / "v01-final.mp4")
    assert (final.width, final.height) == (180, 320)


def test_the_clean_temporary_file_is_gone_before_the_final_encode(film, stub, monkeypatch):
    from atomic_flix.finish import chain
    seen = []
    real = chain.encode_final

    def spy(picture, *args, **kwargs):
        seen.append(sorted(p.name for p in Path(picture).parent.iterdir()))
        return real(picture, *args, **kwargs)
    monkeypatch.setattr(chain, "encode_final", spy)
    assert _finish(film, "--ntsc-rs", stub) == 0
    assert seen == [["look.mkv"]]
    assert sorted(p.name for p in (film / "cuts").iterdir() if p.is_dir()) == []


def test_an_intro_outside_the_film_folder_is_refused(film, tmp_path, capsys):
    _clip(tmp_path / "outside.mp4", "0x101010")
    _brand(film, intro="../../outside.mp4")
    assert _finish(film, "--no-look") == 2
    assert "outside the film folder" in capsys.readouterr().err


def test_a_cuts_folder_that_leads_outside_is_refused_before_writing(film, tmp_path, capsys):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "v01.mp4").write_bytes((film / "cuts" / "v01.mp4").read_bytes())
    (elsewhere / "v01.edit.json").write_text("{}", encoding="utf-8")
    import shutil
    shutil.rmtree(film / "cuts")
    try:
        (film / "cuts").symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("this machine cannot make symbolic links")
    assert _finish(film, "--no-look") == 2
    assert "outside the film folder" in capsys.readouterr().err
    assert not (elsewhere / "v01-final.mp4").exists()


def test_every_ffmpeg_call_of_finish_whitelists_its_inputs(film, stub, monkeypatch):
    from ffmpeg_calls import assert_whitelisted, ffmpeg_calls
    _brand(film, intro="era")
    calls_seen = ffmpeg_calls(monkeypatch)
    assert _finish(film, "--ntsc-rs", stub) == 0
    assert_whitelisted(calls_seen)


def test_the_environment_names_ntsc_rs(film, stub, monkeypatch):
    monkeypatch.setenv(ntsc.ENV, str(stub))
    assert _finish(film) == 0
    assert len(calls(stub.parent)) == 1


def test_no_look_and_no_era_leave_ntsc_rs_alone(film, stub, capsys):
    assert _finish(film, "--ntsc-rs", stub, "--no-look") == 0
    assert "look left off" in capsys.readouterr().out
    _set_year(film, None)
    assert _finish(film, "--ntsc-rs", stub) == 0
    assert "no era" in capsys.readouterr().out
    assert calls(stub.parent) == []
    assert (film / "cuts" / "v01-final.mp4").is_file()


def test_the_era_override_brings_its_preset_and_pre_filter(film, stub):
    _clip(film / "cuts" / "v01.mp4", "0xd02020")
    assert _finish(film, "--ntsc-rs", stub, "--era", "1950s", "--no-logo") == 0
    assert preset_given(stub.parent) == load_preset("1950s")
    given = read_frames(next(stub.parent.glob("input-0.*")), count=1)[0].astype(int)
    assert np.abs(given[..., 0] - given[..., 2]).mean() < 3         # monochrome before ntsc-rs
    final = read_frames(film / "cuts" / "v01-final.mp4", count=1)[0].astype(int)
    assert np.abs(final[..., 0] - final[..., 2]).mean() < 3


def test_an_unknown_era_is_refused(film, capsys):
    assert _finish(film, "--era", "1940s") == 2
    assert "1940s" in capsys.readouterr().err


def test_a_year_between_eras_blends_the_look_and_keeps_its_decades_logo(film, stub, capsys):
    _clip(film / "cuts" / "v01.mp4", "0xd02020")
    assert _finish(film, "--ntsc-rs", stub, "--year", 1956) == 0
    assert preset_given(stub.parent) == look_for_year(1956)
    assert preset_given(stub.parent) not in (load_preset("1950s"), load_preset("1960s"))
    given = read_frames(next(stub.parent.glob("input-0.*")), count=1)[0].astype(int)
    red = np.abs(given[..., 0] - given[..., 2])[HEIGHT // 2:].mean()
    assert 0.45 * 176 < red < 0.75 * 176                              # about six tenths of the red is left
    text = capsys.readouterr().out
    assert "year 1956: the 1950s look, 60 percent of the way to the 1960s" in text
    assert "logo-1950s.png" in text and "--year 1956" in text
    assert json.loads((film / "film.json").read_text(encoding="utf-8"))["setup"]["year"] == 1987   # one run only


def test_an_anchor_year_gives_the_era_preset_exactly(film, stub):
    assert _finish(film, "--ntsc-rs", stub, "--year", 1970, "--no-logo") == 0
    assert preset_given(stub.parent) == load_preset("1970s")


def test_the_era_override_is_the_pure_look_whatever_the_year(film, stub, capsys):
    assert _finish(film, "--ntsc-rs", stub, "--era", "1990s", "--no-logo") == 0
    assert preset_given(stub.parent) == load_preset("1990s")
    assert "the 1990s look" in capsys.readouterr().out


@pytest.mark.parametrize("year", [1949, 2011, "soon"])
def test_a_year_off_the_air_is_refused_by_finish(film, capsys, year):
    assert _finish(film, "--year", year) == 2
    assert "1950 to 2010" in capsys.readouterr().err


def test_year_and_era_together_are_refused(film):
    with pytest.raises(SystemExit):
        _finish(film, "--year", 1960, "--era", "1950s")


def test_the_sample_uses_the_year_too(film, stub, tmp_path):
    still = tmp_path / "still.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360", "-frames:v", "1",
                    str(still)], check=True)
    assert _finish(film, "--ntsc-rs", stub, "--sample", still, "--year", 1983) == 0
    assert preset_given(stub.parent) == look_for_year(1983)


def test_the_logo_is_in_the_top_right_box_and_nowhere_else(film):
    assert _finish(film, "--no-look") == 0
    branded = read_frames(film / "cuts" / "v01-final.mp4")
    assert _finish(film, "--no-look", "--no-logo") == 0
    plain = read_frames(film / "cuts" / "v01-final.mp4")
    inside, outside = _box_change(branded, plain)
    assert inside > 20 and outside < 1
    _brand(film, logo=False)
    assert _finish(film, "--no-look") == 0
    assert np.array_equal(read_frames(film / "cuts" / "v01-final.mp4"), plain)


def test_the_era_logo_is_the_one_laid_on(film, capsys):
    assert _finish(film, "--no-look") == 0
    assert "logo-1980s.png" in capsys.readouterr().out
    _set_year(film, None)
    assert _finish(film, "--no-look") == 0
    assert "channel92-logo.png" in capsys.readouterr().out


def test_an_intro_file_is_joined_in_front(film):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=200x200:rate=24:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(film / "intro.mp4")], check=True)
    _brand(film, intro="intro.mp4")
    assert _finish(film, "--no-look") == 0
    assert probe(film / "cuts" / "v01-final.mp4").frames == 24 + SECONDS * FPS


def test_a_missing_intro_or_an_era_intro_without_an_era_is_refused(film, capsys):
    _brand(film, intro="nowhere.mp4")
    assert _finish(film) == 2
    assert "nowhere.mp4" in capsys.readouterr().err
    _brand(film, intro="era")
    _set_year(film, None)
    assert _finish(film) == 2
    assert "era" in capsys.readouterr().err


def test_the_sample_shows_the_look_and_logo_on_one_still(film, stub, tmp_path):
    still = tmp_path / "still.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360", "-frames:v", "1",
                    str(still)], check=True)
    assert _finish(film, "--ntsc-rs", stub, "--sample", still) == 0
    sample = film / "plan" / "look-sample.png"
    assert sample.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (probe(sample).width, probe(sample).height) == (WIDTH, HEIGHT)
    assert len(calls(stub.parent)) == 1
    assert not (film / "cuts" / "v01-final.mp4").exists()


def test_finish_needs_a_cut(tmp_path):
    folder = tmp_path / "empty"
    assert main(["new", str(folder)]) == 0
    assert main(["finish", str(folder)]) == 2


def test_progress_names_the_era(film, capsys):
    main(["progress", str(film)])
    text = capsys.readouterr().out
    assert "era 1980s" in text and "year 1987: the 1980s look, 70 percent of the way to the 1990s" in text
    _set_year(film, 1975)
    main(["progress", str(film)])
    assert "year 1975: halfway between the 1970s and the 1980s looks" in capsys.readouterr().out
    _set_year(film, 1970)
    main(["progress", str(film)])
    assert "year 1970: the 1970s look" in capsys.readouterr().out
    _set_year(film, None)
    main(["progress", str(film)])
    assert "no era" in capsys.readouterr().out


@pytest.mark.ntsc_rs
def test_the_real_ntsc_rs_lays_the_look_on(film):
    found = ntsc.find_ntsc_rs()
    if found is None:
        pytest.skip("no ntsc-rs-cli on this machine (CHANNEL92_NTSC_RS or the PATH)")
    assert _finish(film, "--ntsc-rs", found) == 0
    final = read_frames(film / "cuts" / "v01-final.mp4").astype(int)
    clean = read_frames(film / "cuts" / "v01.mp4").astype(int)
    assert final.shape == clean.shape and np.abs(final - clean).mean() > 1
