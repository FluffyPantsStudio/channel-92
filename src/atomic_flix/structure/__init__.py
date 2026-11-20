"""The song's structure (`structure`): sections sung and instrumental, story gaps and pacing, read before the concept.

Sections come from the lead stem's level and the lyric's [Section] order, never from listening; a person confirms
them by ear at gate 2.
"""

from .build import STORY_GAP_S, StructureInputs, build_structure
from .lines import TimedLine, timed_lines
from .page import reading, structure_page

__all__ = ["STORY_GAP_S", "StructureInputs", "TimedLine", "build_structure", "reading", "structure_page",
           "timed_lines"]
