"""
O.R.I.O.N — Cognitive Manifest Generator (Sprint 3, v0.2.0)

Progressive Cognitive Unpacking (PCU) — Phase 1:
  Generates an ultra-compact <COGNITIVE_MANIFEST> XML block for System Prompt
  injection at agent boot.

Budget constraint: < 250 tokens (enforced at generation time).
  Token estimate: conservative 4 chars/token rule.

The manifest contains only high-level metadata and pointers; the full memory
content is loaded on-demand via `recall` / `inspect_environment` tools.

ADR-013: Cognitive Manifest & PCU
ADR-014: 5-Sphere Cognitive Architecture
"""

from __future__ import annotations

import logging
from pathlib import Path

from orion.memory.models import CognitiveManifest

logger = logging.getLogger(__name__)

# Hard budget: < 250 tokens (4 chars/token conservative estimate = 1000 chars)
_TOKEN_BUDGET = 250
_CHARS_PER_TOKEN = 4
_CHAR_BUDGET = _TOKEN_BUDGET * _CHARS_PER_TOKEN  # 1000 chars


def _estimate_tokens(text: str) -> int:
    """Conservative token estimate: ceil(len(text) / 4)."""
    return (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN


class ManifestBudgetExceeded(Exception):
    """Raised when the generated manifest exceeds the 250-token budget."""

    def __init__(self, token_count: int) -> None:
        super().__init__(
            f"Cognitive Manifest exceeds budget: {token_count} tokens "
            f"(limit: {_TOKEN_BUDGET}). Trim the manifest fields."
        )
        self.token_count = token_count


class CognitiveManifestGenerator:
    """
    Synthesises the ultra-compact <COGNITIVE_MANIFEST> block for System Prompt
    injection.

    The generated block is strictly kept under 250 tokens so that it occupies
    a negligible fraction of the context window at boot.

    Usage::

        gen = CognitiveManifestGenerator(
            facts_store=facts_store,
            timeline=timeline,
            user_profile=profile,
            project_root=Path("."),
        )
        manifest = gen.generate()
        xml_block = manifest.to_xml_block()
        token_count = gen.count_tokens(xml_block)
        assert token_count < 250
    """

    def __init__(
        self,
        *,
        user_name: str = "Daniel",
        call_sign: str = "Senhor",
        active_project: str | None = None,
        confirmed_facts_count: int = 0,
        timeline_event_count: int = 0,
        last_session_date: str | None = None,
        available_skills_count: int = 0,
    ) -> None:
        self._user_name = user_name
        self._call_sign = call_sign
        self._active_project = active_project
        self._confirmed_facts_count = confirmed_facts_count
        self._timeline_event_count = timeline_event_count
        self._last_session_date = last_session_date
        self._available_skills_count = available_skills_count

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, enforce_budget: bool = True) -> CognitiveManifest:
        """
        Generate and return the CognitiveManifest.

        Args:
            enforce_budget: If True (default), raises ManifestBudgetExceeded
                            when the rendered XML block exceeds 250 tokens.

        Returns:
            CognitiveManifest — ready for to_xml_block() injection.

        Raises:
            ManifestBudgetExceeded: If enforce_budget=True and limit exceeded.
        """
        manifest = CognitiveManifest(
            user_name=self._user_name,
            call_sign=self._call_sign,
            active_project=self._active_project,
            top_facts_count=self._confirmed_facts_count,
            timeline_event_count=self._timeline_event_count,
            last_session_date=self._last_session_date,
            available_skills_count=self._available_skills_count,
        )

        if enforce_budget:
            xml_block = manifest.to_xml_block()
            token_count = _estimate_tokens(xml_block)
            if token_count >= _TOKEN_BUDGET:
                logger.error(
                    "Cognitive Manifest budget exceeded: %d tokens (limit %d).",
                    token_count,
                    _TOKEN_BUDGET,
                )
                raise ManifestBudgetExceeded(token_count)
            logger.debug(
                "Cognitive Manifest generated: %d tokens (budget %d).",
                token_count,
                _TOKEN_BUDGET,
            )

        return manifest

    @classmethod
    def count_tokens(cls, text: str) -> int:
        """Return the conservative token estimate for *text*."""
        return _estimate_tokens(text)

    @classmethod
    def from_live_data(
        cls,
        *,
        user_name: str = "Daniel",
        call_sign: str = "Senhor",
        project_root: Path | None = None,
        confirmed_facts_count: int = 0,
        timeline_event_count: int = 0,
        last_session_date: str | None = None,
        available_skills_count: int = 0,
    ) -> CognitiveManifestGenerator:
        """
        Factory method that auto-detects the active project name from the
        project root directory (uses the folder basename).
        """
        active_project: str | None = None
        if project_root is not None and project_root.is_dir():
            active_project = project_root.resolve().name

        return cls(
            user_name=user_name,
            call_sign=call_sign,
            active_project=active_project,
            confirmed_facts_count=confirmed_facts_count,
            timeline_event_count=timeline_event_count,
            last_session_date=last_session_date,
            available_skills_count=available_skills_count,
        )
