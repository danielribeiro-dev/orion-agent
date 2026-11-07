"""
O.R.I.O.N — Anthropic Provider (v0.5.0 Sprint 1, ADR-020/021)

Messages API nativa (``POST /v1/messages``) via ``httpx``:
  - Streaming SSE tipado (text, thinking, tool_use) com blocos completos.
  - Prompt caching (``cache_control`` por bloco e no nível da requisição).
  - Thinking adaptativo + ``output_config.effort`` (Claude 5 rejeita ``budget_tokens``).
  - ``count_tokens``.
  - Uso com cache lido/escrito.
  - Retry/reconexão antes do primeiro chunk (``base.stream_with_retry``).

Decisões sobre a família Claude 5:
  - ``temperature`` nunca é enviada (valores não-padrão retornam 400).
  - ``tool_choice`` ``any``/``tool`` é rejeitado por Fable 5.1, Opus 5.5 e Sonnet 5.5:
    rebaixado para ``auto`` com aviso no log.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from orion.gateway.errors import (
    GatewayError,
    ProviderAPIError,
    ProviderConnectionError,
    ProviderTimeoutError,
    RateLimitError,
)
from orion.gateway.models import (
    CacheControl,
    ContentBlock,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
    MessageRole,
    ProviderName,
    TokenUsage,
    ToolChoice,
    to_blocks,
)
from orion.gateway.providers.base import (
    BaseLLMProvider,
    RetryPolicy,
    StreamAccumulator,
    stream_with_retry,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.anthropic.com"
_API_VERSION = "2023-06-01"
_MESSAGES_PATH = "/v1/messages"
_COUNT_TOKENS_PATH = "/v1/messages/count_tokens"

# Modelos que retornam 400 para tool_choice any/tool
_NO_FORCED_TOOL_CHOICE = ("claude-fable-5-1", "claude-mythos-5-1", "claude-opus-5-5", "claude-sonnet-5-5")

# Mapeamento do `type` de erro SSE/HTTP da Anthropic para status HTTP equivalente
_ERROR_TYPE_STATUS = {
    "invalid_request_error": 400,
    "authentication_error": 401,
    "permission_error": 403,
    "not_found_error": 404,
    "request_too_large": 413,
    "rate_limit_error": 429,
    "api_error": 500,
    "overloaded_error": 529,
}


def _to_api_error(status: int, message: str, retry_after: float | None = None) -> ProviderAPIError:
    if status == 429:
        return RateLimitError(f"Anthropic rate limit: {message}", retry_after=retry_after)
    if status in (401, 403):
        return ProviderAPIError(f"Anthropic authentication failed: {message}", status_code=status)
    return ProviderAPIError(f"Anthropic error {status}: {message}", status_code=status)


def _cache_dict(cc: CacheControl | None) -> dict[str, Any] | None:
    return cc.model_dump(exclude_none=True) if cc is not None else None


class AnthropicProvider(BaseLLMProvider):
    """Provedor nativo da API Anthropic.

    Args:
        api_key: ``ANTHROPIC_API_KEY``.
        base_url: URL base (padrão ``https://api.anthropic.com``).
        timeout_s: Timeout de leitura em segundos (entre eventos do stream).
        retry: Política de retry (padrão: 3 tentativas, backoff 1s..30s).
        transport: Transporte httpx opcional (testes com servidor SSE falso).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = _BASE_URL,
        timeout_s: float = 120.0,
        retry: RetryPolicy | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("Anthropic API key cannot be empty.")
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._retry = retry or RetryPolicy()
        self._transport = transport

    # ── Serialização ────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout_s, transport=self._transport)

    @classmethod
    def _block(cls, b: ContentBlock) -> dict[str, Any]:
        d: dict[str, Any]
        if b.type == "text":
            d = {"type": "text", "text": b.text}
        elif b.type == "thinking":
            d = {"type": "thinking", "thinking": b.thinking, "signature": b.signature or ""}
        elif b.type == "redacted_thinking":
            d = {"type": "redacted_thinking", "data": b.data}
        elif b.type == "tool_use":
            d = {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
        elif b.type == "tool_result":
            inner = b.content
            d = {
                "type": "tool_result",
                "tool_use_id": b.tool_use_id,
                "content": inner
                if isinstance(inner, str) or inner is None
                else [cls._block(x) for x in inner],
            }
            if b.is_error:
                d["is_error"] = True
        else:  # image
            d = {"type": "image", "source": b.source}
        cc = _cache_dict(b.cache_control)
        if cc:
            d["cache_control"] = cc
        return d

    def _split_messages(
        self, request: LLMRequest
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Retorna (system_blocks, messages). Mensagens SYSTEM legadas viram system."""
        system: list[dict[str, Any]] = []
        if isinstance(request.system, str):
            system.append({"type": "text", "text": request.system})
        elif request.system:
            system.extend(self._block(b) for b in request.system)

        messages: list[dict[str, Any]] = []
        for msg in request.messages:
            if msg.role == MessageRole.SYSTEM:
                system.extend(self._block(b) for b in msg.blocks)
                continue
            role = "assistant" if msg.role == MessageRole.ASSISTANT else "user"
            content = self._message_content(msg)
            if content:
                messages.append({"role": role, "content": content})
        return system, messages

    def _message_content(self, msg: LLMMessage) -> list[dict[str, Any]]:
        return [self._block(b) for b in to_blocks(msg.content)]

    def _tool_choice(self, model: str, tc: ToolChoice) -> dict[str, Any]:
        t = tc.type
        if t in ("any", "tool") and model.startswith(_NO_FORCED_TOOL_CHOICE):
            logger.warning(
                "Anthropic: tool_choice '%s' não é aceito por %s; usando 'auto'.", t, model
            )
            t = "auto"
        d: dict[str, Any] = {"type": t}
        if t == "tool":
            d["name"] = tc.name
        if tc.disable_parallel_tool_use and t != "none":
            d["disable_parallel_tool_use"] = True
        return d

    def _shared_payload(self, request: LLMRequest) -> dict[str, Any]:
        system, messages = self._split_messages(request)
        payload: dict[str, Any] = {"model": request.model, "messages": messages}
        if system:
            payload["system"] = system
        if request.tools:
            tools = []
            for t in request.tools:
                td: dict[str, Any] = {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                if t.strict:
                    td["strict"] = True
                cc = _cache_dict(t.cache_control)
                if cc:
                    td["cache_control"] = cc
                tools.append(td)
            payload["tools"] = tools
            if request.tool_choice is not None:
                payload["tool_choice"] = self._tool_choice(request.model, request.tool_choice)
        th = request.thinking
        if th is not None:
            thinking: dict[str, Any] = {"type": th.type}
            if th.type == "enabled" and th.budget_tokens:
                thinking["budget_tokens"] = th.budget_tokens
            if th.display and th.type != "disabled":
                thinking["display"] = th.display
            payload["thinking"] = thinking
            if th.effort:
                payload["output_config"] = {"effort": th.effort}
        return payload

    def _build_payload(self, request: LLMRequest, stream: bool = True) -> dict[str, Any]:
        payload = self._shared_payload(request)
        payload["max_tokens"] = request.max_tokens
        payload["stream"] = stream
        cc = _cache_dict(request.cache_control)
        if cc:
            payload["cache_control"] = cc
        if request.extra_params:
            payload.update(request.extra_params)
        return payload

    # ── Usage ───────────────────────────────────────────────────────────────

    @staticmethod
    def _usage(raw: dict[str, Any]) -> TokenUsage:
        """``input_tokens`` da Anthropic exclui cache; o ORION guarda o total."""
        base = int(raw.get("input_tokens") or 0)
        read = int(raw.get("cache_read_input_tokens") or 0)
        write = int(raw.get("cache_creation_input_tokens") or 0)
        out = int(raw.get("output_tokens") or 0)
        prompt = base + read + write
        return TokenUsage(
            prompt_tokens=prompt,
            completion_tokens=out,
            cached_tokens=read,
            cache_write_tokens=write,
            total_tokens=prompt + out,
        )

    # ── HTTP ────────────────────────────────────────────────────────────────

    @staticmethod
    async def _raise_http(response: httpx.Response) -> None:
        await response.aread()
        message = response.text[:300]
        with contextlib.suppress(Exception):
            message = response.json()["error"]["message"]
        retry_after: float | None = None
        header = response.headers.get("retry-after")
        if header:
            with contextlib.suppress(ValueError):
                retry_after = float(header)
        raise _to_api_error(response.status_code, message, retry_after)

    # ── stream() ────────────────────────────────────────────────────────────

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:
        """SSE tipado. Retry/reconexão só antes do primeiro chunk entregue."""
        async for chunk in stream_with_retry(
            lambda: self._stream_once(request), self._retry, "Anthropic"
        ):
            yield chunk

    async def _stream_once(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:
        url = f"{self._base_url}{_MESSAGES_PATH}"
        payload = self._build_payload(request, stream=True)
        state = _StreamState()
        try:
            async with self._client() as client, client.stream(
                "POST", url, headers=self._headers(), json=payload
            ) as response:
                if response.status_code != 200:
                    await self._raise_http(response)
                event = ""
                async for raw in response.aiter_lines():
                    line = raw.strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event = line[6:].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    try:
                        data = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        logger.debug("Anthropic: SSE não-JSON ignorado: %s", line[:80])
                        continue
                    for chunk in state.handle(event or data.get("type", ""), data):
                        yield chunk
                    if state.done:
                        return
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"Anthropic stream timeout after {self._timeout_s}s") from exc
        except httpx.TransportError as exc:
            raise ProviderConnectionError(f"Anthropic connection failed: {exc}") from exc
        if not state.done:
            raise ProviderConnectionError("Anthropic: stream terminou sem message_stop")

    # ── complete() ──────────────────────────────────────────────────────────

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Resposta completa, agregada sobre o stream (evita timeouts em saídas longas)."""
        t0 = time.monotonic()
        acc = StreamAccumulator()
        async for chunk in self.stream(request):
            acc.feed(chunk)
        return acc.build(
            request.model, ProviderName.ANTHROPIC, (time.monotonic() - t0) * 1000.0, request
        )

    # ── count_tokens() ──────────────────────────────────────────────────────

    async def count_tokens(self, request: LLMRequest) -> int:
        """Tokens de entrada da requisição (endpoint ``count_tokens``; não gera custo de inferência)."""
        url = f"{self._base_url}{_COUNT_TOKENS_PATH}"
        payload = self._shared_payload(request)
        payload.pop("output_config", None)  # não aceito pelo endpoint de contagem
        try:
            async with self._client() as client:
                response = await client.post(url, headers=self._headers(), json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Anthropic count_tokens timeout") from exc
        except httpx.TransportError as exc:
            raise ProviderConnectionError(f"Anthropic connection failed: {exc}") from exc
        if response.status_code != 200:
            message = response.text[:300]
            with contextlib.suppress(Exception):
                message = response.json()["error"]["message"]
            raise _to_api_error(response.status_code, message)
        return int(response.json()["input_tokens"])

    @property
    def provider_name(self) -> str:
        return "Anthropic"


class _StreamState:
    """Máquina de estados dos eventos SSE da Messages API."""

    def __init__(self) -> None:
        self.done = False
        self._usage: dict[str, Any] = {}
        self._stop_reason: str | None = None
        self._blocks: dict[int, dict[str, Any]] = {}

    def handle(self, event: str, data: dict[str, Any]) -> list[LLMResponseChunk]:
        if event == "message_start":
            self._usage.update(data.get("message", {}).get("usage") or {})
            return []
        if event == "content_block_start":
            self._blocks[data["index"]] = dict(data.get("content_block") or {})
            self._blocks[data["index"]].setdefault("_json", "")
            return []
        if event == "content_block_delta":
            return self._delta(data)
        if event == "content_block_stop":
            return self._stop_block(data["index"])
        if event == "message_delta":
            self._stop_reason = (data.get("delta") or {}).get("stop_reason") or self._stop_reason
            self._usage.update(data.get("usage") or {})
            return []
        if event == "message_stop":
            self.done = True
            return [
                LLMResponseChunk(
                    is_final=True,
                    usage=AnthropicProvider._usage(self._usage),
                    stop_reason=self._stop_reason,
                )
            ]
        if event == "error":
            err = data.get("error") or {}
            status = _ERROR_TYPE_STATUS.get(err.get("type", ""), 500)
            raise _to_api_error(status, err.get("message", "erro desconhecido no stream"))
        return []  # ping e eventos desconhecidos

    def _delta(self, data: dict[str, Any]) -> list[LLMResponseChunk]:
        blk = self._blocks.get(data["index"])
        if blk is None:
            return []
        d = data.get("delta") or {}
        kind = d.get("type")
        if kind == "text_delta":
            blk["text"] = blk.get("text", "") + d.get("text", "")
            return [LLMResponseChunk(delta=d.get("text", ""))]
        if kind == "thinking_delta":
            blk["thinking"] = blk.get("thinking", "") + d.get("thinking", "")
            return [LLMResponseChunk(reasoning_delta=d.get("thinking", ""))]
        if kind == "signature_delta":
            blk["signature"] = blk.get("signature", "") + d.get("signature", "")
        elif kind == "input_json_delta":
            blk["_json"] += d.get("partial_json", "")
        return []

    def _stop_block(self, index: int) -> list[LLMResponseChunk]:
        blk = self._blocks.pop(index, None)
        if blk is None:
            return []
        kind = blk.get("type")
        block: ContentBlock | None = None
        if kind == "text":
            block = ContentBlock.of_text(blk.get("text", ""))
        elif kind == "thinking":
            block = ContentBlock(
                type="thinking", thinking=blk.get("thinking", ""), signature=blk.get("signature")
            )
        elif kind == "redacted_thinking":
            block = ContentBlock(type="redacted_thinking", data=blk.get("data", ""))
        elif kind == "tool_use":
            raw = blk.get("_json") or ""
            try:
                parsed = json.loads(raw) if raw else (blk.get("input") or {})
            except json.JSONDecodeError as exc:
                # Sem input válido a tool não pode rodar: erro explícito, nunca truncar em silêncio.
                raise GatewayError(
                    f"tool_use '{blk.get('name')}' com JSON de input inválido/truncado"
                ) from exc
            block = ContentBlock.of_tool_use(blk["id"], blk["name"], parsed)
        return [LLMResponseChunk(block=block)] if block is not None else []
