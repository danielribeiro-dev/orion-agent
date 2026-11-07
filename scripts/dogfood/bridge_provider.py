"""
Provider-ponte do harness de dogfooding.

Em vez de chamar uma API, cada requisição do ORION é gravada em disco e o provider espera uma
resposta escrita por outro processo (o Claude Code, via ``ctl.py reply``). O ORION continua
executando tudo de verdade: tools, PEP, TUI, sessão, contexto. Só o "modelo" é substituído.

Protocolo (diretório da ponte):
    system.txt / tools.txt     system prompt e tools atuais (reescritos só quando mudam)
    req-NNNN.txt / .json       delta legível das mensagens novas / requisição completa
    res-NNNN.json              resposta: {"text": str, "tools": [{"name", "input"}], "error": str?}
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from orion.gateway.models import (
    ContentBlock,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
    ProviderName,
    TokenUsage,
)
from orion.gateway.providers.base import BaseLLMProvider

CHUNK = 24


def render_block(block: ContentBlock) -> str:
    if block.type == "text":
        return block.text or ""
    if block.type == "tool_use":
        return f"[tool_use {block.name} {json.dumps(block.input, ensure_ascii=False)}]"
    if block.type == "tool_result":
        inner = block.content
        if isinstance(inner, list):
            inner = "\n".join(render_block(b) for b in inner)
        flag = " ERROR" if block.is_error else ""
        return f"[tool_result{flag} {block.tool_use_id}]\n{inner}"
    if block.type == "image":
        data = (block.source or {}).get("data", "")
        return f"[image {(block.source or {}).get('media_type')} ~{len(data) * 3 // 4} bytes]"
    if block.type in ("thinking", "redacted_thinking"):
        return "[thinking omitted]"
    return f"[{block.type}]"


def render_message(message: LLMMessage) -> str:
    content = message.content
    body = content if isinstance(content, str) else "\n".join(render_block(b) for b in content)
    return f"--- {message.role.value} ---\n{body}"


class BridgeProvider(BaseLLMProvider):
    def __init__(self, bridge_dir: Path, poll: float = 0.2) -> None:
        self.dir = bridge_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._poll = poll
        self._seen = 0
        self._counter = max(
            (int(p.stem.split("-")[1]) for p in self.dir.glob("req-*.json")), default=0
        )

    @property
    def provider_name(self) -> str:
        return "bridge"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError("BridgeProvider só suporta stream()")

    def _write_if_changed(self, name: str, text: str) -> None:
        path = self.dir / name
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")

    def _publish(self, request: LLMRequest, n: int) -> None:
        system = ""
        if request.system:
            system = "\n".join(b.text or "" for b in request.system)
        messages = list(request.messages)
        if messages and messages[0].role.value == "system":  # provider legado: system na lista
            system = messages[0].content if isinstance(messages[0].content, str) else system
            messages = messages[1:]
        self._write_if_changed("system.txt", system)
        tools = "\n\n".join(
            f"## {t.name}\n{t.description}\n{json.dumps(t.input_schema, ensure_ascii=False)}"
            for t in request.tools or []
        )
        self._write_if_changed("tools.txt", tools)
        fresh = messages[self._seen :] if len(messages) >= self._seen else messages
        self._seen = len(messages)
        kind = "summary" if not request.tools else "turn"
        header = f"# req {n:04d} · {kind} · model={request.model} · msgs={len(messages)} (novas={len(fresh)})\n"
        (self.dir / f"req-{n:04d}.txt").write_text(
            header + "\n\n".join(render_message(m) for m in fresh) + "\n", encoding="utf-8"
        )
        full: dict[str, Any] = {
            "n": n, "kind": kind, "model": request.model, "max_tokens": request.max_tokens,
            "tools": [t.name for t in request.tools or []],
            "messages": [m.model_dump(mode="json") for m in messages],
        }
        # O .json é o sinal de "requisição pronta": escrito por último e de forma atômica.
        tmp = self.dir / f"req-{n:04d}.json.tmp"
        tmp.write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.dir / f"req-{n:04d}.json")

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:  # type: ignore[override]
        self._counter += 1
        n = self._counter
        self._publish(request, n)
        res_path = self.dir / f"res-{n:04d}.json"
        while not res_path.exists():
            await asyncio.sleep(self._poll)
        await asyncio.sleep(0.05)  # evita ler arquivo ainda em escrita
        reply = json.loads(res_path.read_text(encoding="utf-8"))
        if reply.get("error"):
            raise RuntimeError(str(reply["error"]))

        text = str(reply.get("text") or "")
        tools = reply.get("tools") or []
        for start in range(0, len(text), CHUNK):
            yield LLMResponseChunk(delta=text[start : start + CHUNK])
            await asyncio.sleep(0)
        if text:
            yield LLMResponseChunk(block=ContentBlock.of_text(text))
        for i, call in enumerate(tools, 1):
            yield LLMResponseChunk(
                block=ContentBlock.of_tool_use(f"toolu_bridge_{n}_{i}", call["name"], dict(call.get("input") or {}))
            )
        prompt = len(json.dumps(full_len(request))) // 4
        yield LLMResponseChunk(
            is_final=True,
            stop_reason=reply.get("stop_reason") or ("tool_use" if tools else "end_turn"),
            usage=TokenUsage(prompt_tokens=prompt, completion_tokens=max(1, len(text) // 4)),
        )


def full_len(request: LLMRequest) -> str:
    return "".join(render_message(m) for m in request.messages)


__all__ = ["BridgeProvider", "ProviderName"]
