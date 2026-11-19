import hashlib

import numpy as np
import pytest

from atomic_flix.barmap import BarMap, apply_heard_slot, find_bar_one, naive_low_band_phase, pulse
from atomic_flix.barmap.spectral import spectra_of as _analyse

from bar_synth import four_on_the_floor, load_fixture, tie_song

_SEEN = {}


def spectra_of(samples, rate):
    """The real analysis, remembered per audio so the suite analyses each stem once."""
    key = (hashlib.sha1(np.ascontiguousarray(samples).tobytes()).hexdigest(), rate)
    if key not in _SEEN:
        _SEEN[key] = _analyse(samples, rate)
    return _SEEN[key]


def _bar_one(stems, truth, **kw):
    beats = np.array(truth["beats"])
    drums = spectra_of(stems["drums"], truth["rate"])
    band = spectra_of(stems["band"], truth["rate"])
    return find_bar_one(beats, drums, band, **kw)


def test_steady_song_finds_the_one_after_the_pickup():
    stems, truth = load_fixture("steady-111")
    result = _bar_one(stems, truth)
    assert result.status == "decided"
    assert result.downbeat_slot == truth["downbeat_slot"] == 1
    assert result.clearance >= 0.3


def test_decoy_kick_on_two_fools_the_low_band_but_not_the_method():
    stems, truth = load_fixture("decoy-kick-on-two")
    beats = np.array(truth["beats"])
    drums = spectra_of(stems["drums"], truth["rate"])
    assert naive_low_band_phase(beats, drums) == (truth["downbeat_slot"] + 1) % 4
    result = _bar_one(stems, truth)
    assert result.status == "decided"
    assert result.downbeat_slot == truth["downbeat_slot"]


def test_an_inserted_two_beat_bar_is_reported_and_never_rephased_silently():
    stems, truth = load_fixture("bar-of-two")
    result = _bar_one(stems, truth)
    assert result.status == "needs_click_check"
    assert len(result.phase_changes) == 1
    change = result.phase_changes[0]
    assert change["at_beat"] == truth["expect"]["phase_change_at_beat"]
    assert change["from_phase"] == truth["downbeat_slot"]
    assert change["to_phase"] == truth["expect"]["slot_after"]
    assert result.downbeat_slot == truth["downbeat_slot"]


def test_one_and_three_tie_is_reported_as_either_with_the_snare_beats_rejected():
    stems, truth = tie_song(bars=32)
    result = _bar_one(stems, truth)
    assert result.status == "needs_click_check"
    assert result.one_or_three == tuple(sorted((truth["downbeat_slot"], (truth["downbeat_slot"] + 2) % 4)))
    assert result.pair_margin > 3.0
    assert result.downbeat_slot is None
    cut_ok = set(result.cut_beats(np.array(truth["beats"])).tolist())
    ones = set(np.array(truth["beats"])[truth["downbeat_slot"]::4].tolist())
    assert ones <= cut_ok
    assert "click" in result.question


def test_bass_root_moving_on_the_one_breaks_the_tie():
    stems, truth = tie_song(bars=32, bass=True)
    result = _bar_one(stems, truth)
    assert result.within_pair["bass"] > 0.3
    assert result.status == "decided"
    assert result.downbeat_slot == truth["downbeat_slot"]


def test_eight_bar_phrases_break_the_tie():
    stems, truth = tie_song(bars=32, phrase_pad=True)
    result = _bar_one(stems, truth)
    assert result.within_pair["phrase"] > 0.3
    assert result.status == "decided"
    assert result.downbeat_slot == truth["downbeat_slot"]


def test_four_on_the_floor_without_snare_or_chords_stops_and_asks():
    stems, truth = four_on_the_floor(bars=16)
    result = _bar_one(stems, truth)
    assert result.status == "needs_click_check"
    assert result.downbeat_slot is None
    assert result.one_or_three is None


def test_a_person_overrides_with_a_heard_slot():
    stems, truth = tie_song(bars=16)
    result = _bar_one(stems, truth)
    snare_phase = (truth["downbeat_slot"] + 1) % 4
    picked = apply_heard_slot(result, snare_phase)
    assert picked.status == "override"
    assert picked.downbeat_slot == snare_phase
    assert picked.slot_scores == result.slot_scores
    assert any("snare" in note for note in picked.notes)


def test_override_on_the_evidence_side_has_no_warning():
    stems, truth = tie_song(bars=16)
    picked = apply_heard_slot(_bar_one(stems, truth), truth["downbeat_slot"])
    assert not any("snare" in note for note in picked.notes)


def test_stretches_are_reported_per_sixteen_bars():
    stems, truth = load_fixture("steady-111")
    result = _bar_one(stems, truth)
    assert len(result.stretches) == 2
    assert result.spans_backing == "2/2"


def test_pulse_writes_the_spec_shape(tmp_path):
    stems, truth = load_fixture("steady-111")
    out = pulse(stems["drums"], truth["rate"], band=stems["band"], mix=stems["mix"])
    data = out.to_dict()
    assert set(data) >= {"bpm", "beats", "downbeat_slot", "ones", "thirds", "grounds", "ruling"}
    assert set(data["grounds"]) >= {"slot_scores", "clearance", "spans_backing"}
    assert data["downbeat_slot"] == 1
    assert data["ones"][0] == pytest.approx(truth["ones"][0], abs=0.01)
    assert data["thirds"][0] == pytest.approx(truth["beats"][3], abs=0.01)
    path = out.write(tmp_path / "analysis")
    assert (path / "pulse.json").exists() and (path / "swells.json").exists()


def test_pulse_takes_the_slot_from_the_project():
    stems, truth = tie_song(bars=16)
    out = pulse(stems["drums"], truth["rate"], band=stems["band"], downbeat_slot=0)
    assert out.bar.status == "override"
    assert out.to_dict()["downbeat_slot"] == 0


def test_bar_map_is_immutable():
    stems, truth = load_fixture("steady-111")
    result = _bar_one(stems, truth)
    assert isinstance(result, BarMap)
    with pytest.raises(AttributeError):
        result.downbeat_slot = 2
