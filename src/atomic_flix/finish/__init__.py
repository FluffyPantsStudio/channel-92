"""Finishing a film: the logo, the era's look (ntsc-rs, run from its own command line) and the intro, laid on the
graded cut into the delivered film (`chain.py`); the masters stay clean. Finding and running ntsc-rs: `ntsc.py`."""

from .chain import Finished, Treatment, finish_cut, sample_still
from .ntsc import ENV, RELEASES, NtscError, find_ntsc_rs, missing_sentence

__all__ = ["ENV", "Finished", "NtscError", "RELEASES", "Treatment", "find_ntsc_rs", "finish_cut", "missing_sentence",
           "sample_still"]
