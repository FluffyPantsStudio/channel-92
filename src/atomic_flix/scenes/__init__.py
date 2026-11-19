"""Blender building-block scenes: a JSON scene description compiled into a flat op list, rendered by Blender with
its layers, and turned into control clips for video models. See FORMAT.md in this folder.

Blender is only a subprocess (blender_run.py runs inside it); nothing else here imports bpy.
"""

from .guides import GuideSizeError, check_guide_size, make_guides
from .library import BuildContext, Library
from .plan import apply_overrides, compile_all, compile_plan, write_job
from .schema import SceneError, check_scene, load_scene

__all__ = ["BuildContext", "GuideSizeError", "Library", "SceneError", "apply_overrides", "check_guide_size",
           "check_scene", "compile_all", "compile_plan", "load_scene", "make_guides", "write_job"]
