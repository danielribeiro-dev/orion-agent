"""
O.R.I.O.N — Formato OpenAI/Ollama para tool calling (v0.5.0 Sprint 3, ADR-021)

Tradução entre os content blocks neutros (``tool_use``/``tool_result``) e o formato
de chat das APIs OpenAI-compatíveis (OpenRouter) e do Ollama. Compartilhado pelos
providers legados para que o failover preserve tools e histórico estruturado.

  - ``serialize_messages``: histórico estruturado -> mensagens da API
  - ``tools_to_openai`` / ``tool_choice_to_openai``: schemas e política de escolha
  - ``ToolCallAssembler``: monta ``tool_use`` a partir de ``delta.tool_calls`` em stream
  - ``map_finish_reason``: ``finish_reason`` da API -> ``stop_reason`` neutro
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from orion.gateway.models import (
    ContentBlock,
    LLMMessage,
    MessageRole,
    ToolChoice,
    ToolSpec,
    flatten_content,
)

INVALID_ARGS_KEY = "__invalid_json__"
"""Chave sentinela: argumentos que não são JSON válido (a validação de schema do runtime os recusa)."""

_FINISH_REASONS = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}


def map_finish_reason(reason: str | None, has_tool_calls: bool = False) -> str | None:
    """``finish_reason`` OpenAI -> ``stop_reason`` neutro. Tool calls pendentes sempre vencem."""
    if reason is None:
        return None
    if has_tool_calls and reason in ("stop", "tool_calls", "function_call"):
        return "tool_use"
    return _FINISH_REASONS.get(reason, reason)


def tools_to_openai(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """``ToolSpec`` -> ``tools`` do formato OpenAI (também aceito pelo Ollama)."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]


def tool_choice_to_openai(choice: ToolChoice | None) -> str | dict[str, Any] | None:
    """``ToolChoice`` -> ``tool_choice`` OpenAI; ``None`` deixa o padrão do provider (auto)."""
    if choice is None:
        return None
    if choice.type == "auto":
        return "auto"
    if choice.type == "any":
        return "required"
    if choice.type == "none":
        return "none"
    return {"type": "function", "function": {"name": choice.name}}


def _tool_result_text(block: ContentBlock) -> str:
    inner = block.content
    if isinstance(inner, str):
        return inner
    return flatten_content(inner or [])


def serialize_messages(
    messages: list[LLMMessage], *, ollama: bool = False, with_tools: bool = True
) -> list[dict[str, Any]]:
    """Histórico estruturado -> mensagens do chat.

    - ``thinking``/``redacted_thinking`` são descartados (assinaturas só valem na Anthropic).
    - ``tool_use`` do assistente vira ``tool_calls``; ``tool_result`` vira mensagem ``role=tool``
      (emitida antes de qualquer texto do mesmo turno de usuário, como a API exige).
    - ``with_tools=False`` (modelo sem suporte a tools) achata tudo para texto.
    - ``ollama=True``: ``arguments`` como objeto e ``tool_name`` nos resultados.
    """
    if not with_tools:
        return [{"role": m.role.value, "content": m.text} for m in messages]

    names: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == MessageRole.ASSISTANT:
            text = "".join(b.text or "" for b in msg.blocks if b.type == "text")
            calls: list[dict[str, Any]] = []
            for b in msg.blocks:
                if b.type != "tool_use":
                    continue
                call_id, name = b.id or "", b.name or ""
                names[call_id] = name
                args: Any = b.input or {}
                function = {"name": name, "arguments": args if ollama else json.dumps(args)}
                call: dict[str, Any] = {"function": function}
                if not ollama:
                    call = {"id": call_id, "type": "function", "function": function}
                calls.append(call)
            if not text and not calls:
                continue
            entry: dict[str, Any] = {"role": "assistant", "content": text}
            if calls:
                entry["tool_calls"] = calls
                if not text and not ollama:
                    entry["content"] = None
            out.append(entry)
        elif msg.role == MessageRole.USER:
            blocks = msg.blocks
            for b in blocks:
                if b.type != "tool_result":
                    continue
                result: dict[str, Any] = {"role": "tool", "content": _tool_result_text(b)}
                if ollama:
                    result["tool_name"] = names.get(b.tool_use_id or "", "")
                else:
                    result["tool_call_id"] = b.tool_use_id
                out.append(result)
            rest = [b for b in blocks if b.type != "tool_result"]
            if rest:
                out.append({"role": "user", "content": flatten_content(rest)})
        else:
            entry = {"role": msg.role.value, "content": msg.text}
            if msg.name is not None:
                entry["name"] = msg.name
            out.append(entry)
    return out


def parse_arguments(raw: Any) -> dict[str, Any]:
    """Argumentos de tool call (string JSON ou objeto) -> dict; inválido vira o sentinela."""
    if isinstance(raw, dict):
        return raw
    if raw is None or raw == "":
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {INVALID_ARGS_KEY: str(raw)[:500]}
    if isinstance(parsed, dict):
        return parsed
    return {INVALID_ARGS_KEY: str(raw)[:500]}


def new_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:24]}"


class ToolCallAssembler:
    """Acumula ``delta.tool_calls`` fragmentados (por ``index``) e devolve blocos ``tool_use``."""

    def __init__(self) -> None:
        self._calls: dict[int, dict[str, str]] = {}

    def __bool__(self) -> bool:
        return bool(self._calls)

    def feed(self, tool_calls: list[dict[str, Any]] | None) -> None:
        for position, call in enumerate(tool_calls or []):
            index = call.get("index", position)
            slot = self._calls.setdefault(int(index), {"id": "", "name": "", "arguments": ""})
            if call.get("id"):
                slot["id"] = str(call["id"])
            function = call.get("function") or {}
            if function.get("name"):
                slot["name"] += str(function["name"])
            if function.get("arguments"):
                slot["arguments"] += str(function["arguments"])

    def finish(self) -> list[ContentBlock]:
        """Blocos ``tool_use`` na ordem dos índices; esvazia o acumulador."""
        blocks = [
            ContentBlock.of_tool_use(
                slot["id"] or new_call_id(), slot["name"], parse_arguments(slot["arguments"])
            )
            for _, slot in sorted(self._calls.items())
            if slot["name"]
        ]
        self._calls.clear()
        return blocks


def blocks_from_ollama_calls(tool_calls: list[dict[str, Any]]) -> list[ContentBlock]:
    """``message.tool_calls`` do Ollama (chegam completos) -> blocos ``tool_use``."""
    blocks: list[ContentBlock] = []
    for call in tool_calls:
        function = call.get("function") or {}
        name = str(function.get("name") or "")
        if not name:
            continue
        blocks.append(
            ContentBlock.of_tool_use(
                str(call.get("id") or new_call_id()), name, parse_arguments(function.get("arguments"))
            )
        )
    return blocks
