import numpy as np
import pytest

from atomic_flix.barmap.grid import beat_grid, global_tempo
from atomic_flix.barmap.spectral import spectra_of

from bar_synth import load_fixture, tie_song


def _worst_miss(found, truth):
    found = np.asarray(found)
    return max(np.min(np.abs(found - t)) for t in truth)


@pytest.mark.parametrize("name", ["steady-111", "decoy-kick-on-two", "bar-of-two"])
def test_steady_grids_land_within_ten_ms(name):
    stems, truth = load_fixture(name)
    grid = beat_grid(spectra_of(stems["drums"], truth["rate"]))
    assert _worst_miss(grid.beats, truth["beats"]) <= 0.010
    assert abs(len(grid.beats) - len(truth["beats"])) <= 1
    assert grid.bpm == pytest.approx(111.0, abs=0.5)


def test_drifting_tempo_keeps_every_beat_within_twenty_ms():
    stems, truth = load_fixture("drift-108-114")
    grid = beat_grid(spectra_of(stems["drums"], truth["rate"]))
    assert _worst_miss(grid.beats, truth["beats"]) <= 0.020
    assert grid.tempo_bpm[0] < grid.tempo_bpm[-1]


def test_grid_from_the_full_mix_stays_within_the_snap_window():
    # Beating between the chord's partials blurs some attacks in the mix, so
    # the drum stem is preferred; the mix must still hold every beat to 30 ms.
    stems, truth = load_fixture("steady-111")
    grid = beat_grid(spectra_of(stems["mix"], truth["rate"]))
    assert _worst_miss(grid.beats, truth["beats"]) <= 0.030
    assert abs(len(grid.beats) - len(truth["beats"])) <= 1


def test_tempo_is_found_without_a_hint_and_a_hint_is_respected():
    stems, truth = load_fixture("steady-111")
    spectra = spectra_of(stems["drums"], truth["rate"])
    assert global_tempo(spectra) == pytest.approx(111.0, abs=1.0)
    assert global_tempo(spectra, hint_bpm=55.5) == pytest.approx(55.5, abs=0.5)


def test_resampled_rates_give_the_same_grid():
    stems, truth = tie_song(bars=12)
    mono = stems["drums"]
    doubled = np.repeat(mono, 2)  # a crude 44.1 kHz copy is enough to test the rate handling
    grid = beat_grid(spectra_of(doubled, 2 * truth["rate"]))
    assert _worst_miss(grid.beats, truth["beats"]) <= 0.010


def test_stereo_input_is_accepted():
    stems, truth = load_fixture("steady-111")
    stereo = np.stack([stems["drums"], stems["drums"]], axis=1)
    grid = beat_grid(spectra_of(stereo, truth["rate"]))
    assert _worst_miss(grid.beats, truth["beats"]) <= 0.010
