"""
O.R.I.O.N — Agent Skills Models (Sprint 4, v0.2.0)

Universal Agent Skills Standard (SKILL.md) contracts:
  - SkillMetadata: parsed frontmatter from SKILL.md
  - SkillBundle: full skill package discovered on disk

ADR-010: Universal Agent Skills Standard
"""

from __future__ import annotations

from orion.memory.models import SkillBundle, SkillMetadata

__all__ = ["SkillMetadata", "SkillBundle"]
