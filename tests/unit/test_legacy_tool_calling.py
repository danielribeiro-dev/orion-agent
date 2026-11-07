"""Tool calling nativo nos providers legados (OpenRouter/Ollama) e failover com tools (Sprint 3)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
from aiohttp import web

from orion.gateway.errors import ProviderConnectionError
from orion.gateway.failover import FailoverCandidate, FailoverProvider
from orion.gateway.models import (
    ComplexityTier,
    ContentBlock,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
    MessageRole,
    ModelSpec,
    ProviderName,
    ToolChoice,
    ToolSpec,
)
from orion.gateway.providers import local_ollama
from orion.gateway.providers.base import BaseLLMProvider
from orion.gateway.providers.local_ollama import LocalOllamaProvider
from orion.gateway.providers.openai_wire import (
    INVALID_ARGS_KEY,
    ToolCallAssembler,
    blocks_from_ollama_calls,
    map_finish_reason,
    parse_arguments,
    serialize_messages,
    tool_choice_to_openai,
    tools_to_openai,
)
from orion.gateway.providers.openrouter import OpenRouterProvider

READ = ToolSpec(
    name="read_file",
    description="Lê um arquivo",
    input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
)


def history() -> list[LLMMessage]:
    """Pedido -> dois tool_use paralelos -> resultados -> pedido seguinte."""
    return [
        LLMMessage(role=MessageRole.SYSTEM, content="sys"),
        LLMMessage(role=MessageRole.USER, content="leia a.txt e b.txt"),
        LLMMessage(
            role=MessageRole.ASSISTANT,
            content=[
                ContentBlock(type="thinking", thinking="hmm", signature="sig"),
                ContentBlock.of_text("Lendo."),
                ContentBlock.of_tool_use("call_a", "read_file", {"path": "a.txt"}),
                ContentBlock.of_tool_use("call_b", "read_file", {"path": "b.txt"}),
            ],
        ),
        LLMMessage(
            role=MessageRole.USER,
            content=[
                ContentBlock.of_tool_result("call_a", "conteudo A"),
                ContentBlock.of_tool_result("call_b", "falhou", is_error=True),
            ],
        ),
        LLMMessage(role=MessageRole.USER, content="resuma"),
    ]


# ── Tradução de formato ──────────────────────────────────────────────────────


class TestWireFormat:
    def test_openai_history_keeps_tool_calls_and_results(self) -> None:
        wire = serialize_messages(history())
        assistant = wire[2]
        assert assistant["content"] == "Lendo."
        assert [c["id"] for c in assistant["tool_calls"]] == ["call_a", "call_b"]
        assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"path": "a.txt"}
        assert [(m["role"], m.get("tool_call_id")) for m in wire[3:5]] == [
            ("tool", "call_a"),
            ("tool", "call_b"),
        ]
        assert wire[3]["content"] == "conteudo A"
        assert wire[5] == {"role": "user", "content": "resuma"}
        assert "thinking" not in json.dumps(wire)

    def test_ollama_history_uses_objects_and_tool_name(self) -> None:
        wire = serialize_messages(history(), ollama=True)
        assert wire[2]["tool_calls"][0] == {"function": {"name": "read_file", "arguments": {"path": "a.txt"}}}
        assert wire[3]["tool_name"] == "read_file" and "tool_call_id" not in wire[3]

    def test_degraded_history_is_flat_text(self) -> None:
        wire = serialize_messages(history(), ollama=True, with_tools=False)
        assert all(set(m) == {"role", "content"} for m in wire)
        assert "conteudo A" in wire[3]["content"]

    def test_tools_and_choice(self) -> None:
        assert tools_to_openai([READ])[0]["function"]["parameters"]["required"] == ["path"]
        assert tool_choice_to_openai(None) is None
        assert tool_choice_to_openai(ToolChoice(type="any")) == "required"
        assert tool_choice_to_openai(ToolChoice(type="tool", name="read_file"))["function"]["name"] == "read_file"

    def test_finish_reasons(self) -> None:
        assert map_finish_reason("stop") == "end_turn"
        assert map_finish_reason("length") == "max_tokens"
        assert map_finish_reason("stop", has_tool_calls=True) == "tool_use"
        assert map_finish_reason(None) is None

    def test_malformed_arguments_are_marked_not_dropped(self) -> None:
        assert parse_arguments('{"a": 1}') == {"a": 1}
        assert parse_arguments("") == {}
        assert INVALID_ARGS_KEY in parse_arguments("{nao json")
        assert INVALID_ARGS_KEY in parse_arguments("[1, 2]")

    def test_assembler_merges_fragments_by_index(self) -> None:
        assembler = ToolCallAssembler()
        assembler.feed([{"index": 1, "id": "b", "function": {"name": "read_file", "arguments": '{"path":'}}])
        assembler.feed([{"index": 0, "id": "a", "function": {"name": "read_file", "arguments": '{"path": "x"}'}}])
        assembler.feed([{"index": 1, "function": {"arguments": ' "y"}'}}])
        blocks = assembler.finish()
        assert [(b.id, b.input) for b in blocks] == [("a", {"path": "x"}), ("b", {"path": "y"})]
        assert not assembler

    def test_ollama_calls_get_generated_ids(self) -> None:
        blocks = blocks_from_ollama_calls([{"function": {"name": "read_file", "arguments": {"path": "a"}}}, {}])
        assert len(blocks) == 1 and blocks[0].id and blocks[0].id.startswith("call_")


# ── Servidor HTTP simulado ───────────────────────────────────────────────────


class FakeServer:
    """Servidor aiohttp local que grava as requisições e responde com roteiros."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.handlers: dict[str, Callable[[web.Request, dict[str, Any]], Awaitable[web.StreamResponse]]] = {}
        self._runner: web.AppRunner | None = None
        self.url = ""

    async def start(self) -> None:
        app = web.Application()
        for path in ("/chat/completions", "/api/chat"):
            app.router.add_post(path, self._dispatch)
        app.router.add_get("/api/tags", self._tags)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        self.url = f"http://127.0.0.1:{port}"

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _tags(self, request: web.Request) -> web.Response:
        return web.json_response({"models": [{"name": "qwen"}]})

    async def _dispatch(self, request: web.Request) -> web.StreamResponse:
        body = await request.json()
        self.requests.append(body)
        return await self.handlers[request.path](request, body)


@pytest.fixture
async def server() -> AsyncIterator[FakeServer]:
    fake = FakeServer()
    await fake.start()
    yield fake
    await fake.stop()


def sse(events: list[dict[str, Any] | str]) -> Callable[[web.Request, dict[str, Any]], Awaitable[web.StreamResponse]]:
    async def handler(request: web.Request, body: dict[str, Any]) -> web.StreamResponse:
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        for event in events:
            data = event if isinstance(event, str) else json.dumps(event)
            await response.write(f"data: {data}\n\n".encode())
        return response

    return handler


def request_for(model: str = "m", **kw: Any) -> LLMRequest:
    return LLMRequest(model=model, messages=history(), tools=[READ], **kw)


async def collect(provider: BaseLLMProvider, request: LLMRequest) -> list[LLMResponseChunk]:
    return [chunk async for chunk in provider.stream(request)]


def tool_call_events() -> list[dict[str, Any] | str]:
    def delta(**d: Any) -> dict[str, Any]:
        return {"choices": [{"delta": d}]}

    return [
        delta(content="Vou "),
        delta(content="ler."),
        delta(tool_calls=[{"index": 0, "id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": ""}}]),
        delta(tool_calls=[{"index": 1, "id": "call_2", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "b'}}]),
        delta(tool_calls=[{"index": 0, "function": {"arguments": '{"path": "a.txt"}'}}]),
        delta(tool_calls=[{"index": 1, "function": {"arguments": '.txt"}'}}]),
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
        "[DONE]",
    ]


class TestOpenRouter:
    async def test_streams_parallel_tool_use(self, server: FakeServer) -> None:
        server.handlers["/chat/completions"] = sse(tool_call_events())
        provider = OpenRouterProvider(api_key="k", base_url=server.url)
        chunks = await collect(provider, request_for())

        payload = server.requests[0]
        assert payload["tools"][0]["function"]["name"] == "read_file"
        assert payload["messages"][2]["tool_calls"][1]["id"] == "call_b"
        assert payload["messages"][4]["tool_call_id"] == "call_b"

        assert "".join(c.delta for c in chunks) == "Vou ler."
        blocks = [c.block for c in chunks if c.block is not None]
        assert [(b.id, b.input) for b in blocks] == [
            ("call_1", {"path": "a.txt"}),
            ("call_2", {"path": "b.txt"}),
        ]
        final = [c for c in chunks if c.stop_reason]
        assert final[-1].stop_reason == "tool_use" and final[-1].usage is not None

    async def test_text_answer_ends_turn(self, server: FakeServer) -> None:
        server.handlers["/chat/completions"] = sse(
            [{"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}, "[DONE]"]
        )
        chunks = await collect(OpenRouterProvider(api_key="k", base_url=server.url), request_for())
        assert [c.stop_reason for c in chunks if c.stop_reason] == ["end_turn"]
        assert not [c for c in chunks if c.block]

    async def test_stream_cut_before_finish_keeps_tool_calls(self, server: FakeServer) -> None:
        events = tool_call_events()[:6] + ["[DONE]"]
        server.handlers["/chat/completions"] = sse(events)
        chunks = await collect(OpenRouterProvider(api_key="k", base_url=server.url), request_for())
        assert len([c for c in chunks if c.block]) == 2
        assert chunks[-1].stop_reason == "tool_use"

    async def test_complete_returns_blocks(self, server: FakeServer) -> None:
        async def handler(request: web.Request, body: dict[str, Any]) -> web.StreamResponse:
            return web.json_response(
                {
                    "model": "m",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "content": "x",
                                "tool_calls": [
                                    {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "a"}'}}
                                ],
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            )

        server.handlers["/chat/completions"] = handler
        response = await OpenRouterProvider(api_key="k", base_url=server.url).complete(request_for())
        assert response.stop_reason == "tool_use"
        assert [b.type for b in response.blocks] == ["text", "tool_use"]


def ndjson(lines: list[dict[str, Any]]) -> Callable[[web.Request, dict[str, Any]], Awaitable[web.StreamResponse]]:
    async def handler(request: web.Request, body: dict[str, Any]) -> web.StreamResponse:
        response = web.StreamResponse()
        await response.prepare(request)
        for line in lines:
            await response.write((json.dumps(line) + "\n").encode())
        return response

    return handler


class TestOllama:
    @pytest.fixture(autouse=True)
    def _reset_cache(self) -> None:
        local_ollama._MODELS_WITHOUT_TOOLS.clear()

    async def test_streams_tool_calls_with_native_usage(self, server: FakeServer) -> None:
        server.handlers["/api/chat"] = ndjson(
            [
                {"message": {"content": "Vou ler."}, "done": False},
                {"message": {"content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "a.txt"}}}]}, "done": False},
                {"message": {"content": ""}, "done": True, "done_reason": "stop", "prompt_eval_count": 40, "eval_count": 7},
            ]
        )
        chunks = await collect(LocalOllamaProvider("qwen", base_url=server.url), request_for())
        payload = server.requests[0]
        assert payload["tools"][0]["function"]["name"] == "read_file"
        assert payload["messages"][3]["tool_name"] == "read_file"
        blocks = [c.block for c in chunks if c.block]
        assert blocks[0].name == "read_file" and blocks[0].input == {"path": "a.txt"}
        final = chunks[-1]
        assert final.stop_reason == "tool_use"
        assert final.usage is not None and final.usage.prompt_tokens == 40 and final.usage.completion_tokens == 7

    async def test_model_without_tools_degrades_with_notice(self, server: FakeServer) -> None:
        async def handler(request: web.Request, body: dict[str, Any]) -> web.StreamResponse:
            if "tools" in body:
                return web.json_response({"error": "qwen does not support tools"}, status=400)
            return await ndjson([{"message": {"content": "so texto"}, "done": True}])(request, body)

        server.handlers["/api/chat"] = handler
        chunks = await collect(LocalOllamaProvider("qwen", base_url=server.url), request_for())
        notices = [c.notice for c in chunks if c.notice]
        assert notices and "não suporta tools" in notices[0]
        assert "".join(c.delta for c in chunks) == "so texto"
        retry = server.requests[1]
        assert "tools" not in retry and all(set(m) == {"role", "content"} for m in retry["messages"])

        # o modelo fica marcado: a chamada seguinte já vai sem tools (sem nova tentativa falha)
        await collect(LocalOllamaProvider("qwen", base_url=server.url), request_for())
        assert "tools" not in server.requests[2]

    async def test_complete_parses_tool_calls(self, server: FakeServer) -> None:
        async def handler(request: web.Request, body: dict[str, Any]) -> web.StreamResponse:
            return web.json_response(
                {
                    "message": {"content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "z"}}}]},
                    "done": True,
                    "prompt_eval_count": 3,
                    "eval_count": 2,
                }
            )

        server.handlers["/api/chat"] = handler
        response = await LocalOllamaProvider("qwen", base_url=server.url).complete(request_for())
        assert response.stop_reason == "tool_use" and response.blocks[0].input == {"path": "z"}
        assert response.usage.prompt_tokens == 3


# ── Failover preserva tools e tool_result ────────────────────────────────────


class DeadProvider(BaseLLMProvider):
    async def complete(self, request: LLMRequest) -> LLMResponse:  # pragma: no cover
        raise NotImplementedError

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:  # type: ignore[override]
        raise ProviderConnectionError("anthropic fora do ar")
        yield  # pragma: no cover


def spec(model_id: str, provider: ProviderName) -> ModelSpec:
    return ModelSpec(
        id=model_id, name=model_id, provider=provider, context_window=200_000,
        cost_input_m=1, cost_output_m=1, default_tier=ComplexityTier.HEAVY,
    )


async def test_failover_to_openrouter_keeps_tools_and_tool_results(server: FakeServer) -> None:
    server.handlers["/chat/completions"] = sse(tool_call_events())
    primary = spec("claude-x", ProviderName.ANTHROPIC)
    chain = [
        FailoverCandidate(primary, DeadProvider(), "claude-x", ProviderName.ANTHROPIC),
        FailoverCandidate(
            primary, OpenRouterProvider(api_key="k", base_url=server.url), "anthropic/claude-x", ProviderName.OPENROUTER
        ),
    ]
    provider = FailoverProvider(chain)
    request = request_for("claude-x", thinking=None)
    chunks = await collect(provider, request)

    payload = server.requests[0]
    assert payload["model"] == "anthropic/claude-x"
    assert payload["tools"], "tools perdidas no failover"
    roles = [m["role"] for m in payload["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "tool", "user"]
    assert {m["tool_call_id"] for m in payload["messages"] if m["role"] == "tool"} == {"call_a", "call_b"}
    assert len([c for c in chunks if c.block]) == 2
    assert provider.served is not None and provider.served.provider == ProviderName.OPENROUTER


async def test_failover_to_ollama_keeps_tools(server: FakeServer) -> None:
    local_ollama._MODELS_WITHOUT_TOOLS.clear()
    server.handlers["/api/chat"] = ndjson(
        [{"message": {"content": "ok", "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "q"}}}]}, "done": True}]
    )
    primary = spec("claude-x", ProviderName.ANTHROPIC)
    local = spec("qwen", ProviderName.OLLAMA)
    chain = [
        FailoverCandidate(primary, DeadProvider(), "claude-x", ProviderName.ANTHROPIC),
        FailoverCandidate(local, LocalOllamaProvider("qwen", base_url=server.url), "qwen", ProviderName.OLLAMA, downgrade=True),
    ]
    chunks = await collect(FailoverProvider(chain, allow_downgrade=True), request_for("claude-x"))
    assert server.requests[0]["tools"]
    assert any(c.block for c in chunks)
