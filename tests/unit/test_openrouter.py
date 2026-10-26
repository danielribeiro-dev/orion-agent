"""
O.R.I.O.N — Test Suite: Gateway Sprint 1
tests/unit/test_openrouter.py

Cobre:
  1. ModelSpec e TokenUsage (modelos Pydantic)
  2. ModelRegistry (catálogo, queries por tier/provedor)
  3. BaseLLMProvider (contrato abstrato)
  4. OpenRouterProvider.complete() com mocks httpx
  5. OpenRouterProvider.stream() com mocks SSE
  6. Tratamento de erros tipados (401, 402, 429, 5xx, timeout, connection)
"""

from __future__ import annotations

import json
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from orion.gateway.models import (
    ComplexityTier,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
    MessageRole,
    ModelSpec,
    ProviderName,
    TokenUsage,
)
from orion.gateway.registry import ModelRegistry, _CATALOG
from orion.gateway.providers.base import BaseLLMProvider
from orion.gateway.providers.openrouter import (
    OpenRouterProvider,
    GatewayError,
    ProviderAPIError,
    ProviderConnectionError,
    ProviderTimeoutError,
    RateLimitError,
)


# ---------------------------------------------------------------------------
# Fixtures compartilhadas
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> ModelRegistry:
    return ModelRegistry()


@pytest.fixture()
def provider() -> OpenRouterProvider:
    return OpenRouterProvider(api_key="sk-or-v1-test-key")


@pytest.fixture()
def basic_request() -> LLMRequest:
    return LLMRequest(
        model="anthropic/claude-haiku-3-5",
        messages=[
            LLMMessage(role=MessageRole.USER, content="Hello, ORION!"),
        ],
        max_tokens=100,
        stream=False,
    )


@pytest.fixture()
def stream_request() -> LLMRequest:
    return LLMRequest(
        model="anthropic/claude-haiku-3-5",
        messages=[
            LLMMessage(role=MessageRole.USER, content="Stream test"),
        ],
        max_tokens=50,
        stream=True,
    )


# ---------------------------------------------------------------------------
# 1. Modelos Pydantic — TokenUsage
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_default_values(self) -> None:
        u = TokenUsage()
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0
        assert u.cached_tokens == 0
        assert u.reasoning_tokens == 0
        assert u.total_tokens == 0

    def test_custom_values(self) -> None:
        u = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            cached_tokens=20,
            reasoning_tokens=10,
            total_tokens=150,
        )
        assert u.prompt_tokens == 100
        assert u.completion_tokens == 50
        assert u.cached_tokens == 20
        assert u.reasoning_tokens == 10
        assert u.total_tokens == 150

    def test_immutable(self) -> None:
        u = TokenUsage(prompt_tokens=10)
        with pytest.raises(Exception):
            u.prompt_tokens = 99  # type: ignore[misc]

    def test_negative_values_rejected(self) -> None:
        with pytest.raises(Exception):
            TokenUsage(prompt_tokens=-1)


# ---------------------------------------------------------------------------
# 2. Modelos Pydantic — LLMMessage
# ---------------------------------------------------------------------------


class TestLLMMessage:
    def test_basic_user_message(self) -> None:
        msg = LLMMessage(role=MessageRole.USER, content="Hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"
        assert msg.reasoning_content is None
        assert msg.name is None

    def test_assistant_with_reasoning(self) -> None:
        msg = LLMMessage(
            role=MessageRole.ASSISTANT,
            content="Final answer",
            reasoning_content="Let me think...",
        )
        assert msg.reasoning_content == "Let me think..."

    def test_role_values(self) -> None:
        for role in MessageRole:
            msg = LLMMessage(role=role, content="test")
            assert msg.role == role

    def test_immutable(self) -> None:
        msg = LLMMessage(role=MessageRole.USER, content="x")
        with pytest.raises(Exception):
            msg.content = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. Modelos Pydantic — LLMRequest
# ---------------------------------------------------------------------------


class TestLLMRequest:
    def test_defaults(self) -> None:
        req = LLMRequest(
            model="some/model",
            messages=[LLMMessage(role=MessageRole.USER, content="hi")],
        )
        assert req.temperature == 0.7
        assert req.max_tokens == 4096
        assert req.stream is True
        assert req.complexity_tier == ComplexityTier.BALANCED
        assert req.extra_params == {}

    def test_temperature_bounds(self) -> None:
        with pytest.raises(Exception):
            LLMRequest(
                model="x",
                messages=[LLMMessage(role=MessageRole.USER, content="y")],
                temperature=3.0,
            )

    def test_extra_params_passthrough(self) -> None:
        req = LLMRequest(
            model="x",
            messages=[LLMMessage(role=MessageRole.USER, content="y")],
            extra_params={"top_p": 0.9, "seed": 42},
        )
        assert req.extra_params["top_p"] == 0.9
        assert req.extra_params["seed"] == 42


# ---------------------------------------------------------------------------
# 4. Modelos Pydantic — ModelSpec
# ---------------------------------------------------------------------------


class TestModelSpec:
    def test_cloud_model(self) -> None:
        spec = ModelSpec(
            id="test/model",
            name="Test Model",
            provider=ProviderName.OPENROUTER,
            context_window=128_000,
            cost_input_m=1.0,
            cost_output_m=3.0,
        )
        assert spec.is_local is False
        assert spec.supports_thinking is False
        assert spec.default_tier == ComplexityTier.BALANCED

    def test_local_model(self) -> None:
        spec = ModelSpec(
            id="qwen2.5-coder:1.5b",
            name="Qwen Local",
            provider=ProviderName.OLLAMA,
            context_window=32_768,
            cost_input_m=0.0,
            cost_output_m=0.0,
            is_local=True,
        )
        assert spec.is_local is True
        assert spec.cost_input_m == 0.0

    def test_context_window_minimum(self) -> None:
        with pytest.raises(Exception):
            ModelSpec(
                id="x",
                name="x",
                provider=ProviderName.OPENROUTER,
                context_window=512,  # abaixo do mínimo 1024
                cost_input_m=1.0,
                cost_output_m=1.0,
            )


# ---------------------------------------------------------------------------
# 5. ModelRegistry
# ---------------------------------------------------------------------------


class TestModelRegistry:
    def test_catalog_not_empty(self, registry: ModelRegistry) -> None:
        assert len(registry) > 0

    def test_get_existing_model(self, registry: ModelRegistry) -> None:
        spec = registry.get("anthropic/claude-haiku-3-5")
        assert spec is not None
        assert spec.name == "Claude Haiku 3.5"

    def test_get_nonexistent_returns_none(self, registry: ModelRegistry) -> None:
        assert registry.get("nonexistent/model") is None

    def test_require_existing(self, registry: ModelRegistry) -> None:
        spec = registry.require("google/gemini-2.0-flash")
        assert spec.provider == ProviderName.OPENROUTER

    def test_require_nonexistent_raises_keyerror(self, registry: ModelRegistry) -> None:
        with pytest.raises(KeyError, match="not found in registry"):
            registry.require("nonexistent/model")

    def test_contains_operator(self, registry: ModelRegistry) -> None:
        assert "anthropic/claude-haiku-3-5" in registry
        assert "phantom/model" not in registry

    def test_by_tier_fast(self, registry: ModelRegistry) -> None:
        models = registry.by_tier(ComplexityTier.FAST)
        assert len(models) > 0
        for m in models:
            assert m.default_tier == ComplexityTier.FAST

    def test_by_tier_heavy(self, registry: ModelRegistry) -> None:
        models = registry.by_tier(ComplexityTier.HEAVY)
        assert len(models) > 0
        for m in models:
            assert m.default_tier == ComplexityTier.HEAVY

    def test_by_tier_sorted_by_cost(self, registry: ModelRegistry) -> None:
        models = registry.by_tier(ComplexityTier.BALANCED)
        if len(models) >= 2:
            costs = [m.cost_output_m for m in models]
            assert costs == sorted(costs)

    def test_by_provider_openrouter(self, registry: ModelRegistry) -> None:
        models = registry.by_provider(ProviderName.OPENROUTER)
        assert len(models) > 0
        for m in models:
            assert m.provider == ProviderName.OPENROUTER

    def test_local_models(self, registry: ModelRegistry) -> None:
        locals_ = registry.local_models()
        assert len(locals_) > 0
        for m in locals_:
            assert m.is_local is True
            assert m.provider == ProviderName.OLLAMA
            assert m.cost_input_m == 0.0
            assert m.cost_output_m == 0.0

    def test_cloud_models(self, registry: ModelRegistry) -> None:
        clouds = registry.cloud_models()
        assert len(clouds) > 0
        for m in clouds:
            assert m.is_local is False

    def test_supports_thinking(self, registry: ModelRegistry) -> None:
        thinking = registry.supports_thinking()
        assert len(thinking) > 0
        for m in thinking:
            assert m.supports_thinking is True

    def test_ids(self, registry: ModelRegistry) -> None:
        ids = registry.ids()
        assert "anthropic/claude-haiku-3-5" in ids

    def test_all_models(self, registry: ModelRegistry) -> None:
        models = registry.all_models()
        assert len(models) == len(registry)

    def test_repr(self, registry: ModelRegistry) -> None:
        assert "ModelRegistry" in repr(registry)
        assert str(len(registry)) in repr(registry)

    def test_custom_catalog(self) -> None:
        custom = [
            ModelSpec(
                id="custom/model",
                name="Custom",
                provider=ProviderName.OPENROUTER,
                context_window=4096,
                cost_input_m=0.5,
                cost_output_m=1.5,
            )
        ]
        reg = ModelRegistry(catalog=custom)
        assert len(reg) == 1
        assert reg.get("custom/model") is not None

    def test_qwen_local_models_present(self, registry: ModelRegistry) -> None:
        assert "qwen2.5-coder:1.5b" in registry
        assert "qwen2.5-coder:3b" in registry


# ---------------------------------------------------------------------------
# 6. BaseLLMProvider — Contrato Abstrato
# ---------------------------------------------------------------------------


class TestBaseLLMProvider:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            BaseLLMProvider()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_methods(self) -> None:
        """Uma subclasse sem complete() ou stream() não pode ser instanciada."""

        class IncompleteProvider(BaseLLMProvider):
            pass

        with pytest.raises(TypeError):
            IncompleteProvider()  # type: ignore[abstract]

    def test_concrete_provider_name(self) -> None:
        """provider_name retorna o nome da classe por padrão."""

        class MyProvider(BaseLLMProvider):
            async def complete(self, request: LLMRequest) -> LLMResponse:  # type: ignore[empty-body]
                ...

            def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:  # type: ignore[empty-body]
                ...

        p = MyProvider()
        assert p.provider_name == "MyProvider"


# ---------------------------------------------------------------------------
# 7. OpenRouterProvider — Instanciação & Headers
# ---------------------------------------------------------------------------


class TestOpenRouterProviderInit:
    def test_valid_api_key(self) -> None:
        p = OpenRouterProvider(api_key="sk-or-v1-abc123")
        assert p.provider_name == "OpenRouter"

    def test_empty_api_key_raises(self) -> None:
        with pytest.raises(ValueError, match="API key cannot be empty"):
            OpenRouterProvider(api_key="")

    def test_whitespace_api_key_raises(self) -> None:
        with pytest.raises(ValueError, match="API key cannot be empty"):
            OpenRouterProvider(api_key="   ")

    def test_custom_base_url(self) -> None:
        p = OpenRouterProvider(api_key="key", base_url="https://my-proxy.ai/v1")
        assert "my-proxy" in p._base_url

    def test_headers_contain_bearer(self, provider: OpenRouterProvider) -> None:
        headers = provider._build_headers()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")
        assert "X-Title" in headers
        assert headers["X-Title"] == "ORION-Agent"

    def test_payload_stream_false(
        self, provider: OpenRouterProvider, basic_request: LLMRequest
    ) -> None:
        payload = provider._build_payload(basic_request, stream=False)
        assert payload["stream"] is False
        assert payload["model"] == basic_request.model
        assert len(payload["messages"]) == 1

    def test_payload_extra_params(self, provider: OpenRouterProvider) -> None:
        req = LLMRequest(
            model="x",
            messages=[LLMMessage(role=MessageRole.USER, content="y")],
            extra_params={"top_p": 0.95},
        )
        payload = provider._build_payload(req, stream=False)
        assert payload["top_p"] == 0.95


# ---------------------------------------------------------------------------
# 8. _parse_usage — Extração de métricas
# ---------------------------------------------------------------------------


class TestParseUsage:
    def test_empty_dict(self) -> None:
        u = OpenRouterProvider._parse_usage({})
        assert u.prompt_tokens == 0

    def test_none(self) -> None:
        u = OpenRouterProvider._parse_usage(None)
        assert u.total_tokens == 0

    def test_basic_usage(self) -> None:
        u = OpenRouterProvider._parse_usage(
            {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        )
        assert u.prompt_tokens == 100
        assert u.completion_tokens == 50
        assert u.total_tokens == 150

    def test_with_cached_tokens(self) -> None:
        u = OpenRouterProvider._parse_usage(
            {
                "prompt_tokens": 200,
                "completion_tokens": 80,
                "total_tokens": 280,
                "prompt_tokens_details": {"cached_tokens": 50},
            }
        )
        assert u.cached_tokens == 50

    def test_with_reasoning_tokens(self) -> None:
        u = OpenRouterProvider._parse_usage(
            {
                "prompt_tokens": 100,
                "completion_tokens": 300,
                "total_tokens": 400,
                "completion_tokens_details": {"reasoning_tokens": 150},
            }
        )
        assert u.reasoning_tokens == 150

    def test_total_inferred_if_missing(self) -> None:
        u = OpenRouterProvider._parse_usage(
            {"prompt_tokens": 100, "completion_tokens": 50}
        )
        assert u.total_tokens == 150


# ---------------------------------------------------------------------------
# 9. _raise_for_status — Erros HTTP
# ---------------------------------------------------------------------------


class TestRaiseForStatus:
    def _mock_response(self, status_code: int, text: str = "", headers: dict | None = None) -> httpx.Response:
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code
        response.text = text
        response.headers = headers or {}
        return response

    def test_200_ok(self) -> None:
        r = self._mock_response(200)
        OpenRouterProvider._raise_for_status(r)  # não deve levantar

    def test_401_raises_provider_api_error(self) -> None:
        r = self._mock_response(401)
        with pytest.raises(ProviderAPIError, match="authentication failed"):
            OpenRouterProvider._raise_for_status(r)

    def test_402_raises_provider_api_error(self) -> None:
        r = self._mock_response(402)
        with pytest.raises(ProviderAPIError, match="insufficient credits"):
            OpenRouterProvider._raise_for_status(r)

    def test_429_raises_rate_limit_error(self) -> None:
        r = self._mock_response(429, headers={"Retry-After": "30"})
        with pytest.raises(RateLimitError) as exc_info:
            OpenRouterProvider._raise_for_status(r)
        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == 30.0

    def test_429_no_retry_after(self) -> None:
        r = self._mock_response(429)
        with pytest.raises(RateLimitError) as exc_info:
            OpenRouterProvider._raise_for_status(r)
        assert exc_info.value.retry_after is None

    def test_500_raises_provider_api_error(self) -> None:
        r = self._mock_response(500, text="Internal Server Error")
        with pytest.raises(ProviderAPIError) as exc_info:
            OpenRouterProvider._raise_for_status(r)
        assert exc_info.value.status_code == 500

    def test_503_raises_provider_api_error(self) -> None:
        r = self._mock_response(503, text="Service Unavailable")
        with pytest.raises(ProviderAPIError) as exc_info:
            OpenRouterProvider._raise_for_status(r)
        assert exc_info.value.status_code == 503

    def test_unexpected_4xx(self) -> None:
        r = self._mock_response(404, text="Not Found")
        with pytest.raises(ProviderAPIError) as exc_info:
            OpenRouterProvider._raise_for_status(r)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Helpers para mock de respostas HTTP
# ---------------------------------------------------------------------------

def _make_complete_response_json(
    content: str = "Hello from ORION!",
    model: str = "anthropic/claude-haiku-3-5",
    prompt_tokens: int = 20,
    completion_tokens: int = 10,
) -> dict:
    return {
        "id": "chatcmpl-test-123",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": None,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _make_sse_lines(chunks: list[str], finish_reason: str = "stop", usage: dict | None = None) -> list[str]:
    """Gera linhas SSE simuladas para streaming."""
    lines = []
    for i, delta in enumerate(chunks):
        is_last = i == len(chunks) - 1
        chunk = {
            "choices": [
                {
                    "delta": {"content": delta},
                    "finish_reason": finish_reason if is_last else None,
                }
            ],
        }
        if is_last and usage:
            chunk["usage"] = usage
        lines.append(f"data: {json.dumps(chunk)}")
    lines.append("data: [DONE]")
    return lines


# ---------------------------------------------------------------------------
# 10. OpenRouterProvider.complete() — Mocks
# ---------------------------------------------------------------------------


class TestOpenRouterComplete:
    @pytest.mark.asyncio
    async def test_complete_success(
        self, provider: OpenRouterProvider, basic_request: LLMRequest
    ) -> None:
        """complete() retorna LLMResponse com conteúdo e usage corretos."""
        response_json = _make_complete_response_json("Hello, world!")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = response_json

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            result = await provider.complete(basic_request)

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello, world!"
        assert result.provider == ProviderName.OPENROUTER
        assert result.usage.prompt_tokens == 20
        assert result.usage.completion_tokens == 10
        assert result.latency_ms >= 0.0
        assert result.complexity_tier == ComplexityTier.BALANCED

    @pytest.mark.asyncio
    async def test_complete_with_reasoning_content(
        self, provider: OpenRouterProvider, basic_request: LLMRequest
    ) -> None:
        """complete() extrai reasoning_content quando presente."""
        resp_json = _make_complete_response_json()
        resp_json["choices"][0]["message"]["reasoning_content"] = "Let me reason..."

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = resp_json

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            result = await provider.complete(basic_request)

        assert result.reasoning_content == "Let me reason..."

    @pytest.mark.asyncio
    async def test_complete_401_raises_provider_api_error(
        self, provider: OpenRouterProvider, basic_request: LLMRequest
    ) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ProviderAPIError, match="authentication failed"):
                await provider.complete(basic_request)

    @pytest.mark.asyncio
    async def test_complete_timeout_raises(
        self, provider: OpenRouterProvider, basic_request: LLMRequest
    ) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ProviderTimeoutError):
                await provider.complete(basic_request)

    @pytest.mark.asyncio
    async def test_complete_connection_error_raises(
        self, provider: OpenRouterProvider, basic_request: LLMRequest
    ) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("Network unreachable")
        )

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ProviderConnectionError, match="connection failed"):
                await provider.complete(basic_request)

    @pytest.mark.asyncio
    async def test_complete_retries_on_rate_limit(
        self, provider: OpenRouterProvider, basic_request: LLMRequest
    ) -> None:
        """complete() deve tentar novamente após RateLimitError e ter sucesso."""
        ok_response = MagicMock(spec=httpx.Response)
        ok_response.status_code = 200
        ok_response.json.return_value = _make_complete_response_json()

        rate_limit_response = MagicMock(spec=httpx.Response)
        rate_limit_response.status_code = 429
        rate_limit_response.text = "Rate Limited"
        rate_limit_response.headers = {}  # sem Retry-After

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return rate_limit_response
            return ok_response

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = mock_post

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await provider.complete(basic_request)

        assert call_count == 2
        assert isinstance(result, LLMResponse)

    @pytest.mark.asyncio
    async def test_complete_complexity_tier_propagated(
        self, provider: OpenRouterProvider
    ) -> None:
        """Tier de complexidade da request é propagado para a response."""
        req = LLMRequest(
            model="anthropic/claude-haiku-3-5",
            messages=[LLMMessage(role=MessageRole.USER, content="hi")],
            complexity_tier=ComplexityTier.HEAVY,
            stream=False,
        )
        ok_response = MagicMock(spec=httpx.Response)
        ok_response.status_code = 200
        ok_response.json.return_value = _make_complete_response_json()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=ok_response)

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            result = await provider.complete(req)

        assert result.complexity_tier == ComplexityTier.HEAVY


# ---------------------------------------------------------------------------
# 11. OpenRouterProvider.stream() — Mocks SSE
# ---------------------------------------------------------------------------


async def _collect_stream(gen) -> list[LLMResponseChunk]:
    """Helper: coleta todos os chunks de um async generator."""
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return chunks


class TestOpenRouterStream:
    def _make_streaming_client(self, sse_lines: list[str], status_code: int = 200):
        """Cria um mock de httpx.AsyncClient configurado para streaming SSE."""
        # Mock do context manager de streaming
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_cm)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)
        mock_stream_cm.status_code = status_code

        async def mock_aiter_lines():
            for line in sse_lines:
                yield line

        mock_stream_cm.aiter_lines = mock_aiter_lines

        # Mock do client
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        return mock_client

    @pytest.mark.asyncio
    async def test_stream_basic(
        self, provider: OpenRouterProvider, stream_request: LLMRequest
    ) -> None:
        """stream() emite chunks com deltas de texto corretos."""
        sse_lines = _make_sse_lines(["Hello", " world", "!"])
        mock_client = self._make_streaming_client(sse_lines)

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            gen = provider.stream(stream_request)
            chunks = await _collect_stream(gen)

        assert len(chunks) == 3
        assert chunks[0].delta == "Hello"
        assert chunks[1].delta == " world"
        assert chunks[2].delta == "!"
        assert chunks[2].is_final is True

    @pytest.mark.asyncio
    async def test_stream_last_chunk_has_usage(
        self, provider: OpenRouterProvider, stream_request: LLMRequest
    ) -> None:
        """Último chunk do stream deve conter usage."""
        usage = {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20}
        sse_lines = _make_sse_lines(["Done!"], usage=usage)
        mock_client = self._make_streaming_client(sse_lines)

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            gen = provider.stream(stream_request)
            chunks = await _collect_stream(gen)

        final = chunks[-1]
        assert final.is_final is True
        assert final.usage is not None
        assert final.usage.prompt_tokens == 15
        assert final.usage.completion_tokens == 5

    @pytest.mark.asyncio
    async def test_stream_skips_empty_lines(
        self, provider: OpenRouterProvider, stream_request: LLMRequest
    ) -> None:
        """Linhas vazias (separadores SSE) são ignoradas."""
        raw_lines = [
            "",
            "data: " + json.dumps({"choices": [{"delta": {"content": "Hi"}, "finish_reason": "stop"}]}),
            "",
            "data: [DONE]",
        ]
        mock_client = self._make_streaming_client(raw_lines)

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            gen = provider.stream(stream_request)
            chunks = await _collect_stream(gen)

        assert len(chunks) == 1
        assert chunks[0].delta == "Hi"

    @pytest.mark.asyncio
    async def test_stream_skips_non_data_lines(
        self, provider: OpenRouterProvider, stream_request: LLMRequest
    ) -> None:
        """Linhas SSE sem prefixo 'data:' são ignoradas."""
        raw_lines = [
            ": heartbeat",
            "event: message",
            "data: " + json.dumps({"choices": [{"delta": {"content": "OK"}, "finish_reason": "stop"}]}),
            "data: [DONE]",
        ]
        mock_client = self._make_streaming_client(raw_lines)

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            gen = provider.stream(stream_request)
            chunks = await _collect_stream(gen)

        assert len(chunks) == 1
        assert chunks[0].delta == "OK"

    @pytest.mark.asyncio
    async def test_stream_timeout_raises(
        self, provider: OpenRouterProvider, stream_request: LLMRequest
    ) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(
            side_effect=httpx.TimeoutException("Stream timeout")
        )

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ProviderTimeoutError, match="stream timeout"):
                async for _ in provider.stream(stream_request):
                    pass

    @pytest.mark.asyncio
    async def test_stream_connection_error_raises(
        self, provider: OpenRouterProvider, stream_request: LLMRequest
    ) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(
            side_effect=httpx.ConnectError("Network down")
        )

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ProviderConnectionError, match="stream connection failed"):
                async for _ in provider.stream(stream_request):
                    pass

    @pytest.mark.asyncio
    async def test_stream_reasoning_delta(
        self, provider: OpenRouterProvider, stream_request: LLMRequest
    ) -> None:
        """stream() propaga reasoning_delta quando presente (modelos com thinking)."""
        chunk_data = {
            "choices": [
                {
                    "delta": {"content": "Answer", "reasoning_content": "Thinking..."},
                    "finish_reason": "stop",
                }
            ]
        }
        raw_lines = [f"data: {json.dumps(chunk_data)}", "data: [DONE]"]
        mock_client = self._make_streaming_client(raw_lines)

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            gen = provider.stream(stream_request)
            chunks = await _collect_stream(gen)

        assert chunks[0].delta == "Answer"
        assert chunks[0].reasoning_delta == "Thinking..."

    @pytest.mark.asyncio
    async def test_stream_usage_in_separate_chunk(
        self, provider: OpenRouterProvider, stream_request: LLMRequest
    ) -> None:
        """Quando usage vem em chunk sem choices, é emitido como chunk final."""
        content_chunk = json.dumps({
            "choices": [{"delta": {"content": "Hi"}, "finish_reason": "stop"}]
        })
        usage_chunk = json.dumps({
            "choices": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })
        raw_lines = [
            f"data: {content_chunk}",
            f"data: {usage_chunk}",
            "data: [DONE]",
        ]
        mock_client = self._make_streaming_client(raw_lines)

        with patch("orion.gateway.providers.openrouter.httpx.AsyncClient", return_value=mock_client):
            gen = provider.stream(stream_request)
            chunks = await _collect_stream(gen)

        # Deve haver chunk de conteúdo + chunk de usage
        assert any(c.usage is not None for c in chunks)
        usage_chunks = [c for c in chunks if c.usage is not None]
        assert usage_chunks[0].usage.total_tokens == 15


# ---------------------------------------------------------------------------
# 12. Exceções de Gateway — Hierarquia
# ---------------------------------------------------------------------------


class TestGatewayExceptions:
    def test_gateway_error_is_base(self) -> None:
        assert issubclass(ProviderAPIError, GatewayError)
        assert issubclass(RateLimitError, ProviderAPIError)
        assert issubclass(ProviderTimeoutError, GatewayError)
        assert issubclass(ProviderConnectionError, GatewayError)

    def test_rate_limit_error_attributes(self) -> None:
        err = RateLimitError("Rate limited", retry_after=30.0)
        assert err.status_code == 429
        assert err.retry_after == 30.0

    def test_provider_api_error_attributes(self) -> None:
        err = ProviderAPIError("Bad request", status_code=400)
        assert err.status_code == 400

    def test_timeout_error_message(self) -> None:
        err = ProviderTimeoutError("Timed out after 120s")
        assert "120s" in str(err)
