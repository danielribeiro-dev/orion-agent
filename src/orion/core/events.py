"""
O.R.I.O.N — Action-Observation Event Stream Models
Immutable Pydantic v2 typed events for the ReAct cognitive loop.

Design: Every state change in the engine is represented as an immutable event.
Events are published to the EventBus and permanently recorded in the turn history.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Risk level (used by Action before PEP validation in Sprint 3)
# ---------------------------------------------------------------------------


class RiskLevel(IntEnum):
    """Maps to PEP LEVEL_0 through LEVEL_3.

    SAFE        (0) — Pure reads; no side-effects (read_file, search_files).
    CONTROLLED  (1) — Writes inside workspace scope (write_file, edit_file).
    ELEVATED    (2) — Potentially destructive or irreversible operations.
    CRITICAL    (3) — System-wide / network / destructive shell commands.
    """

    SAFE = 0
    CONTROLLED = 1
    ELEVATED = 2
    CRITICAL = 3


# ---------------------------------------------------------------------------
# Core immutable event base
# ---------------------------------------------------------------------------


class OrionEvent(BaseModel):
    """Base for all ORION events. Frozen and timestamped at creation."""

    model_config = {"frozen": True}

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Action — intent emitted by the engine to the runtime
# ---------------------------------------------------------------------------


class Action(OrionEvent):
    """Represents a tool invocation intent produced by the ReAct engine.

    The engine emits an Action; the PEP validates it; the LocalRuntimeProvider
    executes it and returns an Observation.
    """

    tool: str = Field(description="Name of the primitive tool to invoke.")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool parameters as a key-value mapping.",
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.SAFE,
        description="Estimated risk level, used by PEP for gate selection.",
    )
    turn_index: int = Field(
        default=0,
        description="Turn number within the current engine session.",
    )
    reasoning: str | None = Field(
        default=None,
        description="The engine's stated rationale for this action (from <thinking>).",
    )


# ---------------------------------------------------------------------------
# Observation — result returned from the runtime to the engine
# ---------------------------------------------------------------------------


class Observation(OrionEvent):
    """Represents the outcome of an Action execution.

    Published by the runtime layer after executing a tool.
    The engine reads this to decide its next step.
    """

    action_id: str = Field(description="ID of the Action this observation responds to.")
    success: bool = Field(description="True if the tool executed without error.")
    output: str = Field(
        default="",
        description="Raw tool output (stdout, file contents, search results, etc.).",
    )
    error: str | None = Field(
        default=None,
        description="Error message if success=False.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured metadata (exit_code, path, line_count, etc.).",
    )


# ---------------------------------------------------------------------------
# Lifecycle events — for observability and debugging
# ---------------------------------------------------------------------------


class TurnStarted(OrionEvent):
    """Published at the beginning of each ReAct turn."""

    turn_index: int
    session_id: str
    user_message: str


class Thinking(OrionEvent):
    """Published when the engine enters its internal reasoning phase."""

    turn_index: int
    content: str = Field(description="Raw reasoning / chain-of-thought text.")


class ActionEmitted(OrionEvent):
    """Published when the engine decides to call a tool."""

    turn_index: int
    action_id: str
    tool: str
    risk_level: RiskLevel


class ObservationReceived(OrionEvent):
    """Published when the runtime returns an Observation to the engine."""

    turn_index: int
    action_id: str
    success: bool


class FinalAnswer(OrionEvent):
    """Published when the engine produces a conclusive response to the user."""

    turn_index: int
    session_id: str
    content: str


class TurnCompleted(OrionEvent):
    """Published at the end of a full engine session (success or budget exceeded)."""

    session_id: str
    total_turns: int
    success: bool
    final_answer: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Union type for type-narrowing in handlers
# ---------------------------------------------------------------------------

AnyEvent = (
    Action
    | Observation
    | TurnStarted
    | Thinking
    | ActionEmitted
    | ObservationReceived
    | FinalAnswer
    | TurnCompleted
)
