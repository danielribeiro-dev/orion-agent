"""
O.R.I.O.N — Finite State Machine
Defines legal agent states and the valid transition graph.
"""

from __future__ import annotations

from enum import Enum, auto

from orion.core.errors import EngineStateError


class AgentState(str, Enum):
    """States in the ReAct engine finite state machine.

    Transition graph:
        IDLE
          └─► CONTEXT_ASSEMBLY
                └─► REASONING
                      ├─► FINAL_ANSWER          (engine produced a conclusive response)
                      └─► ACTION_PENDING
                            └─► PEP_VALIDATION
                                  ├─► EXECUTING
                                  │     ├─► VERIFYING
                                  │     │     ├─► REASONING  (next turn)
                                  │     │     └─► COMPLETED
                                  │     └─► FAILED
                                  └─► FAILED    (PEP denied)
        Any ──► FAILED            (on unrecoverable error)
        Any ──► IDLE              (after reset)
    """

    IDLE = "idle"
    CONTEXT_ASSEMBLY = "context_assembly"
    REASONING = "reasoning"
    ACTION_PENDING = "action_pending"
    PEP_VALIDATION = "pep_validation"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    FINAL_ANSWER = "final_answer"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------

_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.IDLE: {AgentState.CONTEXT_ASSEMBLY},
    AgentState.CONTEXT_ASSEMBLY: {AgentState.REASONING},
    AgentState.REASONING: {
        AgentState.ACTION_PENDING,
        AgentState.FINAL_ANSWER,
        AgentState.FAILED,
    },
    AgentState.ACTION_PENDING: {AgentState.PEP_VALIDATION, AgentState.FAILED},
    AgentState.PEP_VALIDATION: {AgentState.EXECUTING, AgentState.FAILED},
    AgentState.EXECUTING: {AgentState.VERIFYING, AgentState.FAILED},
    AgentState.VERIFYING: {AgentState.REASONING, AgentState.COMPLETED},
    AgentState.FINAL_ANSWER: {AgentState.COMPLETED},
    AgentState.COMPLETED: {AgentState.IDLE},
    AgentState.FAILED: {AgentState.IDLE},
}


class StateMachine:
    """Tracks and enforces the ReAct engine state transitions."""

    def __init__(self) -> None:
        self._state: AgentState = AgentState.IDLE

    @property
    def state(self) -> AgentState:
        return self._state

    def transition(self, to: AgentState) -> None:
        """Attempt to move to *to* state.

        Raises:
            EngineStateError: if the transition is not allowed.
        """
        allowed = _TRANSITIONS.get(self._state, set())
        if to not in allowed:
            raise EngineStateError(self._state.value, to.value)
        self._state = to

    def can_transition(self, to: AgentState) -> bool:
        """Return True if transitioning to *to* is currently valid."""
        return to in _TRANSITIONS.get(self._state, set())

    def reset(self) -> None:
        """Force-reset to IDLE (used after COMPLETED or FAILED)."""
        self._state = AgentState.IDLE

    def is_terminal(self) -> bool:
        """Return True if the machine is in a terminal state."""
        return self._state in {AgentState.COMPLETED, AgentState.FAILED}

    def __repr__(self) -> str:
        return f"StateMachine(state={self._state.value!r})"
