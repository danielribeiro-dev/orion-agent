"""Roteiros determinísticos do modelo para testar o engine (sem rede, sem custo)."""

from __future__ import annotations

import itertools
from collections.abc import Callable
from typing import Any

from orion.core.engine import ModelTurn
from orion.gateway.models import ContentBlock, LLMMessage, ToolSpec

_ids = itertools.count(1)


def say(text: str, stop_reason: str = "end_turn") -> ModelTurn:
    """Resposta só de texto."""
    return ModelTurn([ContentBlock.of_text(text)], stop_reason)


def use(tool: str, params: dict[str, Any] | None = None, text: str = "") -> ModelTurn:
    """Resposta com um único tool_use."""
    return uses((tool, params or {}), text=text)


def uses(*calls: tuple[str, dict[str, Any]], text: str = "") -> ModelTurn:
    """Resposta com vários tool_use (paralelos)."""
    blocks = [ContentBlock.of_text(text)] if text else []
    blocks += [ContentBlock.of_tool_use(f"toolu_{next(_ids)}", name, dict(params)) for name, params in calls]
    return ModelTurn(blocks, "tool_use")


class ScriptedLLM:
    """LLM que devolve os turnos do roteiro em ordem (o último se repete se ``repeat``)."""

    def __init__(self, *script: ModelTurn | Callable[[list[LLMMessage]], ModelTurn], repeat: bool = False) -> None:
        self._script = list(script)
        self._repeat = repeat
        self.systems: list[str] = []
        self.requests: list[list[LLMMessage]] = []
        self.tools: list[list[ToolSpec]] = []

    async def __call__(
        self, *, system: str, messages: list[LLMMessage], tools: list[ToolSpec]
    ) -> ModelTurn:
        self.systems.append(system)
        self.requests.append(messages)
        self.tools.append(tools)
        index = len(self.requests) - 1
        if index >= len(self._script):
            if not self._repeat:
                raise AssertionError("roteiro do LLM esgotado")
            index = len(self._script) - 1
        step = self._script[index]
        return step(messages) if callable(step) else step


def tool_results(message: LLMMessage) -> list[ContentBlock]:
    """Blocos tool_result de uma mensagem de usuário."""
    return [b for b in message.blocks if b.type == "tool_result"]


def legacy(*responses: tuple[Any, ...]) -> ScriptedLLM:
    """Converte roteiros no formato antigo (``final_answer``/``tool_call``) em turnos estruturados.

    Como o stub antigo, repete a última resposta quando o roteiro acaba.
    """
    turns: list[ModelTurn] = []
    for resp in responses:
        if resp[0] == "final_answer":
            turns.append(say(resp[1] if len(resp) > 1 else ""))
        else:
            turns.append(use(resp[1], resp[2] if len(resp) > 2 else {}))
    return ScriptedLLM(*turns, repeat=True)
