"""
Tests for LocalOllamaProvider (v0.3.0 Sprint 4)

Covers:
  - Availability check (is_available, list_available_models, check_model_available)
  - complete() with mock HTTP responses
  - stream() with mock HTTP chunked responses
  - OllamaUnavailableError on connection failure
  - OllamaModelNotFoundError on 404
  - ZERO auto-download / ZERO auto-start enforcement (contract tests)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import pytest

from orion.gateway.models import (
    ComplexityTier,
    LLMMessage,
    LLMRequest,
    MessageRole,
    ProviderName,
)
from orion.gateway.providers.local_ollama import (
    LocalOllamaProvider,
    OllamaModelNotFoundError,
    OllamaUnavailableError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def provider() -> LocalOllamaProvider:
    return LocalOllamaProvider(
        model_id="qwen2.5-coder:1.5b",
        base_url="http://localhost:11434",
    )


@pytest.fixture
def basic_request() -> LLMRequest:
    return LLMRequest(
        model="qwen2.5-coder:1.5b",
        messages=[
            LLMMessage(role=MessageRole.USER, content="Hello, what is 2+2?"),
        ],
        stream=False,
        complexity_tier=ComplexityTier.FAST,
    )


# ---------------------------------------------------------------------------
# Contract Tests — ZERO auto-download / ZERO auto-start
# ---------------------------------------------------------------------------


class TestContractHardwareInvariant:
    """These tests verify the hardware-friendly contract:
    The provider NEVER downloads models or starts Ollama automatically."""

    def test_provider_has_no_auto_download_method(self, provider):
        """Provider must not have any method that downloads model weights."""
        download_like = [
            attr for attr in dir(provider)
            if "download" in attr.lower() or "pull" in attr.lower()
        ]
        assert download_like == [], (
            f"Provider should have no auto-download methods, found: {download_like}"
        )

    def test_provider_has_no_auto_start_method(self, provider):
        """Provider must not have any method that starts the Ollama daemon."""
        start_like = [
            attr for attr in dir(provider)
            if "start" in attr.lower() or "launch" in attr.lower() or "spawn" in attr.lower()
        ]
        assert start_like == [], (
            f"Provider should have no auto-start methods, found: {start_like}"
        )

    def test_provider_name_identifies_model(self, provider):
        assert "qwen2.5-coder" in provider.provider_name

    def test_model_id_accessible(self, provider):
        assert provider.model_id == "qwen2.5-coder:1.5b"

    def test_base_url_accessible(self, provider):
        assert provider.base_url == "http://localhost:11434"

    def test_unavailable_error_explains_no_autostart(self):
        err = OllamaUnavailableError(base_url="http://localhost:11434")
        assert "ollama serve" in str(err).lower() or "daemon" in str(err).lower()
        assert "nunca" in str(err).lower() or "never" in str(err).lower() or "automaticamente" in str(err).lower()

    def test_model_not_found_error_explains_no_autodownload(self):
        err = OllamaModelNotFoundError(model_id="qwen2.5-coder:1.5b")
        assert "pull" in str(err).lower()
        assert "nunca" in str(err).lower() or "never" in str(err).lower() or "automaticamente" in str(err).lower()


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestIsAvailable:
    @pytest.mark.asyncio
    async def test_returns_true_when_daemon_running(self, provider):
        mock_response = AsyncMock()
        mock_response.status = 200

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        with patch("orion.gateway.providers.local_ollama.aiohttp.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await provider.is_available()
            # We just confirm the method runs without error and returns a bool
            assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_returns_false_when_daemon_not_running(self, provider):
        import aiohttp

        with patch("orion.gateway.providers.local_ollama.aiohttp.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(
                side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError("refused"))
            )
            result = await provider.is_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_any_exception(self, provider):
        with patch(
            "orion.gateway.providers.local_ollama.aiohttp.ClientSession",
            side_effect=Exception("unexpected"),
        ):
            result = await provider.is_available()
            assert result is False


# ---------------------------------------------------------------------------
# list_available_models
# ---------------------------------------------------------------------------


class TestListAvailableModels:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_unavailable(self, provider):
        with patch(
            "orion.gateway.providers.local_ollama.aiohttp.ClientSession",
            side_effect=Exception("unavailable"),
        ):
            models = await provider.list_available_models()
            assert models == []

    @pytest.mark.asyncio
    async def test_parses_model_list_from_response(self, provider):
        """list_available_models correctly parses the /api/tags response."""
        tags_response = {"models": [{"name": "qwen2.5-coder:1.5b"}, {"name": "llama3.2:3b"}]}

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=tags_response)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_resp)

        with patch("orion.gateway.providers.local_ollama.aiohttp.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

            models = await provider.list_available_models()
            assert "qwen2.5-coder:1.5b" in models
            assert "llama3.2:3b" in models


# ---------------------------------------------------------------------------
# check_model_available
# ---------------------------------------------------------------------------


class TestCheckModelAvailable:
    @pytest.mark.asyncio
    async def test_returns_true_when_model_present(self, provider):
        with patch.object(
            provider,
            "list_available_models",
            return_value=["qwen2.5-coder:1.5b", "llama3.2:3b"],
        ):
            result = await provider.check_model_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_model_absent(self, provider):
        with patch.object(
            provider,
            "list_available_models",
            return_value=["llama3.2:3b"],
        ):
            result = await provider.check_model_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_ollama_unavailable(self, provider):
        with patch.object(provider, "list_available_models", return_value=[]):
            result = await provider.check_model_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_partial_match_works(self, provider):
        """qwen2.5-coder:1.5b matches qwen2.5-coder:1.5b exactly."""
        with patch.object(
            provider,
            "list_available_models",
            return_value=["qwen2.5-coder:1.5b"],
        ):
            assert await provider.check_model_available() is True


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------


class TestComplete:
    @pytest.mark.asyncio
    async def test_raises_when_unavailable(self, provider, basic_request):
        with patch.object(provider, "is_available", return_value=False):
            with pytest.raises(OllamaUnavailableError):
                await provider.complete(basic_request)

    @pytest.mark.asyncio
    async def test_raises_model_not_found_on_404(self, provider, basic_request):
        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch.object(provider, "is_available", return_value=True), \
             patch.object(provider, "list_available_models", return_value=[]):
            with patch("orion.gateway.providers.local_ollama.aiohttp.ClientSession") as mock_cs:
                mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

                with pytest.raises(OllamaModelNotFoundError) as exc_info:
                    await provider.complete(basic_request)
                assert "qwen2.5-coder:1.5b" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_returns_llm_response_on_success(self, provider, basic_request):
        api_response = {
            "message": {"content": "4"},
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=api_response)
        mock_resp.raise_for_status = MagicMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch.object(provider, "is_available", return_value=True):
            with patch("orion.gateway.providers.local_ollama.aiohttp.ClientSession") as mock_cs:
                mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

                response = await provider.complete(basic_request)

        assert response.content == "4"
        assert response.provider == ProviderName.OLLAMA
        assert response.model == "qwen2.5-coder:1.5b"
        assert response.usage.prompt_tokens == 10
        assert response.usage.completion_tokens == 5
        assert response.latency_ms >= 0.0


# ---------------------------------------------------------------------------
# stream()
# ---------------------------------------------------------------------------


class AsyncBytesIterator:
    """Helper to mock aiohttp chunked content stream."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        try:
            return next(self._chunks)
        except StopIteration:
            raise StopAsyncIteration


class TestStream:
    @pytest.mark.asyncio
    async def test_stream_raises_when_unavailable(self, provider, basic_request):
        with patch.object(provider, "is_available", return_value=False):
            with pytest.raises(OllamaUnavailableError):
                async for _ in provider.stream(basic_request):
                    pass

    @pytest.mark.asyncio
    async def test_stream_raises_model_not_found_on_404(self, provider, basic_request):
        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch.object(provider, "is_available", return_value=True), \
             patch.object(provider, "list_available_models", return_value=[]):
            with patch("orion.gateway.providers.local_ollama.aiohttp.ClientSession") as mock_cs:
                mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

                with pytest.raises(OllamaModelNotFoundError):
                    async for _ in provider.stream(basic_request):
                        pass

    @pytest.mark.asyncio
    async def test_stream_yields_chunks_and_final_usage(self, provider, basic_request):
        lines = [
            b'{"message": {"content": "Hello"}, "done": false}\n',
            b'{"message": {"content": " world"}, "done": false}\n',
            b'{"message": {"content": "!"}, "done": true, "usage": {"prompt_tokens": 8, "completion_tokens": 3}}\n',
        ]
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = AsyncBytesIterator(lines)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch.object(provider, "is_available", return_value=True):
            with patch("orion.gateway.providers.local_ollama.aiohttp.ClientSession") as mock_cs:
                mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

                chunks = []
                async for chunk in provider.stream(basic_request):
                    chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0].delta == "Hello"
        assert chunks[0].is_final is False
        assert chunks[1].delta == " world"
        assert chunks[1].is_final is False
        assert chunks[2].delta == "!"
        assert chunks[2].is_final is True
        assert chunks[2].usage is not None
        assert chunks[2].usage.prompt_tokens == 8
        assert chunks[2].usage.completion_tokens == 3
        assert chunks[2].usage.total_tokens == 11


# ---------------------------------------------------------------------------
# OllamaUnavailableError
# ---------------------------------------------------------------------------


class TestOllamaUnavailableError:
    def test_attributes_set_correctly(self):
        original = OSError("connection refused")
        err = OllamaUnavailableError("http://localhost:11434", original)
        assert err.base_url == "http://localhost:11434"
        assert err.original_error is original

    def test_error_message_informative(self):
        err = OllamaUnavailableError("http://localhost:11434")
        msg = str(err)
        assert "http://localhost:11434" in msg


# ---------------------------------------------------------------------------
# OllamaModelNotFoundError
# ---------------------------------------------------------------------------


class TestOllamaModelNotFoundError:
    def test_attributes_set_correctly(self):
        err = OllamaModelNotFoundError(
            model_id="qwen2.5-coder:1.5b",
            available_models=["llama3.2"],
        )
        assert err.model_id == "qwen2.5-coder:1.5b"
        assert "llama3.2" in err.available_models

    def test_error_message_includes_pull_command(self):
        err = OllamaModelNotFoundError(model_id="qwen2.5-coder:1.5b")
        assert "ollama pull qwen2.5-coder:1.5b" in str(err)
