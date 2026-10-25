"""
O.R.I.O.N — Core ReAct Engine
Async Action-Observation loop with formal prompt delimiters, Turn Budgeting
and structured prompt injection protection.

Architecture:
    User message ──► assemble_context()
                         └──► _reasoning_turn()   ← calls LLM (or stub)
                                   ├── emits Action  ──► PEP ──► LocalRuntimeProvider
                                   │       └── returns Observation ──► next turn
                                   └── emits FinalAnswer ──► done

The engine is LLM-provider-agnostic. The _call_llm() method is a stub that
must be replaced by the Model Gateway in v0.3.0.

Sprint 3: _execute_action() is wired to LocalRuntimeProvider via the optional
          ``runtime`` constructor argument. When not provided, a synthetic
          stub Observation is returned for backwards compatibility with
          Sprint 2 tests.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from orion.core.errors import PromptInjectionSuspected, TurnBudgetExceeded
from orion.core.event_bus import EventBus
from orion.core.events import (
    Action,
    ActionEmitted,
    FinalAnswer,
    Observation,
    ObservationReceived,
    RiskLevel,
    Thinking,
    TurnCompleted,
    TurnStarted,
)
from orion.core.state import AgentState, StateMachine
from orion.runtime.provider import BaseRuntimeProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Formal prompt delimiters (anti-injection)
# ---------------------------------------------------------------------------

DELIM_SYSTEM_START = "<<<ORION_SYSTEM_START>>>"
DELIM_SYSTEM_END = "<<<ORION_SYSTEM_END>>>"
DELIM_CONTEXT_START = "<<<ORION_CONTEXT_START>>>"
DELIM_CONTEXT_END = "<<<ORION_CONTEXT_END>>>"
DELIM_USER_START = "<<<ORION_USER_START>>>"
DELIM_USER_END = "<<<ORION_USER_END>>>"
DELIM_TOOL_START = "<<<ORION_TOOL_OUTPUT_START>>>"
DELIM_TOOL_END = "<<<ORION_TOOL_OUTPUT_END>>>"

# Patterns that suggest a prompt-injection attempt in user input
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<<<ORION_SYSTEM", re.IGNORECASE),
    re.compile(r"<<<ORION_CONTEXT", re.IGNORECASE),
    re.compile(r"<<<ORION_TOOL_OUTPUT", re.IGNORECASE),
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?prior", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# LLM response type (simplified — will be expanded in v0.3.0 Model Gateway)
# ---------------------------------------------------------------------------

# The engine expects the LLM callable to return one of:
#   - ("final_answer", str)           → engine produces FinalAnswer
#   - ("tool_call", tool_name, params) → engine produces Action
LLMResponse = tuple[str, ...]

LLMCallable = Callable[
    [str],  # assembled prompt
    Coroutine[Any, Any, LLMResponse],
]

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ReActEngine:
    """Async ReAct engine implementing the Action-Observation Event Stream.

    Args:
        event_bus:  Shared EventBus instance.
        llm:        Async callable that receives a prompt and returns an LLMResponse.
                    In Sprint 2 this is a test stub; the real gateway plugs in at v0.3.0.
        max_turns:  Maximum reasoning turns. Engine halts and raises TurnBudgetExceeded
                    if exceeded.
        session_id: Unique identifier for this run. Auto-generated if omitted.
        runtime:    Optional BaseRuntimeProvider. When provided, tool calls are
                    dispatched to it (Sprint 3+). When None, a synthetic stub
                    Observation is returned for backwards compatibility.
    """

    def __init__(
        self,
        event_bus: EventBus,
        llm: LLMCallable,
        max_turns: int = 20,
        session_id: str | None = None,
        runtime: BaseRuntimeProvider | None = None,
    ) -> None:
        self._bus = event_bus
        self._llm = llm
        self._max_turns = max_turns
        self._session_id = session_id or str(uuid.uuid4())
        self._fsm = StateMachine()
        self._runtime = runtime

        # Accumulated observations to append to context in subsequent turns
        self._observations: list[Observation] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def state(self) -> AgentState:
        return self._fsm.state

    @property
    def max_turns(self) -> int:
        return self._max_turns

    async def run(self, user_message: str) -> str:
        """Execute a full ReAct session for *user_message*.

        Returns:
            The final answer string.

        Raises:
            TurnBudgetExceeded: if max_turns is hit without a FinalAnswer.
            PromptInjectionSuspected: if the user input fails sanitisation.
        """
        self._sanitize_input(user_message)
        self._observations.clear()

        # IDLE → CONTEXT_ASSEMBLY
        self._fsm.transition(AgentState.CONTEXT_ASSEMBLY)

        final_answer: str | None = None

        for turn_index in range(self._max_turns):
            await self._bus.publish(
                TurnStarted(
                    turn_index=turn_index,
                    session_id=self._session_id,
                    user_message=user_message,
                )
            )

            # CONTEXT_ASSEMBLY / VERIFYING → REASONING
            if self._fsm.can_transition(AgentState.REASONING):
                self._fsm.transition(AgentState.REASONING)

            # Build prompt and call LLM
            prompt = self._assemble_prompt(user_message, turn_index)
            llm_response = await self._llm(prompt)

            # Parse response
            kind = llm_response[0]

            if kind == "final_answer":
                # ── Produce FinalAnswer ──────────────────────────────────
                answer_text = llm_response[1] if len(llm_response) > 1 else ""

                await self._bus.publish(
                    Thinking(
                        turn_index=turn_index,
                        content=f"[final] {answer_text[:200]}",
                    )
                )

                self._fsm.transition(AgentState.FINAL_ANSWER)

                final_event = FinalAnswer(
                    turn_index=turn_index,
                    session_id=self._session_id,
                    content=answer_text,
                )
                await self._bus.publish(final_event)

                self._fsm.transition(AgentState.COMPLETED)

                await self._bus.publish(
                    TurnCompleted(
                        session_id=self._session_id,
                        total_turns=turn_index + 1,
                        success=True,
                        final_answer=answer_text,
                    )
                )

                final_answer = answer_text
                break

            elif kind == "tool_call":
                # ── Emit Action and await Observation ───────────────────
                tool_name = llm_response[1] if len(llm_response) > 1 else "unknown"
                params: dict[str, Any] = (
                    llm_response[2] if len(llm_response) > 2 else {}  # type: ignore[assignment]
                )
                risk_raw = llm_response[3] if len(llm_response) > 3 else RiskLevel.SAFE
                risk = RiskLevel(risk_raw) if isinstance(risk_raw, int) else risk_raw
                reasoning_text = llm_response[4] if len(llm_response) > 4 else None

                await self._bus.publish(
                    Thinking(
                        turn_index=turn_index,
                        content=f"[tool_call] {tool_name}({params})",
                    )
                )

                action = Action(
                    tool=tool_name,
                    params=params,
                    risk_level=risk,
                    turn_index=turn_index,
                    reasoning=reasoning_text,  # type: ignore[arg-type]
                )

                self._fsm.transition(AgentState.ACTION_PENDING)

                await self._bus.publish(
                    ActionEmitted(
                        turn_index=turn_index,
                        action_id=action.event_id,
                        tool=tool_name,
                        risk_level=risk,
                    )
                )

                # PEP_VALIDATION + EXECUTING (wired to runtime in Sprint 3)
                self._fsm.transition(AgentState.PEP_VALIDATION)
                self._fsm.transition(AgentState.EXECUTING)

                observation = await self._execute_action(action)

                self._fsm.transition(AgentState.VERIFYING)

                await self._bus.publish(
                    ObservationReceived(
                        turn_index=turn_index,
                        action_id=action.event_id,
                        success=observation.success,
                    )
                )

                self._observations.append(observation)
                await self._bus.publish(observation)

            else:
                # Unknown response kind — treat as failed turn
                logger.warning("ReActEngine: unknown LLM response kind %r", kind)

        else:
            # Loop exhausted without a FinalAnswer
            await self._bus.publish(
                TurnCompleted(
                    session_id=self._session_id,
                    total_turns=self._max_turns,
                    success=False,
                    error=f"Turn budget exceeded after {self._max_turns} turns.",
                )
            )
            self._fsm.reset()
            raise TurnBudgetExceeded(self._max_turns)

        self._fsm.reset()
        return final_answer or ""

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    def _assemble_prompt(self, user_message: str, turn_index: int) -> str:
        """Build the delimited prompt string for the LLM.

        Sections:
            SYSTEM   — static agent identity and rules.
            CONTEXT  — prior observation history (tool outputs).
            USER     — sanitized user request.
        """
        system_block = (
            f"{DELIM_SYSTEM_START}\n"
            "You are O.R.I.O.N, a Personal Operating Intelligence assistant.\n"
            "Rules:\n"
            "  1. Think step-by-step before acting.\n"
            "  2. Prefer targeted tool calls over broad ones.\n"
            "  3. Never produce harmful, deceptive or policy-violating outputs.\n"
            "  4. Always verify tool results before declaring completion.\n"
            f"  5. You have {self._max_turns - turn_index} turns remaining.\n"
            f"{DELIM_SYSTEM_END}"
        )

        context_parts: list[str] = []
        for obs in self._observations:
            status = "SUCCESS" if obs.success else "ERROR"
            context_parts.append(
                f"{DELIM_TOOL_START}\n"
                f"action_id={obs.action_id} status={status}\n"
                f"{obs.output}\n"
                f"{DELIM_TOOL_END}"
            )

        context_block = ""
        if context_parts:
            context_block = (
                f"\n{DELIM_CONTEXT_START}\n"
                + "\n".join(context_parts)
                + f"\n{DELIM_CONTEXT_END}"
            )

        user_block = (
            f"\n{DELIM_USER_START}\n"
            f"{user_message}\n"
            f"{DELIM_USER_END}"
        )

        return system_block + context_block + user_block

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_input(text: str) -> None:
        """Raise PromptInjectionSuspected if *text* matches known injection patterns."""
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                raise PromptInjectionSuspected(pattern.pattern)

    # ------------------------------------------------------------------
    # Action execution — wired to LocalRuntimeProvider in Sprint 3
    # ------------------------------------------------------------------

    async def _execute_action(self, action: Action) -> Observation:
        """Dispatch *action* to the runtime provider (if wired) or return a stub.

        When ``self._runtime`` is set (Sprint 3+), the LocalRuntimeProvider
        executes the tool through the PEP and returns a real result.
        When ``self._runtime`` is None, a synthetic stub Observation is returned
        to preserve full backward-compatibility with Sprint 2 tests.
        """
        if self._runtime is not None and self._runtime.supports(action.tool):
            result = await self._runtime.execute(action.tool, dict(action.params))
            return Observation(
                action_id=action.event_id,
                success=result.success,
                output=result.output if result.success else result.error,
                error=result.error,
                metadata=result.metadata,
            )

        # Stub path (Sprint 2 compatibility / unsupported tools)
        return Observation(
            action_id=action.event_id,
            success=True,
            output=f"[stub] executed {action.tool} with params {action.params}",
        )
