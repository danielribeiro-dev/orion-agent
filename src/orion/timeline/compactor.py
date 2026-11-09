"""
O.R.I.O.N — Dynamic Context Compactor (Sprint 4, v0.2.0)

Context Window Health & Pruning:
  - Automatic trigger: activated when context usage reaches 80% of window budget.
  - Manual slash command: `/compact` (with optional directional `focus`).
  - Reduction strategy:
      1. Preserves intact the vital tail (last 3 to 5 turns).
      2. Extracts and tracks all modified/active files across the entire session.
      3. Summarizes completed actions, rationales, and architectural decisions.
      4. Discards bulky raw tool outputs (e.g., massive read_file, logs, stack traces).
      5. Generates structured `CompactionResult` with token savings statistics.

ADR-011: Dynamic Context Compactor
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from orion.memory.models import CompactionResult

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD_PERCENT = 0.80
_DEFAULT_VITAL_TAIL_COUNT = 3
_CHARS_PER_TOKEN = 4

# Regex for common file path patterns in tool params or text
_FILE_PATH_PATTERN = re.compile(
    r'(?:path=["\']?|file=["\']?|edit_file\s+|write_file\s+)?([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)',
    re.IGNORECASE,
)


def estimate_tokens(text: str) -> int:
    """Estimate token count (approx. 4 characters per token)."""
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


@dataclass
class TurnData:
    """Normalized turn representation for context compaction."""

    turn_index: int
    user_input: str = ""
    thinking: str = ""
    tool_name: str = ""
    tool_params: dict[str, Any] = field(default_factory=dict)
    tool_output: str = ""
    modified_files: list[str] = field(default_factory=list)

    def to_full_text(self) -> str:
        """Render the complete uncompacted turn text."""
        parts = [f"--- Turn {self.turn_index} ---"]
        if self.user_input:
            parts.append(f"User: {self.user_input}")
        if self.thinking:
            parts.append(f"Thinking: {self.thinking}")
        if self.tool_name:
            parts.append(f"Action: {self.tool_name}({self.tool_params})")
        if self.tool_output:
            parts.append(f"Observation: {self.tool_output}")
        return "\n".join(parts)

    def to_compact_summary(self) -> str:
        """Render a concise summary of the turn, omitting bulky output."""
        desc = f"Turn {self.turn_index}: "
        if self.user_input:
            desc += f"Goal: {self.user_input[:80]}. "
        if self.tool_name:
            params_brief = ", ".join(f"{k}={v}" for k, v in list(self.tool_params.items())[:2])
            desc += f"Executed {self.tool_name}({params_brief}) -> "
            desc += "Success." if "error" not in self.tool_output.lower() else "Error noted."
        elif self.thinking:
            desc += f"Reasoned: {self.thinking[:100]}..."
        return desc


class ContextCompactor:
    """
    Dynamic context compactor that condenses turn histories to maintain
    context window health.
    """

    def __init__(
        self,
        threshold_percent: float = _DEFAULT_THRESHOLD_PERCENT,
        vital_tail_count: int = _DEFAULT_VITAL_TAIL_COUNT,
    ) -> None:
        self.threshold_percent = threshold_percent
        self.vital_tail_count = max(1, vital_tail_count)

    def should_compact(self, current_tokens: int, max_tokens: int) -> bool:
        """
        Check if context usage has reached or exceeded the threshold (default 80%).
        """
        if max_tokens <= 0:
            return False
        return (current_tokens / max_tokens) >= self.threshold_percent

    def compact(
        self,
        turns: Sequence[TurnData | dict[str, Any] | str],
        focus: str | None = None,
        vital_tail_count: int | None = None,
    ) -> CompactionResult:
        """
        Execute context compaction over the provided turns.

        Args:
            turns: Sequence of TurnData objects, dicts, or raw turn strings.
            focus: Optional directional focus for the compaction summary.
            vital_tail_count: Number of recent turns to preserve intact.

        Returns:
            CompactionResult with summary, active files, and token statistics.
        """
        tail_count = vital_tail_count or self.vital_tail_count
        normalized = [self._normalize_turn(t, i) for i, t in enumerate(turns)]
        total_turns = len(normalized)

        if total_turns <= tail_count:
            # History is shorter than vital tail; nothing to prune
            full_text = "\n\n".join(t.to_full_text() for t in normalized)
            estimate_tokens(full_text)
            active_files = self._extract_active_files(normalized)
            return CompactionResult(
                original_turns=total_turns,
                compacted_summary=full_text,
                preserved_tail_turns=total_turns,
                active_files=active_files,
                tokens_saved=0,
                focus=focus,
            )

        # Split into historical head and vital tail
        split_idx = total_turns - tail_count
        head_turns = normalized[:split_idx]
        tail_turns = normalized[split_idx:]

        # Calculate original uncompacted token footprint
        original_full_text = "\n\n".join(t.to_full_text() for t in normalized)
        original_tokens = estimate_tokens(original_full_text)

        # Extract active files across the entire session
        active_files = self._extract_active_files(normalized)

        # Synthesize historical head
        summary_lines = [
            f"[CONTEXT COMPACTION SUMMARY — {len(head_turns)} PRIOR TURNS CONDENSED]"
        ]
        if focus:
            summary_lines.append(f"Directional Focus: {focus}")
        if active_files:
            summary_lines.append(f"Active Files: {', '.join(active_files)}")
        summary_lines.append("Key Milestones & Executed Actions:")

        for t in head_turns:
            line = f"  - {t.to_compact_summary()}"
            if focus and focus.lower() in (t.user_input + t.thinking + t.tool_name).lower():
                line += f" [Matches focus: '{focus}']"
            summary_lines.append(line)

        # Append vital tail intact
        summary_lines.append(f"\n[VITAL TAIL — LAST {len(tail_turns)} TURNS INTACT]")
        for t in tail_turns:
            summary_lines.append(t.to_full_text())

        compacted_text = "\n".join(summary_lines)
        compacted_tokens = estimate_tokens(compacted_text)
        tokens_saved = max(0, original_tokens - compacted_tokens)

        logger.info(
            "Compaction completed: %d turns -> %d saved tokens (~%.1f%% reduction).",
            total_turns,
            tokens_saved,
            (tokens_saved / original_tokens * 100) if original_tokens else 0,
        )

        return CompactionResult(
            original_turns=total_turns,
            compacted_summary=compacted_text,
            preserved_tail_turns=len(tail_turns),
            active_files=active_files,
            tokens_saved=tokens_saved,
            focus=focus,
        )

    def format_notification(self, result: CompactionResult) -> str:
        """Format an informative notification string for the user or terminal."""
        pct = (
            (result.tokens_saved / (result.tokens_saved + estimate_tokens(result.compacted_summary)) * 100)
            if (result.tokens_saved + estimate_tokens(result.compacted_summary)) > 0
            else 0
        )
        focus_str = f" [focus: {result.focus}]" if result.focus else ""
        return (
            f"⚡ [O.R.I.O.N Compactor{focus_str}] {result.original_turns} turns compacted. "
            f"Preserved {result.preserved_tail_turns} vital turns. "
            f"Saved ~{result.tokens_saved} tokens ({pct:.1f}% reduction). "
            f"Active files: {len(result.active_files)}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize_turn(self, raw: TurnData | dict[str, Any] | str, index: int) -> TurnData:
        """Convert any turn format into a standardized TurnData instance."""
        if isinstance(raw, TurnData):
            return raw
        if isinstance(raw, dict):
            return TurnData(
                turn_index=raw.get("turn_index", index),
                user_input=raw.get("user_input", ""),
                thinking=raw.get("thinking", ""),
                tool_name=raw.get("tool_name", ""),
                tool_params=raw.get("tool_params", {}),
                tool_output=str(raw.get("tool_output", raw.get("output", ""))),
                modified_files=list(raw.get("modified_files", [])),
            )
        # raw string
        text = str(raw)
        return TurnData(
            turn_index=index,
            tool_output=text,
        )

    def _extract_active_files(self, turns: Sequence[TurnData]) -> list[str]:
        """Collect unique files referenced or modified across turns."""
        files: set[str] = set()
        for t in turns:
            files.update(t.modified_files)
            # Inspect tool params
            for k in ("path", "file_path", "target_path", "file"):
                val = t.tool_params.get(k)
                if isinstance(val, str) and val.strip():
                    files.add(val.strip())

            # Regex search in user input and outputs
            for text in (t.user_input, t.tool_output):
                for match in _FILE_PATH_PATTERN.findall(text):
                    # Filter out short or improbable paths
                    clean = match.strip("'\"")
                    if "/" in clean or clean.endswith((".py", ".md", ".json", ".toml", ".txt")):
                        files.add(clean)

        return sorted(list(files))
