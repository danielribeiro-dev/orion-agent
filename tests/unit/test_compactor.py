"""
Tests — Dynamic Context Compactor (Sprint 4, v0.2.0)

Validates:
  - Teste 3 (spec): 40-turn history compaction achieves >= 60% reduction,
    preserves last 3 turns intact, and maintains modified active files.
  - Directional focus filtering (/compact <focus>).
  - Active file tracking across tool calls and outputs.
  - Automatic threshold trigger (should_compact at 80%).
  - Short history handling (turns <= vital tail).
  - Notification formatting.
"""

from __future__ import annotations

import pytest

from orion.memory.models import CompactionResult
from orion.timeline.compactor import ContextCompactor, TurnData, estimate_tokens


# ---------------------------------------------------------------------------
# Test 3 (spec): 40 turns compaction >= 60% reduction & vital tail preserved
# ---------------------------------------------------------------------------


class TestCompactionReduction:
    def test_forty_turns_compaction_reduction_and_tail(self):
        """
        Teste 3 (spec): Dynamic Compactor acionado em histórico com 40 turnos
        reduz o tamanho total em pelo menos 60%, mantendo intactos os 3 turnos
        finais literais e a lista de arquivos modificados.
        """
        compactor = ContextCompactor(vital_tail_count=3)
        turns: list[TurnData] = []

        # Generate 40 turns with verbose tool outputs (e.g. read_file / terminal logs)
        for i in range(40):
            turns.append(
                TurnData(
                    turn_index=i,
                    user_input=f"Step {i}: Inspect and modify authentication layer part {i}.",
                    thinking=f"Turn {i} reasoning: Need to read module and verify signatures.",
                    tool_name="read_file" if i % 2 == 0 else "edit_file",
                    tool_params={
                        "path": f"src/orion/auth/module_{i % 5}.py",
                        "lines": [1, 200],
                    },
                    tool_output=(
                        f"Line 1: # Header for module {i}\n"
                        + "\n".join(f"def helper_{j}(): return {j * i}" for j in range(30))
                        + f"\nExecution result: OK for turn {i}."
                    ),
                    modified_files=[f"src/orion/auth/module_{i % 5}.py"] if i % 2 != 0 else [],
                )
            )

        # Full original token count
        original_full = "\n\n".join(t.to_full_text() for t in turns)
        original_tokens = estimate_tokens(original_full)

        result = compactor.compact(turns, vital_tail_count=3)

        assert isinstance(result, CompactionResult)
        assert result.original_turns == 40
        assert result.preserved_tail_turns == 3

        # Reduction percentage: tokens_saved / original_tokens >= 0.60
        reduction_ratio = result.tokens_saved / original_tokens
        assert reduction_ratio >= 0.60, (
            f"Expected reduction >= 60%, got {reduction_ratio * 100:.2f}% "
            f"(saved {result.tokens_saved} of {original_tokens} tokens)."
        )

        # Verify the last 3 turns (37, 38, 39) are intact in the summary
        for tail_idx in (37, 38, 39):
            assert f"--- Turn {tail_idx} ---" in result.compacted_summary
            assert f"Step {tail_idx}:" in result.compacted_summary

        # Prior turns should NOT be fully expanded (bulky outputs pruned)
        assert "def helper_25():" not in result.compacted_summary[:500]

        # Active files list must contain all modified files (module_1, module_3)
        assert len(result.active_files) >= 5
        for mod_idx in range(5):
            assert any(f"module_{mod_idx}.py" in f for f in result.active_files)


# ---------------------------------------------------------------------------
# Directional Focus (/compact <focus>)
# ---------------------------------------------------------------------------


class TestDirectionalFocus:
    def test_focus_highlighted_in_summary(self):
        compactor = ContextCompactor(vital_tail_count=2)
        turns = [
            TurnData(turn_index=0, user_input="Setup database connection", tool_name="run_command"),
            TurnData(turn_index=1, user_input="Refactor auth token validation", tool_name="edit_file"),
            TurnData(turn_index=2, user_input="Fix styles in css", tool_name="write_file"),
            TurnData(turn_index=3, user_input="Final verification", thinking="Check auth again"),
        ]

        result = compactor.compact(turns, focus="auth", vital_tail_count=1)

        assert result.focus == "auth"
        assert "Directional Focus: auth" in result.compacted_summary
        assert "Matches focus: 'auth'" in result.compacted_summary


# ---------------------------------------------------------------------------
# Threshold Trigger (should_compact)
# ---------------------------------------------------------------------------


class TestThresholdTrigger:
    def test_should_compact_at_80_percent(self):
        compactor = ContextCompactor(threshold_percent=0.80)

        # Below threshold (79%)
        assert compactor.should_compact(current_tokens=790, max_tokens=1000) is False

        # Exactly at threshold (80%)
        assert compactor.should_compact(current_tokens=800, max_tokens=1000) is True

        # Above threshold (85%)
        assert compactor.should_compact(current_tokens=850, max_tokens=1000) is True

    def test_zero_max_tokens_returns_false(self):
        compactor = ContextCompactor()
        assert compactor.should_compact(100, 0) is False


# ---------------------------------------------------------------------------
# Short history & Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_history_shorter_than_vital_tail(self):
        compactor = ContextCompactor(vital_tail_count=5)
        turns = [
            TurnData(turn_index=0, user_input="Hello"),
            TurnData(turn_index=1, user_input="World"),
        ]
        result = compactor.compact(turns)
        assert result.original_turns == 2
        assert result.tokens_saved == 0

    def test_compact_with_dicts_and_strings(self):
        compactor = ContextCompactor(vital_tail_count=1)
        raw_turns = [
            {"turn_index": 0, "user_input": "Run pytest", "tool_output": "100 passed"},
            {"turn_index": 1, "user_input": "Next task", "tool_output": "OK"},
        ]
        result = compactor.compact(raw_turns, vital_tail_count=1)
        assert result.original_turns == 2
        assert result.preserved_tail_turns == 1

    def test_format_notification(self):
        compactor = ContextCompactor()
        res = CompactionResult(
            original_turns=40,
            compacted_summary="Short summary",
            preserved_tail_turns=3,
            active_files=["src/main.py"],
            tokens_saved=5000,
            focus="security",
        )
        notif = compactor.format_notification(res)
        assert "40 turns" in notif
        assert "security" in notif
        assert "5000 tokens" in notif
