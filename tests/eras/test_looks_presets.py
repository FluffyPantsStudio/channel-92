"""The era presets are ntsc-rs effect settings in its own JSON form (established from its source, see
docs/third-party.md): every key it reads, each value of the right kind and inside its range, version 1."""

from __future__ import annotations

import json

import pytest

from atomic_flix.eras import ERAS, era
from atomic_flix.looks import PRESET_VERSION, SETTINGS, PresetError, check_preset, load_preset

IDS = [row.id for row in ERAS]


@pytest.mark.parametrize("row", ERAS, ids=IDS)
def test_every_era_preset_validates_against_the_schema(row):
    text = row.preset.read_text(encoding="utf-8")
    data = json.loads(text)
    assert check_preset(data) == []
    assert set(data) == set(SETTINGS) | {"version"} and data["version"] == PRESET_VERSION
    assert load_preset(row.id) == data


@pytest.mark.parametrize("row", ERAS, ids=IDS)
def test_integers_are_written_as_integers_and_floats_as_floats(row):
    data = json.loads(row.preset.read_text(encoding="utf-8"))
    for key, setting in SETTINGS.items():
        value = data[key]
        if setting.kind in ("int", "enum"):
            assert type(value) is int, key
        elif setting.kind in ("float", "share"):
            assert type(value) is float, key
        else:
            assert type(value) is bool, key


def test_the_schema_refuses_what_ntsc_rs_would_not_read():
    good = load_preset("1980s")
    assert check_preset({**good, "grain": 0.5}) == ["grain is not an ntsc-rs setting"]
    assert any("version" in p for p in check_preset({k: v for k, v in good.items() if k != "version"}))
    assert any("luma_smear" in p for p in check_preset({**good, "luma_smear": 1.5}))
    assert any("vhs_tape_speed" in p for p in check_preset({**good, "vhs_tape_speed": 9}))
    assert any("head_switching" in p for p in check_preset({**good, "head_switching": 1}))
    assert any("chroma_delay_vertical" in p for p in check_preset({**good, "chroma_delay_vertical": 2.5}))
    missing = {k: v for k, v in good.items() if k != "snow_intensity"}
    assert check_preset(missing) == ["snow_intensity is missing (ntsc-rs would fill it with its own old default)"]
    with pytest.raises(PresetError):
        load_preset("1940s")


def test_the_schema_has_every_setting_ntsc_rs_0_9_7_reads():
    assert len(SETTINGS) == 60
    assert SETTINGS["vhs_tape_speed"].choices == {0: "none", 1: "SP", 2: "LP", 3: "EP"}
    assert SETTINGS["composite_preemphasis"].low == -1.0 and SETTINGS["composite_preemphasis"].high == 2.0


def _get(name: str, key: str):
    return load_preset(name)[key]


def test_the_presets_are_tuned_to_each_eras_medium():
    # Tuned on real renders of a test clip with the real ntsc-rs (docs/eras.md), judged by eye: what each era must
    # still be, not the exact numbers.
    # 1950s: monochrome kinescope, no tape
    assert not _get("1950s", "vhs_settings") and not _get("1950s", "head_switching")
    # 1960s: early colour, the heaviest colour smear; the vhs group only carries the colour blend, no tape runs
    assert _get("1960s", "chroma_delay_horizontal") == max(_get(r.id, "chroma_delay_horizontal") for r in ERAS)
    assert _get("1960s", "vhs_tape_speed") == 0 and not _get("1960s", "head_switching")
    # 1970s: broadcast composite, no tape
    assert not _get("1970s", "vhs_settings") and _get("1970s", "ringing")
    # 1980s: VHS and Betamax tape: head switching, tracking noise
    assert _get("1980s", "vhs_settings") and _get("1980s", "head_switching") and _get("1980s", "tracking_noise")
    # 1990s: a worn camcorder tape: a slower speed, more edge wave and noise than the 1980s deck, no switching band
    assert _get("1990s", "vhs_settings") and _get("1990s", "vhs_tape_speed") > _get("1980s", "vhs_tape_speed")
    assert _get("1990s", "vhs_edge_wave") > _get("1980s", "vhs_edge_wave") and not _get("1990s", "head_switching")
    # 2000s: late analog, composite noise only, the cleanest of all
    assert not _get("2000s", "vhs_settings") and _get("2000s", "composite_noise")
    assert _get("2000s", "luma_smear") == min(_get(r.id, "luma_smear") for r in ERAS)
    assert era("2000s").preset.name == "2000s.json"


def test_no_preset_turns_skin_orange():
    # composite_preemphasis is the one setting that moves colour: on a neutral preset 0.5 took a skin patch from
    # RGB (132, 85, 67) to (142, 83, 51). The tuned presets keep it at or under a third of the old values.
    for era_ in ERAS:
        assert _get(era_.id, "composite_preemphasis") <= 0.4, era_.id
