"""Provider roteirizado do laboratório: streaming com cadência realista, sem rede e sem custo.

Cada roteiro casa por palavra-chave na última mensagem de texto do usuário. Um roteiro tem passos:
o passo N responde depois de N resultados de ferramenta (permite ler, editar e rodar em sequência).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orion.gateway.models import (
    ContentBlock,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
    TokenUsage,
)
from orion.gateway.providers.base import BaseLLMProvider


@dataclass
class Step:
    """Uma resposta do "modelo"."""

    text: str = ""
    reasoning: str = ""
    tools: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    stall_after: float | None = None  # fração do texto em que o stream pausa
    stall_seconds: float = 0.0
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Step:
        tools = [(str(name), dict(params)) for name, params in data.get("tools", [])]
        return cls(
            text=str(data.get("text", "")),
            reasoning=str(data.get("reasoning", "")),
            tools=tools,
            stall_after=data.get("stall_after"),
            stall_seconds=float(data.get("stall_seconds", 0.0)),
            error=data.get("error"),
        )


@dataclass
class Script:
    match: str
    steps: list[Step]


@dataclass
class ScriptBook:
    """Conjunto de roteiros carregado de JSON (o launcher roda em outro processo)."""

    scripts: list[Script]
    default: Step = field(default_factory=lambda: Step(text="pong"))
    chunk: int = 6
    delay: float = 0.03

    @classmethod
    def load(cls, path: Path) -> ScriptBook:
        data = json.loads(path.read_text(encoding="utf-8"))
        scripts = [
            Script(match=str(item["match"]).lower(), steps=[Step.from_dict(s) for s in item["steps"]])
            for item in data.get("scripts", [])
        ]
        default = Step.from_dict(data["default"]) if "default" in data else Step(text="pong")
        return cls(scripts, default, int(data.get("chunk", 6)), float(data.get("delay", 0.03)))

    @staticmethod
    def dump(path: Path, scripts: dict[str, list[dict[str, Any]]], **options: Any) -> None:
        payload = {"scripts": [{"match": k, "steps": v} for k, v in scripts.items()], **options}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def pick(self, request: LLMRequest) -> Step:
        text = last_user_text(request.messages).lower()
        stage = tool_stage(request.messages)
        for script in self.scripts:
            if script.match in text:
                return script.steps[min(stage, len(script.steps) - 1)]
        return self.default


def _text_of(message: LLMMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return " ".join(block.text or "" for block in content if block.type == "text")


def last_user_text(messages: list[LLMMessage]) -> str:
    for message in reversed(messages):
        if message.role.value == "user" and _text_of(message).strip():
            return _text_of(message)
    return ""


def tool_stage(messages: list[LLMMessage]) -> int:
    """Quantos resultados de ferramenta vieram depois do último pedido em texto."""
    stage = 0
    for message in reversed(messages):
        content = message.content
        if not isinstance(content, str) and any(b.type == "tool_result" for b in content):
            stage += 1
        elif message.role.value == "user":
            break
    return stage


class ScriptedProvider(BaseLLMProvider):
    """Provider de teste: streaming com cadência. Nunca faz rede."""

    def __init__(self, book: ScriptBook) -> None:
        self.book = book
        self.calls = 0

    @property
    def provider_name(self) -> str:
        return "scripted"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError("ScriptedProvider só suporta stream()")

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:  # type: ignore[override]
        self.calls += 1
        step = self.book.pick(request)
        chunk, delay = self.book.chunk, self.book.delay
        if step.error:
            await asyncio.sleep(0.2)
            raise RuntimeError(step.error)
        for i in range(0, len(step.reasoning), chunk):
            yield LLMResponseChunk(reasoning_delta=step.reasoning[i : i + chunk])
            await asyncio.sleep(delay)
        stall_at = int(len(step.text) * step.stall_after) if step.stall_after is not None else -1
        stalled = False
        for i in range(0, len(step.text), chunk):
            if not stalled and stall_at >= 0 and i >= stall_at:
                stalled = True
                await asyncio.sleep(step.stall_seconds)
            yield LLMResponseChunk(delta=step.text[i : i + chunk])
            await asyncio.sleep(delay)
        if step.text:
            yield LLMResponseChunk(block=ContentBlock.of_text(step.text))
        for n, (name, params) in enumerate(step.tools, 1):
            yield LLMResponseChunk(
                block=ContentBlock.of_tool_use(f"toolu_lab_{self.calls}_{n}", name, params)
            )
        yield LLMResponseChunk(
            is_final=True,
            stop_reason="tool_use" if step.tools else "end_turn",
            usage=TokenUsage(prompt_tokens=1200, completion_tokens=max(1, len(step.text) // 4)),
        )
