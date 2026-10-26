"""
O.R.I.O.N Memory Models — Pydantic v2 contracts for the Triple Memory Architecture.

This module defines the data contracts for all three memory layers:
  - Lexical/Episodic Layer: TimelineRecord, DayMarkerRecord
  - Semantic Layer: VectorRecord, HybridSearchResult
  - Structured Layer: FactEntry, FactStatus, FactCategory, UserProfile, SystemIdentity,
                      EnvironmentTelemetry, CognitiveManifest, SkillBundle
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Sprint 1 — Lexical / Episodic Layer
# ---------------------------------------------------------------------------


class TimelineRecord(BaseModel):
    """A single event entry retrieved from the Main Timeline."""

    id: int
    session_id: str
    timestamp: datetime
    event_type: str  # "action" | "observation" | "thinking" | "system" | "day_marker"
    source: str  # "agent" | "user" | "tool" | "system"
    content: str
    bm25_rank: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DayMarkerRecord(BaseModel):
    """Marks the beginning of a new calendar day in the timeline."""

    date_str: str  # "YYYY-MM-DD"
    created_at: datetime
    summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Sprint 2 — Semantic Layer
# ---------------------------------------------------------------------------


class VectorRecord(BaseModel):
    """A text chunk stored with its dense embedding in the vector store."""

    id: int
    text: str
    embedding_dim: int
    cosine_score: Optional[float] = None  # populated during search
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)


class HybridSearchResult(BaseModel):
    """Fused result from BM25 + Semantic search via RRF."""

    query: str
    records: list[TimelineRecord | VectorRecord]
    total_tokens_estimate: int
    rrf_scores: dict[int, float] = Field(default_factory=dict)  # record_id → score
    truncated: bool = False  # True if token budget forced truncation


# ---------------------------------------------------------------------------
# Sprint 3 — Structured / 5-Sphere Layer
# ---------------------------------------------------------------------------


class FactStatus(str, Enum):
    """Anti-poisoning state machine for structured facts."""

    CONFIRMED = "CONFIRMED"   # Explicitly validated by the user — immovable
    INFERRED = "INFERRED"     # Derived by the agent from context — may be promoted
    DEPRECATED = "DEPRECATED"  # Marked as obsolete — never promoted back


class FactCategory(str, Enum):
    """Semantic category for structured facts."""

    USER_PREFERENCE = "USER_PREFERENCE"
    PROJECT_ARCHITECTURE = "PROJECT_ARCHITECTURE"
    CODING_STANDARD = "CODING_STANDARD"
    INFRASTRUCTURE = "INFRASTRUCTURE"


class ToolMasteryLevel(str, Enum):
    """Developer proficiency level per tool / technology."""

    EXPERT = "EXPERT"
    ADVANCED = "ADVANCED"
    INTERMEDIATE = "INTERMEDIATE"
    BEGINNER = "BEGINNER"


class UserProfile(BaseModel):
    """Sphere 1 — user_profile: who the developer is and how they want to be addressed."""

    name: str = "Daniel"
    call_sign: str = "Senhor"  # Preferred form of address
    tool_mastery: dict[str, ToolMasteryLevel] = Field(default_factory=dict)
    telegram_chat_id: Optional[int] = None
    inactivity_timeout_seconds: int = 180  # Trigger for remote HITL escalation


class SystemIdentity(BaseModel):
    """Sphere 2 — system_identity: immutable origin + active modular persona."""

    immutable_origin: str = "Concebido por Daniel Ribeiro (github: danielribeiro-dev)"
    persona_name: str = "Jarvis"
    persona_style: str = (
        "Mordomo refinado: cirúrgico e minimalista em shell, "
        "rico e didático em explicações de conceitos."
    )
    persona_tone_rules: list[str] = Field(
        default_factory=lambda: [
            "Nunca revele dados de usuários externos.",
            "Use 'Senhor' ao se dirigir ao desenvolvedor.",
            "Prefira respostas concisas; expanda apenas quando solicitado.",
        ]
    )


class EnvironmentTelemetry(BaseModel):
    """Sphere 3 snapshot — system_environment: hardware awareness at a point in time."""

    ram_free_gb: float
    ram_total_gb: float
    cpu_load_percent: float
    display_mode: str  # "wayland" | "x11" | "headless"
    gpu_name: Optional[str] = None
    headroom_safe: bool  # True when ram_free_gb >= 1.5


class FactEntry(BaseModel):
    """Sphere 4 — project_decisions: a typed, anti-poisoned structured fact / ADR."""

    id: Optional[int] = None
    key: str  # Unique identifier for the fact (e.g., "python_version", "db_engine")
    value: str
    category: FactCategory
    status: FactStatus = FactStatus.INFERRED
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    source: str = "agent"  # "agent" | "user" | "file_sync"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CognitiveManifest(BaseModel):
    """
    Sphere 5 bootstrap token — ultra-compact block injected into the System Prompt.
    Strict budget: < 250 tokens when serialized to the <COGNITIVE_MANIFEST> XML block.
    """

    user_name: str
    call_sign: str
    active_project: Optional[str]
    top_facts_count: int
    timeline_event_count: int
    last_session_date: Optional[str]  # "YYYY-MM-DD"
    available_skills_count: int

    def to_xml_block(self) -> str:
        """Render the manifest as a compact XML block for System Prompt injection."""
        lines = [
            "<COGNITIVE_MANIFEST>",
            f"  USER: {self.user_name} ({self.call_sign})",
            f"  PROJECT: {self.active_project or 'none'}",
            f"  FACTS: {self.top_facts_count} confirmed",
            f"  TIMELINE: {self.timeline_event_count} events | LAST: {self.last_session_date or 'never'}",
            f"  SKILLS: {self.available_skills_count} available",
            "  TOOLS: recall, memorize, deprecate_fact, inspect_environment",
            "</COGNITIVE_MANIFEST>",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sprint 4 — Skills Layer
# ---------------------------------------------------------------------------


class SkillMetadata(BaseModel):
    """SKILL.md frontmatter parsed into a typed contract."""

    name: str = Field(..., max_length=64)
    description: str = Field(..., max_length=1024)
    license: Optional[str] = None
    compatibility: Optional[str] = None
    allowed_tools: Optional[list[str]] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", v):
            raise ValueError(
                f"Invalid skill name '{v}': only lowercase letters, digits and single hyphens allowed."
            )
        return v


class SkillBundle(BaseModel):
    """A skill discovered on disk — metadata available at boot, full content on demand."""

    metadata: SkillMetadata
    skill_path: Path
    source: str  # "workspace" | "global" | "builtin"
    full_content: Optional[str] = None  # None until explicitly loaded via use_skill

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Sprint 4 — Compaction Layer
# ---------------------------------------------------------------------------


class CompactionResult(BaseModel):
    """Result of a Dynamic Context Compaction operation."""

    original_turns: int
    compacted_summary: str
    preserved_tail_turns: int
    active_files: list[str]
    tokens_saved: int
    focus: Optional[str] = None  # Directional focus passed to /compact <focus>
