"""
O.R.I.O.N — Skills Loader (Sprint 4, v0.2.0)

Universal Agent Skills Standard (SKILL.md) loader.
Discovers and loads skills following the hierarchical precedence:
  1. Workspace: `<workspace>/.orion/skills/` (highest precedence)
  2. Global:    `~/.orion/skills/` (intermediate)
  3. Builtin:   `src/orion/builtin/skills/` (base fallback)

Frontmatter Parsing:
  Parses YAML frontmatter enclosed in `---` blocks at the top of `SKILL.md`.
  Produces typed `SkillMetadata` and `SkillBundle` with lazy content loading.

ADR-010: Universal Agent Skills Standard
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from orion.skills.models import SkillBundle, SkillMetadata

logger = logging.getLogger(__name__)

_DEFAULT_GLOBAL_DIR = Path.home() / ".orion" / "skills"
_BUILTIN_DIR = Path(__file__).resolve().parent.parent / "builtin" / "skills"
_UNSET = object()

_FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL
)


def parse_skill_file(file_path: Path, source: str) -> SkillBundle:
    """
    Parse a SKILL.md file into a SkillBundle.

    Extracts YAML frontmatter for metadata and retains skill_path for lazy loading.
    Raises ValueError or yaml.YAMLError if parsing or metadata validation fails.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"Skill file not found: {file_path}")

    raw_text = file_path.read_text(encoding="utf-8")
    match = _FRONTMATTER_PATTERN.match(raw_text)
    if not match:
        raise ValueError(
            f"File '{file_path}' does not contain valid '---' YAML frontmatter."
        )

    frontmatter_raw, body = match.groups()
    parsed_yaml = yaml.safe_load(frontmatter_raw)
    if not isinstance(parsed_yaml, dict):
        raise ValueError(
            f"Frontmatter in '{file_path}' must evaluate to a YAML dictionary."
        )

    metadata = SkillMetadata(**parsed_yaml)
    return SkillBundle(
        metadata=metadata,
        skill_path=file_path,
        source=source,
        full_content=None,  # Loaded lazily on activation
    )


class SkillsLoader:
    """
    Hierarchical scanner for Universal Agent Skills (SKILL.md).

    Scans configured directories in reverse precedence order (Builtin -> Global -> Workspace),
    ensuring that higher-precedence skills override lower-precedence ones with identical names.
    """

    def __init__(
        self,
        workspace_dir: Path | None = None,
        global_dir: Path | None = None,
        builtin_dir: Any = _UNSET,
    ) -> None:
        self.workspace_dir = (
            workspace_dir / ".orion" / "skills" if workspace_dir else None
        )
        self.global_dir = global_dir or _DEFAULT_GLOBAL_DIR
        self.builtin_dir = _BUILTIN_DIR if builtin_dir is _UNSET else builtin_dir

    def discover(self) -> dict[str, SkillBundle]:
        """
        Scan all skill locations and return a dictionary of discovered skills
        keyed by skill name.

        Precedence (highest wins): Workspace > Global > Builtin.
        """
        discovered: dict[str, SkillBundle] = {}

        # 1. Builtin (lowest precedence)
        if self.builtin_dir and self.builtin_dir.is_dir():
            self._scan_directory(self.builtin_dir, source="builtin", target=discovered)

        # 2. Global
        if self.global_dir and self.global_dir.is_dir():
            self._scan_directory(self.global_dir, source="global", target=discovered)

        # 3. Workspace (highest precedence)
        if self.workspace_dir and self.workspace_dir.is_dir():
            self._scan_directory(self.workspace_dir, source="workspace", target=discovered)

        logger.info("Discovered %d skills across all sources.", len(discovered))
        return discovered

    def _scan_directory(
        self, root: Path, source: str, target: dict[str, SkillBundle]
    ) -> None:
        """Scan a directory for SKILL.md files and add them to target dict."""
        for entry in root.iterdir():
            skill_file: Path | None = None
            if entry.is_dir():
                candidate = entry / "SKILL.md"
                if candidate.is_file():
                    skill_file = candidate
            elif entry.is_file() and entry.name == "SKILL.md" or entry.is_file() and entry.suffix == ".md":
                skill_file = entry

            if skill_file is not None:
                try:
                    bundle = parse_skill_file(skill_file, source=source)
                    target[bundle.metadata.name] = bundle
                    logger.debug(
                        "Loaded skill '%s' from %s (%s)",
                        bundle.metadata.name,
                        skill_file,
                        source,
                    )
                except Exception as exc:
                    logger.warning(
                        "Skipping invalid skill at %s: %s", skill_file, exc
                    )

    @staticmethod
    def load_content(bundle: SkillBundle) -> str:
        """
        Read and cache the full content of a skill.
        Returns the markdown body after the YAML frontmatter.
        """
        if bundle.full_content is not None:
            return bundle.full_content

        raw = bundle.skill_path.read_text(encoding="utf-8")
        match = _FRONTMATTER_PATTERN.match(raw)
        if match:
            _, body = match.groups()
            content = body.strip()
        else:
            content = raw.strip()

        bundle.full_content = content
        return content
