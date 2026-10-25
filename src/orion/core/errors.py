"""
O.R.I.O.N — Domain Exception Hierarchy
Typed domain errors for every subsystem layer.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class OrionError(Exception):
    """Root of all ORION domain exceptions."""


# ---------------------------------------------------------------------------
# Engine / Turn Budgeting
# ---------------------------------------------------------------------------


class TurnBudgetExceeded(OrionError):
    """Raised when the ReAct engine hits max_turns without completing."""

    def __init__(self, max_turns: int) -> None:
        super().__init__(
            f"Turn budget exceeded: engine reached {max_turns} turns without "
            "producing a final answer. Halting to request user guidance."
        )
        self.max_turns = max_turns


class EngineStateError(OrionError):
    """Raised when the engine attempts an illegal state transition."""

    def __init__(self, from_state: str, to_state: str) -> None:
        super().__init__(
            f"Illegal state transition: {from_state!r} → {to_state!r}"
        )
        self.from_state = from_state
        self.to_state = to_state


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class EventBusError(OrionError):
    """Base for EventBus failures."""


class HandlerNotFoundError(EventBusError):
    """Raised when trying to unsubscribe a handler that was never registered."""

    def __init__(self, event_type: str) -> None:
        super().__init__(f"No handler registered for event type {event_type!r}")
        self.event_type = event_type


# ---------------------------------------------------------------------------
# Prompt / Security
# ---------------------------------------------------------------------------


class PromptInjectionSuspected(OrionError):
    """Raised when the prompt sanitizer detects a potential injection attempt."""

    def __init__(self, pattern: str) -> None:
        super().__init__(
            f"Potential prompt injection detected — pattern: {pattern!r}. "
            "Input has been rejected."
        )
        self.pattern = pattern


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


class ArtifactError(OrionError):
    """Base for ArtifactStore failures."""


class ArtifactNotFoundError(ArtifactError):
    """Raised when an artifact ID cannot be located in the store."""

    def __init__(self, artifact_id: str) -> None:
        super().__init__(f"Artifact not found: {artifact_id!r}")
        self.artifact_id = artifact_id


class ArtifactWriteError(ArtifactError):
    """Raised when writing an artifact to disk fails."""


# ---------------------------------------------------------------------------
# Governance / PEP (forward refs — full impl in Sprint 3)
# ---------------------------------------------------------------------------


class PEPDeniedError(OrionError):
    """Raised when the Policy Enforcement Point blocks an action."""

    def __init__(self, action: str, reason: str) -> None:
        super().__init__(f"PEP denied action {action!r}: {reason}")
        self.action = action
        self.reason = reason
