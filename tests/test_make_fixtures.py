import hashlib
import json

import numpy as np
import pytest

from atomic_flix.wav import read_wav

NAMES = ["steady-111", "decoy-kick-on-two", "drift-108-114", "bar-of-two"]


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    from tool_loader import load_tool

    mf = load_tool("make_fixtures")
    out = tmp_path_factory.mktemp("synthetic")
    mf.write_synthetic(out)
    return out


def _truth(root, name):
    return json.loads((root / name / "truth.json").read_text(encoding="utf-8"))


def _band_energy(sig, rate, t, lo, hi, span=0.04):
    a = int(round(t * rate))
    seg = sig[a:a + int(span * rate)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    freqs = np.fft.rfftfreq(len(seg), 1 / rate)
    return float(spec[(freqs >= lo) & (freqs < hi)].sum())


def _chroma(sig, rate, t0, t1):
    seg = sig[int(t0 * rate):int(t1 * rate)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    freqs = np.fft.rfftfreq(len(seg), 1 / rate)
    keep = (freqs > 60) & (freqs < 2000)
    pcs = np.round(12 * np.log2(freqs[keep] / 440.0)).astype(int) % 12
    chroma = np.bincount(pcs, weights=spec[keep], minlength=12)
    return chroma / (np.linalg.norm(chroma) + 1e-12)


def test_every_fixture_has_stems_and_truth(synth):
    for name in NAMES:
        truth = _truth(synth, name)
        assert truth["name"] == name
        for stem in ("drums", "band", "mix"):
            path = synth / name / truth["stems"][stem]
            data, rate = read_wav(path)
            assert rate == truth["rate"] == 22050
            assert data.shape[1] == 1
            assert data.shape[0] / rate > truth["beats"][-1] + 1.0
            assert path.stat().st_size < 4_000_000  # small


def test_steady_grid_pickup_and_bars(synth):
    truth = _truth(synth, "steady-111")
    beats = np.array(truth["beats"])
    assert truth["bpm"] == 111.0
    assert len(beats) == 1 + 32 * 4  # one pickup beat, then 32 bars
    assert np.allclose(np.diff(beats), 60 / 111, atol=1e-9)
    assert truth["pickup_beats"] == 1
    assert truth["first_one_beat"] == 1 and truth["downbeat_slot"] == 1
    assert len(truth["ones"]) == 32
    assert np.allclose(truth["ones"], beats[1::4])
    assert all(bar["extent"] == 4 for bar in truth["bars"])


def test_steady_kick_on_one_and_three_snare_on_two_and_four(synth):
    truth = _truth(synth, "steady-111")
    drums, rate = read_wav(synth / "steady-111" / "drums.wav")
    drums = drums[:, 0]
    beats = truth["beats"]
    low = {c: [] for c in range(4)}
    high = {c: [] for c in range(4)}
    for i, t in enumerate(beats):
        count = (i - truth["downbeat_slot"]) % 4  # 0 = the bar's one
        low[count].append(_band_energy(drums, rate, t, 30, 150))
        high[count].append(_band_energy(drums, rate, t, 1500, 6000))
    low_mean = {c: np.mean(v) for c, v in low.items()}
    high_mean = {c: np.mean(v) for c, v in high.items()}
    assert min(low_mean[0], low_mean[2]) > 10 * max(low_mean[1], low_mean[3])
    assert min(high_mean[1], high_mean[3]) > 10 * max(high_mean[0], high_mean[2])


def test_steady_chord_changes_on_one_only(synth):
    truth = _truth(synth, "steady-111")
    band, rate = read_wav(synth / "steady-111" / "band.wav")
    band = band[:, 0]
    beats = truth["beats"]
    half = 0.2
    changes = {c: [] for c in range(4)}
    for i in range(2, len(beats) - 1):
        t = beats[i]
        before = _chroma(band, rate, t - half, t - 0.02)
        after = _chroma(band, rate, t + 0.02, t + half)
        changes[(i - truth["downbeat_slot"]) % 4].append(1 - float(before @ after))
    assert np.mean(changes[0]) > 0.3
    assert max(np.mean(changes[c]) for c in (1, 2, 3)) < 0.05


def test_pickup_beat_has_snare_and_no_chord(synth):
    truth = _truth(synth, "steady-111")
    band, rate = read_wav(synth / "steady-111" / "band.wav")
    t0, t1 = truth["beats"][0], truth["beats"][1]
    assert np.max(np.abs(band[int(t0 * rate):int((t1 - 0.01) * rate), 0])) < 1e-3
    drums, _ = read_wav(synth / "steady-111" / "drums.wav")
    assert _band_energy(drums[:, 0], rate, t0, 1500, 6000) > 0


def test_decoy_loudest_kick_on_beat_two(synth):
    truth = _truth(synth, "decoy-kick-on-two")
    assert truth["first_one_beat"] == 1 and truth["downbeat_slot"] == 1
    drums, rate = read_wav(synth / "decoy-kick-on-two" / "drums.wav")
    drums = drums[:, 0]
    low = {c: [] for c in range(4)}
    for i, t in enumerate(truth["beats"]):
        low[(i - truth["downbeat_slot"]) % 4].append(_band_energy(drums, rate, t, 30, 150))
    means = {c: np.mean(v) for c, v in low.items()}
    assert max(means, key=means.get) == 1  # a low-band method would call beat 2 the one
    assert truth["expect"]["low_band_strongest_count"] == 1


def test_drift_tempo_runs_108_to_114(synth):
    truth = _truth(synth, "drift-108-114")
    beats = np.array(truth["beats"])
    gaps = np.diff(beats)
    assert gaps[0] == pytest.approx(60 / 108, rel=1e-3)
    assert gaps[-1] == pytest.approx(60 / 114, rel=1e-3)
    assert np.all(np.diff(gaps) < 0)
    assert truth["bpm"] is None
    assert truth["bpm_from"] == 108.0 and truth["bpm_to"] == 114.0


def test_drift_kicks_sit_on_the_truth_beats(synth):
    truth = _truth(synth, "drift-108-114")
    drums, rate = read_wav(synth / "drift-108-114" / "drums.wav")
    env = np.abs(drums[:, 0])
    for t in truth["ones"]:
        a = int((t - 0.03) * rate)
        b = int((t + 0.03) * rate)
        onset = a + int(np.argmax(env[a:b] > 0.05))
        assert abs(onset / rate - t) < 0.002


def test_bar_of_two_changes_phase(synth):
    truth = _truth(synth, "bar-of-two")
    lengths = [bar["extent"] for bar in truth["bars"]]
    assert lengths.count(2) == 1
    short = lengths.index(2)
    assert lengths[:short] == [4] * 8 and lengths[short + 1:] == [4] * 8
    first = truth["bars"][0]["first_beat"]
    change = truth["bars"][short + 1]["first_beat"]
    assert truth["expect"]["phase_change_at_beat"] == change
    assert truth["downbeat_slot"] == first % 4
    assert truth["expect"]["slot_after"] == change % 4
    assert (truth["downbeat_slot"] - truth["expect"]["slot_after"]) % 4 == 2
    assert len(truth["ones"]) == 17


def test_output_is_deterministic(tmp_path):
    from tool_loader import load_tool

    mf = load_tool("make_fixtures")
    a, b = tmp_path / "a", tmp_path / "b"
    mf.write_synthetic(a, names=["steady-111"])
    mf.write_synthetic(b, names=["steady-111"])
    for f in ("drums.wav", "band.wav", "mix.wav", "truth.json"):
        da = hashlib.sha256((a / "steady-111" / f).read_bytes()).hexdigest()
        db = hashlib.sha256((b / "steady-111" / f).read_bytes()).hexdigest()
        assert da == db


# ---- first-film pack extractor -------------------------------------------------


def _fake_film(root):
    (root / "audio").mkdir(parents=True)
    (root / "build").mkdir()
    for name in ("lead.wav", "rest.wav", "song.wav", "group.wav"):
        (root / "audio" / name).write_bytes(name.encode() * 10)
    for name in ("beats.json", "lines.json", "words.json", "drums.json", "hits.json",
                 "phrases.json", "loudness.json"):
        (root / "build" / name).write_text('{"x": 1}', encoding="utf-8")
    (root / "build" / "unrelated.json").write_text("{}", encoding="utf-8")
    return root


def test_extract_copies_named_files_with_manifest(tmp_path, tool):
    mf = tool("make_fixtures")
    src = _fake_film(tmp_path / "film")
    dst = tmp_path / "pack"
    manifest = mf.extract_first_film(src, dst)
    paths = sorted(item["path"] for item in manifest["files"])
    assert len(paths) == 11
    assert "audio/lead.wav" in paths and "build/beats.json" in paths
    assert not (dst / "build" / "unrelated.json").exists()
    for item in manifest["files"]:
        data = (dst / item["path"]).read_bytes()
        assert item["bytes"] == len(data)
        assert item["sha256"] == hashlib.sha256(data).hexdigest()
    on_disk = json.loads((dst / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk == manifest


def test_extract_records_known_truth(tmp_path, tool):
    mf = tool("make_fixtures")
    manifest = mf.extract_first_film(_fake_film(tmp_path / "film"), tmp_path / "pack")
    truth = manifest["truth"]
    assert truth["downbeat_slot"] == 0
    assert truth["phase_tie"] == [0, 2]
    assert truth["confirmed_by_ear"] is False
    note = (tmp_path / "pack" / "TRUTH.txt").read_text(encoding="utf-8")
    assert "bar phase 0" in note.lower()
    assert chr(0x2014) not in note  # no em dashes in prose


def test_extract_fails_on_missing_file(tmp_path, tool):
    mf = tool("make_fixtures")
    src = _fake_film(tmp_path / "film")
    (src / "build" / "hits.json").unlink()
    with pytest.raises(FileNotFoundError, match="hits.json"):
        mf.extract_first_film(src, tmp_path / "pack")
    assert not (tmp_path / "pack" / "manifest.json").exists()
