"""
O.R.I.O.N — Tools: session_branch e session_switch (v0.5.3 Sprint 3, ADR-051)

``session_branch`` abre uma thread a partir da conversa atual quando um tópico se sustenta
(contexto mínimo: últimos 2 turnos + resumo), liga-a à daily e passa a conversa para ela ao
fim do turno. ``session_switch`` volta para uma sessão pelo nome, id ou data.

Faixa: Livre (só organiza o transcript do ORION; nada no sistema muda). ActionLevel: LEVEL_0.
Nunca entregues a subagents.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool

#: ``async (title, reason) -> mensagem``; levanta ``ValueError`` com o motivo da recusa.
Brancher = Callable[[str, str], Awaitable[str]]
#: ``async (query) -> mensagem``; levanta ``LookupError``/``ValueError`` quando não acha.
Switcher = Callable[[str], Awaitable[str]]


class SessionBranchTool(BaseTool):
    name = "session_branch"
    description = (
        "Open a new thread (a separate, titled session) for a topic that is turning into its own "
        "line of work, so the current conversation (often the daily) stays clean. The thread starts "
        "with the last 2 turns plus a short summary, is linked to today's daily, and becomes the "
        "active session when this turn ends. Use it when the Senhor sustains a distinct topic for "
        "several turns or asks to separate it; do not use it for one-off questions."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short title in Portuguese (up to 60 characters)."},
            "reason": {"type": "string", "description": "Why this topic deserves its own thread (one line)."},
        },
        "required": ["title", "reason"],
    }

    def __init__(self, branch: Brancher | None = None) -> None:
        self._branch = branch

    async def run(self, title: str = "", reason: str = "", **_: Any) -> RuntimeResult:
        if self._branch is None:
            return RuntimeResult.fail("session_branch: not available in this session.")
        if not title.strip():
            return RuntimeResult.fail("session_branch: title is required.")
        try:
            return RuntimeResult.ok(await self._branch(title.strip(), reason.strip()))
        except (ValueError, LookupError) as exc:
            return RuntimeResult.fail(f"session_branch: {exc}")


class SessionSwitchTool(BaseTool):
    name = "session_switch"
    description = (
        "Switch the conversation to another saved session (a thread or a daily) found by title "
        "words, id prefix or date filters such as 'hoje', 'ontem', 'semana', 'nov', '2026-11', "
        "'16/11', 'daily', 'thread'. The switch happens when this turn ends. Use it when the "
        "Senhor asks to go back to an earlier subject or session."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Title words, id prefix and/or date filters."},
        },
        "required": ["query"],
    }

    def __init__(self, switch: Switcher | None = None) -> None:
        self._switch = switch

    async def run(self, query: str = "", **_: Any) -> RuntimeResult:
        if self._switch is None:
            return RuntimeResult.fail("session_switch: not available in this session.")
        if not query.strip():
            return RuntimeResult.fail("session_switch: query is required.")
        try:
            return RuntimeResult.ok(await self._switch(query.strip()))
        except (ValueError, LookupError) as exc:
            return RuntimeResult.fail(f"session_switch: {exc}")
