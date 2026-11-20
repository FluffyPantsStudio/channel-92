"""Blending two era presets into the look of a year between them (`eras.look_for_year` picks the two and the weight).

WEIGHT is the share of the way from LOW to HIGH: 0 gives LOW exactly, 1 gives HIGH exactly. Each setting is
blended by its kind in the schema (`looks.SETTINGS`):

    float, share   linear: LOW * (1 - WEIGHT) + HIGH * WEIGHT
    int            linear, then rounded (half up)
    enum, bool     the nearer anchor's value; a tie (WEIGHT 0.5) goes to the later era
    random_seed    an int in the schema, but a seed: the nearer anchor's, like a menu choice
    an angle       (`CYCLIC`) the short way round the circle, wrapped back into the setting's range. The one angle
                   is `chroma_phase_error`, a fraction of a turn that ntsc-rs wraps, so 0.985 is a few degrees the
                   other way from 0, not almost a full turn: blending 0.0 and 0.985 stays within 0.015 of 0. A
                   straight line through 0.5 would turn every hue round (red to green). The other settings are
                   intensities, positions along a line, frequencies or sizes, none of them cyclic
                   (`chroma_phase_noise_intensity` is how much the phase jitters, not an angle)

A switch group is a switch and the settings that belong to it (`GROUPS`); ntsc-rs ignores the members while the
switch is off. Snow has no switch of its own: it counts as on while `snow_intensity` is above 0.

    on at both     the switch stays on, the members are blended by kind (a nested group, such as the VHS edge wave
                   inside the VHS settings, by these same rules)
    on at one      the group is on once that anchor's weight reaches FADE_IN (0.2); it then takes every member
                   from that anchor, with its strength members (`STRENGTH`) scaled by that weight toward their
                   neutral value, so the effect fades in or out instead of switching. Below FADE_IN the group is
                   off and taken whole from the other anchor
    off at both    taken whole from the nearer anchor (still off)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from . import SETTINGS

FADE_IN = 0.2
EPSILON = 1e-9          # weights come from (year - anchor) / 10; 1 - 0.8 must still count as 0.2
NEAREST = frozenset({"random_seed"})
CYCLIC: dict[str, float] = {"chroma_phase_error": 1.0}     # an angle, and its period (one turn)

# The strength members: what makes an effect stronger, mapped to the value at which it does nothing. Every other
# member of a group (a frequency, a detail level, an offset, a menu choice) keeps the on-side value as it is.
STRENGTH: dict[str, float] = {
    "composite_noise_intensity": 0.0,
    "snow_intensity": 0.0,
    "head_switching_height": 0.0,
    "head_switching_horizontal_shift": 0.0,
    "tracking_noise_height": 0.0,
    "tracking_noise_wave_intensity": 0.0,
    "tracking_noise_snow_intensity": 0.0,
    "tracking_noise_noise_intensity": 0.0,
    "ringing_scale": 0.0,
    "luma_noise_intensity": 0.0,
    "chroma_noise_intensity": 0.0,
    "vhs_chroma_loss": 0.0,
    "vhs_sharpen": 0.0,
    "vhs_edge_wave": 0.0,
    "bandwidth_scale": 1.0,
    "vertical_scale": 1.0,
}


@dataclass(frozen=True)
class Group:
    """A switch (None for snow, which is on while its intensity is above 0), its plain members and nested groups."""

    name: str
    switch: str | None
    members: tuple[str, ...]
    inner: tuple["Group", ...] = ()

    @property
    def keys(self) -> tuple[str, ...]:
        own = (self.switch,) if self.switch else ()
        return own + self.members + tuple(key for group in self.inner for key in group.keys)

    def is_on(self, preset: Mapping) -> bool:
        return bool(preset[self.switch]) if self.switch else preset["snow_intensity"] > 0


GROUPS: tuple[Group, ...] = (
    Group("composite_noise", "composite_noise",
          ("composite_noise_intensity", "composite_noise_frequency", "composite_noise_detail")),
    Group("snow", None, ("snow_intensity", "snow_anisotropy")),
    Group("head_switching", "head_switching",
          ("head_switching_height", "head_switching_offset", "head_switching_horizontal_shift"),
          (Group("head_switching_start_mid_line", "head_switching_start_mid_line",
                 ("head_switching_mid_line_position", "head_switching_mid_line_jitter")),)),
    Group("tracking_noise", "tracking_noise",
          ("tracking_noise_height", "tracking_noise_wave_intensity", "tracking_noise_snow_intensity",
           "tracking_noise_snow_anisotropy", "tracking_noise_noise_intensity")),
    Group("ringing", "ringing", ("ringing_frequency", "ringing_power", "ringing_scale")),
    Group("luma_noise", "luma_noise", ("luma_noise_intensity", "luma_noise_frequency", "luma_noise_detail")),
    Group("chroma_noise", "chroma_noise",
          ("chroma_noise_intensity", "chroma_noise_frequency", "chroma_noise_detail")),
    Group("vhs_settings", "vhs_settings", ("vhs_tape_speed", "vhs_chroma_loss", "vhs_chroma_vert_blend"),
          (Group("vhs_sharpen", "vhs_sharpen_enabled", ("vhs_sharpen", "vhs_sharpen_frequency")),
           Group("vhs_edge_wave", "vhs_edge_wave_enabled",
                 ("vhs_edge_wave", "vhs_edge_wave_speed", "vhs_edge_wave_frequency", "vhs_edge_wave_detail")))),
    Group("scale_settings", "scale_settings", ("bandwidth_scale", "vertical_scale", "scale_with_video_size")),
)


def _round(value: float) -> int:
    return int(math.floor(value + 0.5))


def _nearer(low: Mapping, high: Mapping, weight: float) -> Mapping:
    return high if weight >= 0.5 else low


def _blend_angle(key: str, start: float, end: float, weight: float) -> float:
    """START to END the short way round a circle of CYCLIC[key], WEIGHT of the way, back inside the setting's
    range (from its low end, 0 for a share, for one period)."""
    period = CYCLIC[key]
    floor = SETTINGS[key].low if SETTINGS[key].low is not None else 0.0
    step = (end - start + period / 2) % period - period / 2
    return float((start + step * weight - floor) % period + floor)


def _blend_value(key: str, low: Mapping, high: Mapping, weight: float):
    kind = SETTINGS[key].kind
    if kind in ("enum", "bool") or key in NEAREST:
        return _nearer(low, high, weight)[key]
    if key in CYCLIC:
        return _blend_angle(key, low[key], high[key], weight)
    mixed = low[key] * (1 - weight) + high[key] * weight
    return _round(mixed) if kind == "int" else float(mixed)


def _scaled(key: str, value, share: float):
    if key not in STRENGTH:
        return value
    neutral = STRENGTH[key]
    mixed = value * share + neutral * (1 - share)
    return _round(mixed) if SETTINGS[key].kind == "int" else float(mixed)


def _blend_group(group: Group, low: Mapping, high: Mapping, weight: float) -> dict:
    low_on, high_on = group.is_on(low), group.is_on(high)
    if low_on and high_on:
        out = {key: _blend_value(key, low, high, weight)
               for key in ((group.switch,) if group.switch else ()) + group.members}
        for inner in group.inner:
            out.update(_blend_group(inner, low, high, weight))
        return out
    if low_on or high_on:
        source, share = (low, 1 - weight) if low_on else (high, weight)
        if share + EPSILON >= FADE_IN:
            return {key: _scaled(key, source[key], share) for key in group.keys}
        source = high if low_on else low
        return {key: source[key] for key in group.keys}
    nearer = _nearer(low, high, weight)
    return {key: nearer[key] for key in group.keys}


def check_weight(weight: object) -> float:
    """WEIGHT as a float from 0 to 1; TypeError or ValueError for anything else."""
    if type(weight) is bool or not isinstance(weight, (int, float)):
        raise TypeError(f"a weight is a number from 0 to 1, not {weight!r}")
    if not 0.0 <= weight <= 1.0:          # also refuses nan
        raise ValueError(f"a weight lies from 0 to 1, not {weight!r}")
    return float(weight)


def blend_presets(low: Mapping, high: Mapping, weight: float) -> dict:
    """The preset WEIGHT of the way from LOW to HIGH (two checked era presets), by the rules above. A new dict;
    LOW and HIGH are only read."""
    weight = check_weight(weight)
    if weight == 0.0:
        return dict(low)
    if weight == 1.0:
        return dict(high)
    out: dict = {}
    for group in GROUPS:
        out.update(_blend_group(group, low, high, weight))
    for key in SETTINGS:
        if key not in out:
            out[key] = _blend_value(key, low, high, weight)
    out["version"] = high["version"]
    return {key: out[key] for key in (*SETTINGS, "version")}


__all__ = ["CYCLIC", "FADE_IN", "GROUPS", "Group", "STRENGTH", "blend_presets", "check_weight"]
