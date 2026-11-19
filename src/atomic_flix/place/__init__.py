"""Placing renders on the song by their sound, and building the vocal audio a render hears."""

from .check import check_fit
from .features import levels_db, resample, sound_features, working_level_db
from .fit import fit_by_sound, render_time_at, voiced_phrases
from .voice import GatedVoice, gated_voice, soft_copy, write_voice_pair

__all__ = [
    "GatedVoice", "check_fit", "fit_by_sound", "gated_voice", "levels_db", "render_time_at", "resample",
    "soft_copy", "sound_features", "voiced_phrases", "working_level_db", "write_voice_pair",
]
