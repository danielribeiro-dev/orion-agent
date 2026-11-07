"""
O.R.I.O.N — Tool: ask_user
Faz uma pergunta objetiva ao Senhor (modal na TUI) quando falta uma decisão que só ele pode tomar.

ActionLevel: LEVEL_0 (apenas coleta resposta; nenhum efeito no sistema)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool

#: ``async (question, options, multi_select) -> list[str] | None`` (None = sem resposta/cancelado)
Asker = Callable[[str, list[dict[str, str]], bool], Awaitable[list[str] | None]]


class AskUserTool(BaseTool):
    name = "ask_user"
    description = (
        "Ask the user a question and wait for the answer. Offer 2-4 'options' (label + short "
        "description) when the choices are known; the user can always type a custom answer. "
        "Use only for decisions you cannot resolve from the code or request."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "minLength": 3},
            "options": {
                "type": "array",
                "minItems": 2,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "minLength": 1},
                        "description": {"type": "string"},
                    },
                    "required": ["label"],
                },
            },
            "multi_select": {"type": "boolean"},
        },
        "required": ["question"],
    }
    read_only = True

    def __init__(self, asker: Asker | None = None) -> None:
        self._asker = asker

    async def run(
        self,
        question: str,
        options: list[dict[str, str]] | None = None,
        multi_select: bool = False,
        **_: Any,
    ) -> RuntimeResult:
        if self._asker is None:
            return RuntimeResult.fail("ask_user: no interactive channel is available.")
        answer = await self._asker(question, options or [], multi_select)
        if not answer:
            return RuntimeResult.fail("ask_user: the user did not answer. Proceed with a safe default or stop.")
        return RuntimeResult.ok(f"User answered: {'; '.join(answer)}", answers=answer)
