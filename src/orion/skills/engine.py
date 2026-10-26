"""
O.R.I.O.N — Skills Engine (Sprint 4, v0.2.0)

Progressive Disclosure Execution Engine:
  - Phase 1 (Discovery):  Generates an ultra-lightweight `<AVAILABLE_SKILLS>` block
                          containing only skill names and descriptions (~60-80 tokens/skill).
  - Phase 2 (Activation): `UseSkillTool` (`use_skill`) dynamically loads full
                          `SKILL.md` instructions on demand into the ReAct turn context.

ADR-010: Universal Agent Skills Standard
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from orion.runtime.provider import RuntimeResult
from orion.skills.loader import SkillsLoader
from orion.skills.models import SkillBundle

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Conservative token count estimation (1 token ≈ 4 characters)."""
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def render_available_skills(skills: dict[str, SkillBundle] | list[SkillBundle]) -> str:
    """
    Render Phase 1 (Discovery) prompt injection block: `<AVAILABLE_SKILLS>`.

    Only includes skill name and high-level description to minimize token usage.
    """
    skill_list = list(skills.values()) if isinstance(skills, dict) else skills

    if not skill_list:
        return "<AVAILABLE_SKILLS>\n  (No agent skills available)\n</AVAILABLE_SKILLS>"

    lines = ["<AVAILABLE_SKILLS>"]
    for s in sorted(skill_list, key=lambda x: x.metadata.name):
        lines.append(f"  - {s.metadata.name}: {s.metadata.description}")
    lines.append("</AVAILABLE_SKILLS>")
    return "\n".join(lines)


class UseSkillTool:
    """
    Primitive ReAct tool to activate and load full instructions for a discovered skill.

    Conforms to the RuntimeProvider tool contract:
      - `supports(name: str) -> bool`
      - `execute(params: dict[str, Any]) -> RuntimeResult`
    """

    TOOL_NAME = "use_skill"

    def __init__(self, skills: dict[str, SkillBundle]) -> None:
        self._skills = skills

    def update_skills(self, skills: dict[str, SkillBundle]) -> None:
        """Update the internal registry of available skills."""
        self._skills = skills

    def supports(self, name: str) -> bool:
        return name == self.TOOL_NAME

    def execute(self, params: dict[str, Any]) -> RuntimeResult:
        skill_name = str(params.get("skill_name", "")).strip()
        if not skill_name:
            return RuntimeResult.fail(
                "Parameter 'skill_name' is required to invoke use_skill."
            )

        bundle = self._skills.get(skill_name)
        if not bundle:
            available = sorted(list(self._skills.keys()))
            return RuntimeResult.fail(
                f"Skill '{skill_name}' not found. Available skills: {available}"
            )

        content = SkillsLoader.load_content(bundle)
        logger.info("Skill '%s' loaded successfully (%s).", skill_name, bundle.source)

        return RuntimeResult.ok(
            output=content,
            skill_name=bundle.metadata.name,
            source=bundle.source,
            allowed_tools=bundle.metadata.allowed_tools or [],
        )


class SkillsEngine:
    """
    High-level facade coordinating skill discovery, manifest rendering,
    and runtime activation.
    """

    def __init__(self, loader: Optional[SkillsLoader] = None) -> None:
        self.loader = loader or SkillsLoader()
        self.discovered_skills: dict[str, SkillBundle] = {}
        self.tool = UseSkillTool(self.discovered_skills)

    def reload(self) -> dict[str, SkillBundle]:
        """Discover skills across hierarchy and refresh tool registry."""
        self.discovered_skills = self.loader.discover()
        self.tool.update_skills(self.discovered_skills)
        return self.discovered_skills

    def get_manifest_block(self) -> str:
        """Generate the Phase 1 `<AVAILABLE_SKILLS>` block for system prompt."""
        if not self.discovered_skills:
            self.reload()
        return render_available_skills(self.discovered_skills)

    def get_skill(self, name: str) -> Optional[SkillBundle]:
        """Retrieve a specific discovered skill bundle by name."""
        return self.discovered_skills.get(name)
