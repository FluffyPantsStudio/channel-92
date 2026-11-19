"""The check over a placement: cost, rate, inserted pauses and drift."""

from __future__ import annotations

from atomic_flix.place.check import check_fit


def _fit(cost=0.03, rate=1.0, offsets=(0.3, 0.3, 0.31), rests=()):
    ties = [[1.0 + i, 1.0 + i + off] for i, off in enumerate(offsets)]
    return {"how": "sound",
            "vocal_spans": [{"from": 0.5, "to": 4.0, "cost": cost, "rate": rate, "ties": ties}],
            "map": [[t, r] for t, r in ties], "added_rests": list(rests)}


def _ids(flags):
    return sorted(flag["id"] for flag in flags)


def test_a_clean_placement_has_no_flags():
    assert check_fit(_fit()) == []


def test_cost_over_the_limit_is_flagged_and_the_limit_can_be_tightened():
    assert _ids(check_fit(_fit(cost=0.25))) == ["cost"]
    assert check_fit(_fit(cost=0.08), max_cost=0.09) == []
    assert _ids(check_fit(_fit(cost=0.12), max_cost=0.09)) == ["cost"]


def test_a_rate_off_by_more_than_18_percent_is_flagged():
    assert _ids(check_fit(_fit(rate=1.25))) == ["rate"]
    assert _ids(check_fit(_fit(rate=0.80))) == ["rate"]
    assert check_fit(_fit(rate=1.15)) == []


def test_drift_along_the_take_is_flagged():
    flags = check_fit(_fit(offsets=(0.10, 0.20, 0.32)))
    assert _ids(flags) == ["drift"]
    assert "0.22" in flags[0]["message"]


def test_inserted_pauses_are_flagged():
    flags = check_fit(_fit(rests=[{"at": 1.5, "render_at": 1.8, "seconds": 0.3}]))
    assert _ids(flags) == ["pause"]


def test_a_phrase_that_did_not_place_is_flagged():
    fit = _fit(cost=0.6)
    fit["vocal_spans"][0]["ties"] = []
    fit["map"] = []
    assert "unplaced" in _ids(check_fit(fit))
