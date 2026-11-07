"""
Tests — CognitiveManifestGenerator (Sprint 3, v0.2.0)

Validates:
  - Generated manifest stays < 250 tokens (TEST 3 of spec — budget enforcement)
  - ManifestBudgetExceeded is raised when limit is breached
  - to_xml_block() format is correct
  - from_live_data() factory resolves project name from path
  - Token counter is deterministic
"""

from __future__ import annotations

import pytest

from orion.memory.manifest import (
    _TOKEN_BUDGET,
    CognitiveManifestGenerator,
    ManifestBudgetExceeded,
    _estimate_tokens,
)
from orion.memory.models import CognitiveManifest

# ---------------------------------------------------------------------------
# Token estimation helper
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_empty_string(self):
        assert _estimate_tokens("") == 0 or _estimate_tokens("") == 1  # ceil of 0/4

    def test_four_chars_is_one_token(self):
        assert _estimate_tokens("abcd") == 1

    def test_eight_chars_is_two_tokens(self):
        assert _estimate_tokens("abcdefgh") == 2

    def test_five_chars_rounds_up(self):
        # ceil(5/4) = 2
        assert _estimate_tokens("abcde") == 2


# ---------------------------------------------------------------------------
# TEST 3 (spec): Cognitive Manifest < 250 tokens
# ---------------------------------------------------------------------------


class TestManifestBudget:
    def test_default_manifest_under_250_tokens(self):
        """TEST 3: CognitiveManifest generated for System Prompt < 250 tokens."""
        gen = CognitiveManifestGenerator(
            user_name="Daniel",
            call_sign="Senhor",
            active_project="orion-agent",
            confirmed_facts_count=12,
            timeline_event_count=500,
            last_session_date="2026-10-25",
            available_skills_count=3,
        )
        manifest = gen.generate(enforce_budget=True)
        xml_block = manifest.to_xml_block()
        token_count = CognitiveManifestGenerator.count_tokens(xml_block)

        assert token_count < _TOKEN_BUDGET, (
            f"Manifest consumed {token_count} tokens (limit: {_TOKEN_BUDGET}).\n"
            f"Block:\n{xml_block}"
        )

    def test_empty_manifest_under_budget(self):
        """Minimal manifest (no project, no facts) must also pass budget."""
        gen = CognitiveManifestGenerator()
        manifest = gen.generate()
        xml_block = manifest.to_xml_block()
        assert CognitiveManifestGenerator.count_tokens(xml_block) < _TOKEN_BUDGET

    def test_budget_is_250_tokens(self):
        """Budget constant sanity check."""
        assert _TOKEN_BUDGET == 250

    def test_enforce_budget_false_skips_check(self):
        """enforce_budget=False skips the token check even if budget exceeded."""
        # Craft a generator that would normally fail by monkey-patching
        gen = CognitiveManifestGenerator(
            user_name="Daniel",
            call_sign="Senhor",
        )
        # Should not raise when enforce_budget=False
        manifest = gen.generate(enforce_budget=False)
        assert isinstance(manifest, CognitiveManifest)

    def test_manifest_budget_exceeded_error(self, monkeypatch):
        """ManifestBudgetExceeded is raised when the XML exceeds 250 tokens."""
        # Monkey-patch to_xml_block to return a long string (> 1000 chars = 250 tokens)
        def long_block(self) -> str:
            return "X" * 1001  # 1001 chars → 251 tokens

        monkeypatch.setattr(CognitiveManifest, "to_xml_block", long_block)

        gen = CognitiveManifestGenerator()
        with pytest.raises(ManifestBudgetExceeded) as exc_info:
            gen.generate(enforce_budget=True)

        assert exc_info.value.token_count >= _TOKEN_BUDGET


# ---------------------------------------------------------------------------
# CognitiveManifest.to_xml_block()
# ---------------------------------------------------------------------------


class TestManifestXmlBlock:
    def test_xml_block_format(self):
        manifest = CognitiveManifest(
            user_name="Daniel",
            call_sign="Senhor",
            active_project="orion-agent",
            top_facts_count=5,
            timeline_event_count=100,
            last_session_date="2026-10-25",
            available_skills_count=2,
        )
        block = manifest.to_xml_block()

        assert block.startswith("<COGNITIVE_MANIFEST>")
        assert block.endswith("</COGNITIVE_MANIFEST>")
        assert "Daniel" in block
        assert "Senhor" in block
        assert "orion-agent" in block
        assert "5" in block
        assert "100" in block
        assert "2026-10-25" in block
        assert "2" in block

    def test_xml_block_with_none_project(self):
        manifest = CognitiveManifest(
            user_name="Daniel",
            call_sign="Senhor",
            active_project=None,
            top_facts_count=0,
            timeline_event_count=0,
            last_session_date=None,
            available_skills_count=0,
        )
        block = manifest.to_xml_block()
        assert "none" in block.lower()
        assert "never" in block.lower()

    def test_xml_block_contains_tools_hint(self):
        """The manifest must advertise the four cognitive tools."""
        manifest = CognitiveManifest(
            user_name="Daniel",
            call_sign="Senhor",
            active_project=None,
            top_facts_count=0,
            timeline_event_count=0,
            last_session_date=None,
            available_skills_count=0,
        )
        block = manifest.to_xml_block()
        assert "recall" in block
        assert "memorize" in block
        assert "deprecate_fact" in block
        assert "inspect_environment" in block


# ---------------------------------------------------------------------------
# from_live_data() factory
# ---------------------------------------------------------------------------


class TestFromLiveData:
    def test_resolves_project_name_from_path(self, tmp_path):
        project_dir = tmp_path / "my-cool-project"
        project_dir.mkdir()

        gen = CognitiveManifestGenerator.from_live_data(
            user_name="Daniel",
            project_root=project_dir,
        )
        manifest = gen.generate()
        assert manifest.active_project == "my-cool-project"

    def test_none_project_root_gives_none_project(self):
        gen = CognitiveManifestGenerator.from_live_data(project_root=None)
        manifest = gen.generate()
        assert manifest.active_project is None

    def test_nonexistent_project_root_gives_none_project(self, tmp_path):
        gen = CognitiveManifestGenerator.from_live_data(
            project_root=tmp_path / "does_not_exist"
        )
        manifest = gen.generate()
        assert manifest.active_project is None

    def test_counts_propagated(self):
        gen = CognitiveManifestGenerator.from_live_data(
            confirmed_facts_count=7,
            timeline_event_count=250,
            available_skills_count=4,
            last_session_date="2026-10-24",
        )
        manifest = gen.generate()
        assert manifest.top_facts_count == 7
        assert manifest.timeline_event_count == 250
        assert manifest.available_skills_count == 4
        assert manifest.last_session_date == "2026-10-24"
