"""Gated voice, its soft copy, the shot-list text format and the GPU-hours estimate."""

import json

import numpy as np
import pytest

from atomic_flix.plan import Line, Pulse, ShotSpec, parse_shot_list, plan_film, write_plan
from atomic_flix.plan.estimate import estimate_batch, load_rates
from atomic_flix.plan.voice import gated_voice, soft_copy
from atomic_flix.wav import read_wav, save_wav


def rms_db(samples):
    return 20 * np.log10(np.sqrt(np.mean(np.square(samples))) + 1e-12)


def tone(seconds, rate, env_db, freq=220.0):
    t = np.arange(int(seconds * rate)) / rate
    return np.sin(2 * np.pi * freq * t) * (10 ** (env_db / 20) * np.sqrt(2))


def test_gated_voice_is_exactly_the_slice_and_silent_outside_the_gate(tmp_path):
    rate = 44100
    voice = tone(10.0, rate, -20.0)
    out = gated_voice(voice, rate, slice_start=1.0, seconds=6, gate=(2.0, 4.06))
    assert out.shape == (6 * 48000, 2)
    before = out[: int(0.95 * 48000)]
    after = out[int(3.07 * 48000):]
    assert np.max(np.abs(before)) == 0.0
    assert np.max(np.abs(after)) == 0.0
    assert rms_db(out[int(1.3 * 48000): int(2.7 * 48000), 0]) == pytest.approx(-20.0, abs=0.5)
    path = save_wav(tmp_path / "S01.voice.wav", out, 48000)
    back, back_rate = read_wav(path)
    assert back_rate == 48000 and back.shape == (6 * 48000, 2)


def test_soft_copy_is_eight_db_under_a_quiet_voice():
    rate = 48000
    voice = np.stack([tone(3.0, rate, -40.0)] * 2, axis=1)
    soft = soft_copy(voice, rate)
    assert rms_db(voice) - rms_db(soft) == pytest.approx(8.0, abs=2.0)


def test_soft_copy_squeezes_a_loud_vowel():
    rate = 48000
    voice = np.stack([tone(3.0, rate, -10.0)] * 2, axis=1)
    soft = soft_copy(voice, rate)
    assert rms_db(voice) - rms_db(soft) > 18.0


LINEUP_FILE = """\
# a comment line
N01 cutaway
  figures: no
  beat: the street is empty
  beat: a drawer slides open

S01 vocal: v01 v02   # her first lines
  still: stills/S01.png
  setup: KA1
  crop: 0.7
  place: a white salt desert
  act v02: she lifts her chin a little
  gaze: at us

N02 cutaway
  at: 77.6
  cam_move: a slow push-in
  figures: yes
"""


def test_shot_list_text_names_lines_not_times():
    shots = parse_shot_list(LINEUP_FILE)
    assert [shot.key for shot in shots] == ["N01", "S01", "N02"]
    s01 = shots[1]
    assert s01.kind == "vocal" and s01.sings == ("v01", "v02")
    assert s01.crop == pytest.approx(0.7)
    assert s01.acts == {"v02": "she lifts her chin a little"}
    assert s01.extra["gaze"] == "at us"
    assert shots[0].figures is False and shots[0].beats == ("the street is empty", "a drawer slides open")
    assert shots[2].at == "77.6" and shots[2].cam_move == "a slow push-in"


def test_shot_list_rejects_an_unknown_type():
    from atomic_flix.plan import PlanError
    with pytest.raises(PlanError, match="line 1"):
        parse_shot_list("S01 dance: v01\n")


def test_estimate_uses_the_measured_rates():
    rates = load_rates()
    assert rates["sung_pinned"] == pytest.approx(28.1)
    tasks = {"S01": {"key": "S01", "type": "vocal", "seconds": 10, "pin": "full"},
             "N01": {"key": "N01", "type": "cutaway", "seconds": 8, "pin": "none"}}
    batch = estimate_batch(tasks, takes={"S01": 4, "N01": 2}, rates=rates, cards=2)
    assert batch.rows["S01"].busy_s == pytest.approx(10 * 28.1 * 4)
    assert batch.rows["N01"].busy_s == pytest.approx(8 * 27.7 * 2)
    assert batch.gpu_hours == pytest.approx((1124 + 443.2) / 3600, rel=1e-6)
    assert batch.wall_hours == pytest.approx(batch.gpu_hours / 2)
    assert batch.takes == 6


def test_write_plan_files(tmp_path):
    rate = 48000
    save_wav(tmp_path / "audio" / "voice.wav", tone(20.0, rate, -24.0), rate)
    lines = [Line(key="v01", part="lead", text="Hush now", start=10.4, end=12.6)]
    pulse = Pulse(beats=tuple(round(k * 0.5, 3) for k in range(41)), downbeat_slot=0)
    shots = [ShotSpec(key="N01", kind="cutaway"), ShotSpec(key="S01", kind="vocal", sings=("v01",))]
    plan = plan_film(shots, lines, pulse, ends_at=20.0)
    written = write_plan(plan, tmp_path, voice=tmp_path / "audio" / "voice.wav")
    cuts = json.loads((tmp_path / "plan" / "cuts.json").read_text(encoding="utf-8"))
    assert [cut["key"] for cut in cuts["cuts"]] == ["N01", "S01"]
    assert cuts["cuts"][1] == {"key": "S01", "at": 10.0, "grid": "one"}
    task = json.loads((tmp_path / "plan" / "S01.task.json").read_text(encoding="utf-8"))
    assert task["key"] == "S01"
    soft, soft_rate = read_wav(tmp_path / "plan" / "S01.voice-soft.wav")
    assert soft_rate == 48000 and soft.shape == (task["seconds"] * 48000, 2)
    assert (tmp_path / "plan" / "S01.voice.wav") in written
    assert "gate_edges_db" in task
