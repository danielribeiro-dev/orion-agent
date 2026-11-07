"""
Tests — Skills Loader & Progressive Disclosure (Sprint 4, v0.2.0)

Validates:
  - Teste 1 (spec): Scanner scans 10 skills and consumes < 800 tokens in <AVAILABLE_SKILLS>.
  - Teste 2 (spec): Activation of skill via use_skill loads SKILL.md instructions dynamically.
  - Hierarchical precedence: Workspace > Global > Builtin.
  - Validation: skill name regex, malformed frontmatter.
  - Built-in skill system-doctor discovery.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.runtime.provider import RuntimeResult
from orion.skills.engine import (
    SkillsEngine,
    UseSkillTool,
    estimate_tokens,
    render_available_skills,
)
from orion.skills.loader import SkillsLoader, parse_skill_file
from orion.skills.models import SkillMetadata

# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------


def create_sample_skill(
    directory: Path,
    name: str,
    description: str = "A test skill description.",
    body: str = "# Instructions\n\nPerform these tasks.",
) -> Path:
    """Create a sample SKILL.md in directory / name / SKILL.md."""
    skill_dir = directory / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    file_path = skill_dir / "SKILL.md"
    content = f"""---
name: {name}
description: {description}
license: Apache-2.0
compatibility: linux
allowed_tools:
  - run_command
---

{body}
"""
    file_path.write_text(content, encoding="utf-8")
    return file_path


# ---------------------------------------------------------------------------
# Test 1 (spec): 10 skills consume < 800 tokens in <AVAILABLE_SKILLS>
# ---------------------------------------------------------------------------


class TestProgressiveDisclosurePhase1:
    def test_ten_skills_under_800_tokens(self, tmp_path):
        """Teste 1 (spec): Scanner scans 10 skills and <AVAILABLE_SKILLS> < 800 tokens."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        for i in range(10):
            create_sample_skill(
                skills_dir,
                name=f"skill-service-{i}",
                description=f"Specialized automated assistant service number {i} for deployment.",
            )

        loader = SkillsLoader(global_dir=skills_dir, builtin_dir=None)
        discovered = loader.discover()
        assert len(discovered) == 10

        xml_block = render_available_skills(discovered)
        token_count = estimate_tokens(xml_block)

        assert token_count < 800, (
            f"Expected < 800 tokens for 10 skills, got {token_count} tokens.\n"
            f"Block:\n{xml_block}"
        )
        assert "<AVAILABLE_SKILLS>" in xml_block
        assert "</AVAILABLE_SKILLS>" in xml_block
        for i in range(10):
            assert f"skill-service-{i}" in xml_block

    def test_render_empty_skills(self):
        xml_block = render_available_skills({})
        assert "(No agent skills available)" in xml_block


# ---------------------------------------------------------------------------
# Test 2 (spec): use_skill loads instructions dynamically
# ---------------------------------------------------------------------------


class TestUseSkillActivation:
    def test_use_skill_loads_instructions(self, tmp_path):
        """Teste 2 (spec): use_skill loads SKILL.md body into observation."""
        skills_dir = tmp_path / "skills"
        body_content = "# Docker SOP\n\nAlways prune unused dangling volumes."
        create_sample_skill(
            skills_dir,
            name="docker-cleaner",
            description="Cleans docker containers and dangling resources.",
            body=body_content,
        )

        loader = SkillsLoader(global_dir=skills_dir, builtin_dir=None)
        engine = SkillsEngine(loader)
        engine.reload()

        assert engine.tool.supports("use_skill") is True
        assert engine.tool.supports("other_tool") is False

        result = engine.tool.execute({"skill_name": "docker-cleaner"})
        assert isinstance(result, RuntimeResult)
        assert result.success is True
        assert "Docker SOP" in result.output
        assert "dangling volumes" in result.output
        assert result.metadata.get("skill_name") == "docker-cleaner"

    def test_use_skill_nonexistent(self, tmp_path):
        loader = SkillsLoader(global_dir=tmp_path / "empty", builtin_dir=None)
        engine = SkillsEngine(loader)
        engine.reload()

        result = engine.tool.execute({"skill_name": "missing-skill"})
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_use_skill_missing_param(self):
        tool = UseSkillTool({})
        result = tool.execute({})
        assert result.success is False
        assert "skill_name" in result.error.lower()


# ---------------------------------------------------------------------------
# Hierarchical Precedence: Workspace > Global > Builtin
# ---------------------------------------------------------------------------


class TestSkillsHierarchy:
    def test_workspace_overrides_global_and_builtin(self, tmp_path):
        workspace = tmp_path / "ws"
        global_d = tmp_path / "global"
        builtin_d = tmp_path / "builtin"

        # Create same skill name in all three
        create_sample_skill(
            builtin_d,
            name="custom-tool",
            description="Builtin version.",
            body="BUILTIN BODY",
        )
        create_sample_skill(
            global_d,
            name="custom-tool",
            description="Global version.",
            body="GLOBAL BODY",
        )
        create_sample_skill(
            workspace / ".orion" / "skills",
            name="custom-tool",
            description="Workspace version.",
            body="WORKSPACE BODY",
        )

        loader = SkillsLoader(
            workspace_dir=workspace,
            global_dir=global_d,
            builtin_dir=builtin_d,
        )
        discovered = loader.discover()

        assert len(discovered) == 1
        bundle = discovered["custom-tool"]
        assert bundle.source == "workspace"
        assert bundle.metadata.description == "Workspace version."

        content = SkillsLoader.load_content(bundle)
        assert "WORKSPACE BODY" in content

    def test_global_overrides_builtin(self, tmp_path):
        global_d = tmp_path / "global"
        builtin_d = tmp_path / "builtin"

        create_sample_skill(
            builtin_d,
            name="audit-tool",
            description="Builtin audit.",
        )
        create_sample_skill(
            global_d,
            name="audit-tool",
            description="Global audit.",
        )

        loader = SkillsLoader(
            workspace_dir=None,
            global_dir=global_d,
            builtin_dir=builtin_d,
        )
        discovered = loader.discover()

        assert discovered["audit-tool"].source == "global"
        assert discovered["audit-tool"].metadata.description == "Global audit."


# ---------------------------------------------------------------------------
# Builtin skill discovery (system-doctor)
# ---------------------------------------------------------------------------


class TestBuiltinSkill:
    def test_system_doctor_discovered(self):
        loader = SkillsLoader(workspace_dir=None, global_dir=None)
        discovered = loader.discover()

        assert "system-doctor" in discovered
        bundle = discovered["system-doctor"]
        assert bundle.source == "builtin"
        assert "diagnóstico" in bundle.metadata.description.lower()

        content = SkillsLoader.load_content(bundle)
        assert "System Doctor" in content


# ---------------------------------------------------------------------------
# Validation & Error Handling
# ---------------------------------------------------------------------------


class TestValidation:
    def test_invalid_skill_name_rejected(self):
        with pytest.raises(ValueError):
            SkillMetadata(
                name="Invalid_Name_With_Uppercase",
                description="desc",
            )

        with pytest.raises(ValueError):
            SkillMetadata(
                name="invalid--double-hyphen",
                description="desc",
            )

    def test_parse_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_skill_file(tmp_path / "nonexistent.md", source="test")

    def test_missing_frontmatter_raises(self, tmp_path):
        bad_file = tmp_path / "bad.md"
        bad_file.write_text("# No frontmatter here")
        with pytest.raises(ValueError, match="frontmatter"):
            parse_skill_file(bad_file, source="test")
