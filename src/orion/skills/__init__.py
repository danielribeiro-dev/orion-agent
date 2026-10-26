"""
O.R.I.O.N — Skills Subsystem (Sprint 4, v0.2.0)

Universal Agent Skills Standard:
  - Discovery: hierarchical scanning (Workspace > Global > Builtin)
  - Progressive Disclosure: minimal prompt footprint (<AVAILABLE_SKILLS>)
  - Activation: dynamic full-instruction injection via `use_skill` tool

ADR-010: Universal Agent Skills Standard
"""

from orion.skills.engine import SkillsEngine, UseSkillTool, render_available_skills
from orion.skills.loader import SkillsLoader, parse_skill_file
from orion.skills.models import SkillBundle, SkillMetadata

__all__ = [
    "SkillMetadata",
    "SkillBundle",
    "SkillsLoader",
    "parse_skill_file",
    "SkillsEngine",
    "UseSkillTool",
    "render_available_skills",
]
