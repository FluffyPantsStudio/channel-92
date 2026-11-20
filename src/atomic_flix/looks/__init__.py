"""The era looks: one ntsc-rs effect preset per Channel 92 era (`<era>.json` beside this file), and the schema they
are checked against.

ntsc-rs reads a preset as one flat JSON object: every setting by its key (a group's on/off switch is a key of its
own, its members sit beside it, not inside it) and `"version": 1`. Whole-number settings and menu choices are
integers, the rest floats, switches true or false. A value outside its range is clamped by ntsc-rs, and a key left
out takes ntsc-rs's oldest default, so our presets give every key. The keys, kinds, ranges and menu numbers below
were read from ntsc-rs v0.9.7's own source (crates/ntscrs/src/settings/standard.rs and settings.rs); where they came
from and what could not be established is in docs/third-party.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

HERE = Path(__file__).resolve().parent
PRESET_VERSION = 1

FIELDS = {0: "alternating", 1: "upper", 2: "lower", 3: "both", 4: "interleaved upper first",
          5: "interleaved lower first"}
FILTERS = {0: "constant K", 1: "Butterworth"}
LUMA_FILTERS = {0: "none", 1: "box", 2: "notch"}
LOWPASS = {0: "none", 1: "light", 2: "full"}
DEMODULATORS = {0: "box", 1: "notch", 2: "1-line comb", 3: "2-line comb", 4: "2D", 5: "2D adaptive"}
TAPE_SPEEDS = {0: "none", 1: "SP", 2: "LP", 3: "EP"}
INT32 = 2 ** 31


class PresetError(ValueError):
    """A preset that is not there or that ntsc-rs would not read as written."""


@dataclass(frozen=True)
class Setting:
    """One ntsc-rs setting: kind is int, float, share (a float 0 to 1), enum or bool."""

    kind: str
    low: float | None = None
    high: float | None = None
    choices: Mapping[int, str] = field(default_factory=dict)

    def problem(self, key: str, value: object) -> str | None:
        if self.kind == "bool":
            return None if type(value) is bool else f"{key} must be true or false, not {value!r}"
        if self.kind == "enum":
            ok = type(value) is int and value in self.choices
            return None if ok else f"{key} must be one of {sorted(self.choices)}, not {value!r}"
        if self.kind == "int" and type(value) is not int:
            return f"{key} must be a whole number, not {value!r}"
        if self.kind in ("float", "share") and (type(value) is bool or not isinstance(value, (int, float))):
            return f"{key} must be a number, not {value!r}"
        low, high = (0.0, 1.0) if self.kind == "share" else (self.low, self.high)
        if not low <= value <= high:
            return f"{key} must lie in {low:g} to {high:g}, not {value!r}"
        return None


def _int(low: int, high: int) -> Setting:
    return Setting("int", low, high)


def _float(low: float, high: float) -> Setting:
    return Setting("float", low, high)


SHARE = Setting("share")
SWITCH = Setting("bool")

SETTINGS: dict[str, Setting] = {
    "random_seed": _int(-INT32, INT32 - 1),
    "use_field": Setting("enum", choices=FIELDS),
    "filter_type": Setting("enum", choices=FILTERS),
    "input_luma_filter": Setting("enum", choices=LUMA_FILTERS),
    "chroma_lowpass_in": Setting("enum", choices=LOWPASS),
    "composite_preemphasis": _float(-1.0, 2.0),
    "composite_noise": SWITCH,
    "composite_noise_intensity": SHARE,
    "composite_noise_frequency": _float(0.0, 1.0),
    "composite_noise_detail": _int(1, 5),
    "snow_intensity": _float(0.0, 100.0),
    "snow_anisotropy": SHARE,
    "chroma_demodulation": Setting("enum", choices=DEMODULATORS),
    "luma_smear": _float(0.0, 1.0),
    "head_switching": SWITCH,
    "head_switching_height": _int(0, 24),
    "head_switching_offset": _int(0, 24),
    "head_switching_horizontal_shift": _float(-100.0, 100.0),
    "head_switching_start_mid_line": SWITCH,
    "head_switching_mid_line_position": SHARE,
    "head_switching_mid_line_jitter": SHARE,
    "tracking_noise": SWITCH,
    "tracking_noise_height": _int(0, 120),
    "tracking_noise_wave_intensity": _float(-50.0, 50.0),
    "tracking_noise_snow_intensity": _float(0.0, 1.0),
    "tracking_noise_snow_anisotropy": SHARE,
    "tracking_noise_noise_intensity": SHARE,
    "ringing": SWITCH,
    "ringing_frequency": SHARE,
    "ringing_power": _float(1.0, 10.0),
    "ringing_scale": _float(0.0, 10.0),
    "luma_noise": SWITCH,
    "luma_noise_intensity": SHARE,
    "luma_noise_frequency": _float(0.0, 1.0),
    "luma_noise_detail": _int(1, 5),
    "chroma_noise": SWITCH,
    "chroma_noise_intensity": SHARE,
    "chroma_noise_frequency": _float(0.0, 0.5),
    "chroma_noise_detail": _int(1, 5),
    "chroma_phase_error": SHARE,
    "chroma_phase_noise_intensity": SHARE,
    "chroma_delay_horizontal": _float(-40.0, 40.0),
    "chroma_delay_vertical": _int(-20, 20),
    "vhs_settings": SWITCH,
    "vhs_tape_speed": Setting("enum", choices=TAPE_SPEEDS),
    "vhs_chroma_loss": SHARE,
    "vhs_sharpen_enabled": SWITCH,
    "vhs_sharpen": _float(0.0, 5.0),
    "vhs_sharpen_frequency": _float(0.5, 4.0),
    "vhs_edge_wave_enabled": SWITCH,
    "vhs_edge_wave": _float(0.0, 20.0),
    "vhs_edge_wave_speed": _float(0.0, 10.0),
    "vhs_edge_wave_frequency": _float(0.0, 0.5),
    "vhs_edge_wave_detail": _int(1, 5),
    "vhs_chroma_vert_blend": SWITCH,
    "chroma_lowpass_out": Setting("enum", choices=LOWPASS),
    "scale_settings": SWITCH,
    "bandwidth_scale": _float(0.125, 8.0),
    "vertical_scale": _float(0.125, 8.8),
    "scale_with_video_size": SWITCH,
}


def check_preset(data: Mapping) -> list[str]:
    """Every way DATA is not a preset ntsc-rs reads as written (empty when it is one)."""
    problems = [f"{key} is not an ntsc-rs setting" for key in data if key not in SETTINGS and key != "version"]
    if data.get("version") != PRESET_VERSION or type(data.get("version")) is bool:
        problems.append(f"version must be {PRESET_VERSION}, not {data.get('version')!r}")
    for key, setting in SETTINGS.items():
        if key not in data:
            problems.append(f"{key} is missing (ntsc-rs would fill it with its own old default)")
            continue
        problem = setting.problem(key, data[key])
        if problem:
            problems.append(problem)
    return problems


def preset_file(era_id: str) -> Path:
    return HERE / f"{era_id}.json"


def load_preset(era_id: str) -> dict:
    """The era's preset, checked; PresetError when it is missing or would not read as written."""
    path = preset_file(era_id)
    if not path.is_file():
        raise PresetError(f"no look preset for {era_id!r} ({path.name})")
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = check_preset(data)
    if problems:
        raise PresetError(f"{path.name}: " + "; ".join(problems))
    return data


# Blending two presets for a year between eras (`blend.py`, docs/eras.md); imported last, it reads SETTINGS above.
from .blend import blend_presets  # noqa: E402

__all__ = ["PRESET_VERSION", "PresetError", "SETTINGS", "Setting", "blend_presets", "check_preset", "load_preset",
           "preset_file"]
