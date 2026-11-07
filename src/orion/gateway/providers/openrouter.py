"""
O.R.I.O.N — OpenRouter Provider (v0.3.0 Sprint 1)

Conector de primeira classe para o OpenRouter (https://openrouter.ai).
Suporta:
  - Streaming SSE assíncrono token a token.
  - Extração de métricas de uso (prompt/completion/cached/reasoning tokens).
  - Backoff exponencial com jitter em erros 429 e 5xx.
  - Exceções tipadas de domínio (ProviderAPIError, RateLimitError, etc.).

Dependência: ``httpx`` (já no pyproject.toml como dep de produção).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator, Optional

import httpx

from orion.gateway.models import (
    ComplexityTier,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
    ProviderName,
    TokenUsage,
)
from orion.gateway.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceções de Domínio do Gateway
# ---------------------------------------------------------------------------


class GatewayError(Exception):
    """Raiz das exceções do Model Gateway."""


class ProviderAPIError(GatewayError):
    """Erro genérico retornado pelo provedor (autenticação, resposta inválida, etc.)."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(ProviderAPIError):
    """Limite de taxa atingido (HTTP 429). Inclui retry_after em segundos, se disponível."""

    def __init__(self, message: str, retry_after: Optional[float] = None) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class ProviderTimeoutError(GatewayError):
    """Timeout na chamada ao provedor."""


class ProviderConnectionError(GatewayError):
    """Falha de conexão de rede — sinal para ativar o circuit breaker (Sprint 4)."""


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_CHAT_COMPLETIONS_PATH = "/chat/completions"

# Cabeçalhos de identificação requeridos pelo OpenRouter
_APP_TITLE = "ORION-Agent"
_APP_URL = "https://github.com/orion-agent/orion"

# Tentativas de backoff exponencial para 429 / 5xx
_MAX_RETRIES = 3
_BACKOFF_BASE_S = 1.0  # segundos base do backoff
_BACKOFF_MAX_S = 30.0  # teto máximo do backoff


# ---------------------------------------------------------------------------
# OpenRouterProvider
# ---------------------------------------------------------------------------


class OpenRouterProvider(BaseLLMProvider):
    """Provedor primário do ORION Gateway — OpenRouter API v1.

    OpenRouter expõe uma interface compatível com a API Chat Completions
    da OpenAI, aceitando centenas de modelos sob uma única chave de API.

    Streaming é implementado via SSE (Server-Sent Events) com linhas
    ``data: {...}`` seguidas de ``data: [DONE]``.

    Args:
        api_key: Chave de API do OpenRouter (prefixo ``sk-or-v1-...``).
        base_url: URL base da API (padrão: ``https://openrouter.ai/api/v1``).
        timeout_s: Timeout total da requisição em segundos (padrão: 120).
        http_referer: Referer enviado nos headers (para ranking do OpenRouter).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = _OPENROUTER_BASE_URL,
        timeout_s: float = 120.0,
        http_referer: str = _APP_URL,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("OpenRouter API key cannot be empty.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._http_referer = http_referer

    # ── Headers ──────────────────────────────────────────────────────────────

    def _build_headers(self) -> dict[str, str]:
        """Constrói os headers HTTP necessários para o OpenRouter."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._http_referer,
            "X-Title": _APP_TITLE,
        }

    # ── Serialização ─────────────────────────────────────────────────────────

    def _serialize_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """Converte ``LLMMessage`` para o formato dict da API OpenAI-compatible."""
        serialized = []
        for msg in messages:
            d: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
            if msg.name is not None:
                d["name"] = msg.name
            serialized.append(d)
        return serialized

    def _build_payload(self, request: LLMRequest, stream: bool) -> dict[str, Any]:
        """Monta o payload JSON para a API do OpenRouter."""
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": self._serialize_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
        # Inclui parâmetros extras passados pelo caller (ex: top_p, seed)
        if request.extra_params:
            payload.update(request.extra_params)
        return payload

    # ── Parsing de Usage ─────────────────────────────────────────────────────

    @staticmethod
    def _parse_usage(usage_dict: Optional[dict[str, Any]]) -> TokenUsage:
        """Extrai ``TokenUsage`` do campo ``usage`` da resposta do OpenRouter."""
        if not usage_dict:
            return TokenUsage()
        prompt_tokens = usage_dict.get("prompt_tokens", 0)
        completion_tokens = usage_dict.get("completion_tokens", 0)
        total_tokens = usage_dict.get("total_tokens", prompt_tokens + completion_tokens)

        # OpenRouter pode retornar prompt_tokens_details com cached_tokens
        details = usage_dict.get("prompt_tokens_details") or {}
        cached_tokens = details.get("cached_tokens", 0)

        # Reasoning tokens (DeepSeek R1, Claude 3.7+)
        completion_details = usage_dict.get("completion_tokens_details") or {}
        reasoning_tokens = completion_details.get("reasoning_tokens", 0)

        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=total_tokens,
        )

    # ── Tratamento de Erros HTTP ──────────────────────────────────────────────

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Lança exceção tipada baseada no status HTTP da resposta."""
        if response.status_code == 200:
            return
        if response.status_code == 429:
            retry_after: Optional[float] = None
            ra_header = response.headers.get("Retry-After")
            if ra_header is not None:
                try:
                    retry_after = float(ra_header)
                except ValueError:
                    pass
            raise RateLimitError(
                f"OpenRouter rate limit exceeded. Retry-After: {retry_after}s",
                retry_after=retry_after,
            )
        if response.status_code == 401:
            raise ProviderAPIError(
                "OpenRouter authentication failed. Check your API key.",
                status_code=401,
            )
        if response.status_code == 402:
            raise ProviderAPIError(
                "OpenRouter insufficient credits. Top up your account.",
                status_code=402,
            )
        if response.status_code >= 500:
            raise ProviderAPIError(
                f"OpenRouter server error {response.status_code}: {response.text[:200]}",
                status_code=response.status_code,
            )
        raise ProviderAPIError(
            f"OpenRouter unexpected status {response.status_code}: {response.text[:200]}",
            status_code=response.status_code,
        )

    # ── complete() ────────────────────────────────────────────────────────────

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Executa inferência completa (não-streaming) no OpenRouter.

        Inclui retry automático com backoff exponencial para 429 e 5xx.
        """
        url = f"{self._base_url}{_CHAT_COMPLETIONS_PATH}"
        headers = self._build_headers()
        payload = self._build_payload(request, stream=False)

        last_error: Exception = RuntimeError("No attempts made")

        for attempt in range(_MAX_RETRIES):
            try:
                t0 = time.monotonic()
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    response = await client.post(url, headers=headers, json=payload)

                self._raise_for_status(response)
                latency_ms = (time.monotonic() - t0) * 1000.0

                data = response.json()
                choice = data["choices"][0]
                message = choice.get("message", {})
                content = message.get("content") or ""

                # Raciocínio interno (DeepSeek R1, Claude Extended Thinking)
                reasoning_content: Optional[str] = message.get("reasoning_content")

                usage = self._parse_usage(data.get("usage"))

                return LLMResponse(
                    content=content,
                    reasoning_content=reasoning_content,
                    model=data.get("model", request.model),
                    provider=ProviderName.OPENROUTER,
                    usage=usage,
                    latency_ms=latency_ms,
                    complexity_tier=request.complexity_tier,
                )

            except RateLimitError as exc:
                last_error = exc
                wait = min(_BACKOFF_BASE_S * (2**attempt), _BACKOFF_MAX_S)
                if exc.retry_after is not None:
                    wait = max(wait, exc.retry_after)
                logger.warning(
                    "OpenRouter rate limit on attempt %d/%d. Waiting %.1fs.",
                    attempt + 1,
                    _MAX_RETRIES,
                    wait,
                )
                import asyncio
                await asyncio.sleep(wait)

            except ProviderAPIError:
                raise  # Não retenta erros de autenticação, crédito etc.

            except httpx.TimeoutException as exc:
                last_error = ProviderTimeoutError(
                    f"OpenRouter timeout after {self._timeout_s}s on attempt {attempt + 1}"
                )
                logger.warning(str(last_error))
                if attempt == _MAX_RETRIES - 1:
                    raise ProviderTimeoutError(str(last_error)) from exc

            except httpx.ConnectError as exc:
                raise ProviderConnectionError(
                    f"OpenRouter connection failed: {exc}"
                ) from exc

        raise last_error  # type: ignore[misc]

    # ── stream() ──────────────────────────────────────────────────────────────

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:  # type: ignore[override]
        """Streaming SSE assíncrono token a token via OpenRouter.

        Yields:
            ``LLMResponseChunk`` com delta de texto. O chunk final
            (``is_final=True``) carrega o ``usage`` completo.
        """
        url = f"{self._base_url}{_CHAT_COMPLETIONS_PATH}"
        headers = self._build_headers()
        payload = self._build_payload(request, stream=True)

        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    # Trata erros HTTP antes de iniciar o streaming
                    if response.status_code != 200:
                        await response.aread()  # consome o body para poder ler o texto
                        self._raise_for_status(response)

                    # Itera linha a linha sobre os eventos SSE
                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()

                        # Linhas vazias são separadores SSE — ignorar
                        if not line:
                            continue

                        # Prefixo "data: " é o padrão SSE
                        if not line.startswith("data:"):
                            continue

                        data_str = line[len("data:"):].strip()

                        # Sentinel de fim de stream
                        if data_str == "[DONE]":
                            break

                        # Parse do chunk JSON
                        try:
                            chunk_data = json.loads(data_str)
                        except json.JSONDecodeError:
                            logger.debug("Skipping non-JSON SSE line: %s", data_str[:80])
                            continue

                        choices = chunk_data.get("choices", [])
                        if not choices:
                            # Pode ser um chunk de usage final sem choices
                            usage_dict = chunk_data.get("usage")
                            if usage_dict:
                                usage = self._parse_usage(usage_dict)
                                yield LLMResponseChunk(
                                    delta="",
                                    is_final=True,
                                    usage=usage,
                                )
                            continue

                        choice = choices[0]
                        delta = choice.get("delta", {})
                        text_delta: str = delta.get("content") or ""
                        reasoning_delta: Optional[str] = delta.get("reasoning_content") or delta.get("reasoning")
                        finish_reason: Optional[str] = choice.get("finish_reason")

                        is_final = finish_reason is not None

                        # Usage pode vir no chunk final
                        usage_dict = chunk_data.get("usage")
                        usage = self._parse_usage(usage_dict) if (is_final and usage_dict) else None

                        yield LLMResponseChunk(
                            delta=text_delta,
                            reasoning_delta=reasoning_delta,
                            is_final=is_final,
                            usage=usage,
                        )

        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"OpenRouter stream timeout after {self._timeout_s}s"
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError(
                f"OpenRouter stream connection failed: {exc}"
            ) from exc

    @property
    def provider_name(self) -> str:
        return "OpenRouter"
