"""Testes do AnthropicProvider contra um servidor SSE falso no formato real (v0.5.0 Sprint 1)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from orion.gateway.errors import (
    ProviderAPIError,
    ProviderConnectionError,
    RateLimitError,
    StreamInterruptedError,
)
from orion.gateway.ledger import CostLedger
from orion.gateway.models import (
    CacheControl,
    ContentBlock,
    LLMMessage,
    LLMRequest,
    MessageRole,
    ProviderName,
    ThinkingConfig,
    ToolChoice,
    ToolSpec,
)
from orion.gateway.providers.anthropic import AnthropicProvider
from orion.gateway.providers.base import RetryPolicy

FAST = RetryPolicy(max_attempts=3, base_delay_s=0.0, max_delay_s=0.0)


def sse(*events: tuple[str, dict[str, Any]]) -> bytes:
    return "".join(f"event: {n}\ndata: {json.dumps(d)}\n\n" for n, d in events).encode()


def start(inp: int = 10, read: int = 0, write: int = 0) -> tuple[str, dict[str, Any]]:
    return (
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "usage": {
                    "input_tokens": inp,
                    "cache_read_input_tokens": read,
                    "cache_creation_input_tokens": write,
                    "output_tokens": 1,
                },
            },
        },
    )


def text_block(i: int, *parts: str) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = [
        ("content_block_start", {"index": i, "content_block": {"type": "text", "text": ""}})
    ]
    out += [
        ("content_block_delta", {"index": i, "delta": {"type": "text_delta", "text": p}})
        for p in parts
    ]
    out.append(("content_block_stop", {"index": i}))
    return out


def finish(reason: str = "end_turn", out_tokens: int = 7) -> list[tuple[str, dict[str, Any]]]:
    return [
        ("message_delta", {"delta": {"stop_reason": reason}, "usage": {"output_tokens": out_tokens}}),
        ("message_stop", {"type": "message_stop"}),
    ]


def provider(handler: Callable[[httpx.Request], httpx.Response]) -> AnthropicProvider:
    return AnthropicProvider(
        api_key="sk-ant-test", retry=FAST, transport=httpx.MockTransport(handler)
    )


def req(**kw: Any) -> LLMRequest:
    kw.setdefault("model", "claude-sonnet-5-5")
    kw.setdefault("messages", [LLMMessage(role=MessageRole.USER, content="oi")])
    return LLMRequest(**kw)


async def collect(p: AnthropicProvider, r: LLMRequest) -> list[Any]:
    return [c async for c in p.stream(r)]


# ── Streaming tipado ─────────────────────────────────────────────────────────


async def test_stream_text_usage_and_cache_accounting() -> None:
    body = sse(
        ("ping", {"type": "ping"}),
        start(inp=20, read=1000, write=300),
        *text_block(0, "Olá, ", "Senhor."),
        *finish("end_turn", 42),
    )
    chunks = await collect(provider(lambda r: httpx.Response(200, content=body)), req())

    assert "".join(c.delta for c in chunks) == "Olá, Senhor."
    blocks = [c.block for c in chunks if c.block]
    assert [b.text for b in blocks] == ["Olá, Senhor."]
    final = chunks[-1]
    assert final.is_final and final.stop_reason == "end_turn"
    u = final.usage
    assert u is not None
    # prompt_tokens é o TOTAL (input + cache lido + cache escrito)
    assert (u.prompt_tokens, u.cached_tokens, u.cache_write_tokens, u.completion_tokens) == (
        1320,
        1000,
        300,
        42,
    )


async def test_stream_thinking_keeps_signature_and_tool_use_parses_json() -> None:
    body = sse(
        start(),
        ("content_block_start", {"index": 0, "content_block": {"type": "thinking", "thinking": ""}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "thinking_delta", "thinking": "hmm"}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "signature_delta", "signature": "SIG"}}),
        ("content_block_stop", {"index": 0}),
        *text_block(1, "vou ler"),
        (
            "content_block_start",
            {"index": 2, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {}}},
        ),
        ("content_block_delta", {"index": 2, "delta": {"type": "input_json_delta", "partial_json": '{"path": "a'}}),
        ("content_block_delta", {"index": 2, "delta": {"type": "input_json_delta", "partial_json": '.py"}'}}),
        ("content_block_stop", {"index": 2}),
        *finish("tool_use"),
    )
    chunks = await collect(provider(lambda r: httpx.Response(200, content=body)), req())

    assert "".join(c.reasoning_delta or "" for c in chunks) == "hmm"
    blocks = [c.block for c in chunks if c.block]
    assert [b.type for b in blocks] == ["thinking", "text", "tool_use"]
    assert blocks[0].signature == "SIG"
    assert (blocks[2].id, blocks[2].name, blocks[2].input) == ("toolu_1", "read_file", {"path": "a.py"})
    assert chunks[-1].stop_reason == "tool_use"


async def test_stream_truncated_tool_json_is_an_error_not_silent() -> None:
    body = sse(
        start(),
        ("content_block_start", {"index": 0, "content_block": {"type": "tool_use", "id": "t", "name": "x", "input": {}}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"a": '}}),
        ("content_block_stop", {"index": 0}),
    )
    with pytest.raises(Exception, match="inválido/truncado"):
        await collect(provider(lambda r: httpx.Response(200, content=body)), req())


async def test_error_event_mid_stream_raises_interrupted_without_restart() -> None:
    calls = 0

    def handler(r: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = sse(
            start(),
            *text_block(0, "parcial"),
            ("error", {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}),
        )
        return httpx.Response(200, content=body)

    p = provider(handler)
    got: list[Any] = []
    with pytest.raises(StreamInterruptedError):
        async for c in p.stream(req()):
            got.append(c)
    assert "parcial" in "".join(c.delta for c in got)
    assert calls == 1  # nada de reinício silencioso (duplicaria o texto)


async def test_stream_ending_without_message_stop_is_interruption() -> None:
    body = sse(start(), *text_block(0, "x"))
    with pytest.raises(StreamInterruptedError):
        await collect(provider(lambda r: httpx.Response(200, content=body)), req())


# ── Retry ─────────────────────────────────────────────────────────────────────


async def test_429_then_success_retries_before_first_chunk() -> None:
    n = 0

    def handler(r: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        if n == 1:
            return httpx.Response(429, json={"error": {"type": "rate_limit_error", "message": "slow"}},
                                  headers={"retry-after": "0"})
        return httpx.Response(200, content=sse(start(), *text_block(0, "ok"), *finish()))

    chunks = await collect(provider(handler), req())
    assert n == 2 and chunks[0].delta == "ok"


async def test_5xx_and_529_are_retried_until_exhausted() -> None:
    n = 0

    def handler(r: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        return httpx.Response(529, json={"error": {"type": "overloaded_error", "message": "busy"}})

    with pytest.raises(ProviderAPIError) as ei:
        await collect(provider(handler), req())
    assert ei.value.status_code == 529 and n == 3


async def test_429_exhausted_raises_rate_limit() -> None:
    p = provider(lambda r: httpx.Response(429, json={"error": {"message": "x"}}))
    with pytest.raises(RateLimitError):
        await collect(p, req())


async def test_401_is_not_retried() -> None:
    n = 0

    def handler(r: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        return httpx.Response(401, json={"error": {"type": "authentication_error", "message": "bad key"}})

    with pytest.raises(ProviderAPIError, match="authentication"):
        await collect(provider(handler), req())
    assert n == 1


async def test_connection_error_maps_to_connection_error() -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ProviderConnectionError):
        await collect(provider(handler), req())


# ── Payload ───────────────────────────────────────────────────────────────────


async def test_payload_system_tools_cache_thinking_and_no_temperature() -> None:
    seen: dict[str, Any] = {}

    def handler(r: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(r.content)
        seen["headers"] = r.headers
        return httpx.Response(200, content=sse(start(), *finish()))

    request = req(
        model="claude-opus-5-5",
        messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="legado"),
            LLMMessage(role=MessageRole.USER, content="oi"),
            LLMMessage(
                role=MessageRole.ASSISTANT,
                content=[ContentBlock.of_tool_use("t1", "read_file", {"path": "a"})],
            ),
            LLMMessage(
                role=MessageRole.USER,
                content=[ContentBlock.of_tool_result("t1", "conteúdo", is_error=True)],
            ),
        ],
        system=[ContentBlock.of_text("sistema", CacheControl(ttl="1h"))],
        tools=[ToolSpec(name="read_file", description="lê", input_schema={"type": "object"})],
        tool_choice=ToolChoice(type="any"),
        thinking=ThinkingConfig(type="adaptive", display="summarized", effort="high"),
        cache_control=CacheControl(),
        temperature=1.5,
    )
    await collect(provider(handler), request)
    b = seen["body"]

    assert seen["headers"]["x-api-key"] == "sk-ant-test"
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    assert "temperature" not in b
    assert b["stream"] is True and b["cache_control"] == {"type": "ephemeral"}
    assert b["system"][0] == {"type": "text", "text": "sistema", "cache_control": {"type": "ephemeral", "ttl": "1h"}}
    assert b["system"][1]["text"] == "legado"
    assert [m["role"] for m in b["messages"]] == ["user", "assistant", "user"]
    assert b["messages"][1]["content"][0] == {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "a"}}
    assert b["messages"][2]["content"][0]["is_error"] is True
    assert b["tools"][0]["name"] == "read_file"
    # Opus 5.5 recusa tool_choice forçado: rebaixado para auto
    assert b["tool_choice"] == {"type": "auto"}
    assert b["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert b["output_config"] == {"effort": "high"}


async def test_forced_tool_choice_is_kept_for_models_that_accept_it() -> None:
    seen: dict[str, Any] = {}

    def handler(r: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(r.content)
        return httpx.Response(200, content=sse(start(), *finish()))

    await collect(
        provider(handler),
        req(model="claude-haiku-5-5", tools=[ToolSpec(name="t", description="d")],
            tool_choice=ToolChoice(type="tool", name="t")),
    )
    assert seen["body"]["tool_choice"] == {"type": "tool", "name": "t"}


# ── complete / count_tokens ───────────────────────────────────────────────────


async def test_complete_aggregates_stream() -> None:
    body = sse(start(inp=5), *text_block(0, "a", "b"), *finish("end_turn", 3))
    resp = await provider(lambda r: httpx.Response(200, content=body)).complete(req())
    assert resp.content == "ab" and resp.provider == ProviderName.ANTHROPIC
    assert resp.stop_reason == "end_turn" and resp.usage.completion_tokens == 3
    assert [b.type for b in resp.blocks] == ["text"]


async def test_count_tokens() -> None:
    seen: dict[str, Any] = {}

    def handler(r: httpx.Request) -> httpx.Response:
        seen["path"] = r.url.path
        seen["body"] = json.loads(r.content)
        return httpx.Response(200, json={"input_tokens": 123})

    n = await provider(handler).count_tokens(req(thinking=ThinkingConfig(effort="low")))
    assert n == 123 and seen["path"] == "/v1/messages/count_tokens"
    assert "max_tokens" not in seen["body"] and "output_config" not in seen["body"]


async def test_count_tokens_error() -> None:
    p = provider(lambda r: httpx.Response(400, json={"error": {"message": "ruim"}}))
    with pytest.raises(ProviderAPIError, match="ruim"):
        await p.count_tokens(req())


def test_empty_key_rejected() -> None:
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="  ")


# ── Custo de cache no ledger ──────────────────────────────────────────────────


async def test_cache_read_and_write_priced_in_ledger(tmp_path: Any) -> None:
    body = sse(start(inp=1_000_000, read=2_000_000, write=1_000_000), *text_block(0, "x"), *finish("end_turn", 1_000_000))
    chunks = await collect(provider(lambda r: httpx.Response(200, content=body)), req())
    usage = chunks[-1].usage
    assert usage is not None
    ledger = CostLedger(db_path=tmp_path / "m.db")
    rec = ledger.record_turn_cost(ProviderName.ANTHROPIC, "claude-sonnet-5-5", usage)
    # sonnet 5.5: in $2, out $10, cache read $0.20, write 1.25x$2
    expected = 1 * 2.0 + 2 * 0.20 + 1 * 2.0 * 1.25 + 1 * 10.0
    assert rec.cost_usd == pytest.approx(expected)
    assert rec.cache_write_tokens == 1_000_000
