"""
O.R.I.O.N — BaseLLMProvider (v0.3.0 Sprint 1)

Interface abstrata que todo provedor de inferência deve implementar.
Garante que o Gateway seja totalmente agnóstico de provedor.
"""

from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx

from orion.gateway.errors import (
    GatewayError,
    ProviderAPIError,
    ProviderConnectionError,
    ProviderTimeoutError,
    RateLimitError,
    StreamInterruptedError,
)
from orion.gateway.models import (
    ContentBlock,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
    ProviderName,
    TokenUsage,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Retry compartilhado (complete() e stream() de todos os providers)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    """Política de retry com backoff exponencial.

    ``max_attempts`` conta a primeira tentativa. ``jitter`` é fração do atraso.
    """

    max_attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    jitter: float = 0.0

    def delay(self, attempt: int, exc: Exception | None = None) -> float:
        """Atraso antes da próxima tentativa (``attempt`` começa em 0)."""
        wait: float = min(self.base_delay_s * (2**attempt), self.max_delay_s)
        if isinstance(exc, RateLimitError) and exc.retry_after is not None:
            wait = max(wait, exc.retry_after)
        if self.jitter:
            wait += wait * self.jitter * random.random()
        return wait


def is_retryable(exc: BaseException) -> bool:
    """429, 408/409, 5xx (inclui 529 overloaded) e timeouts são transitórios.

    Falha de conexão NÃO é retentada aqui: o failover assume (resposta rápida).
    """
    if isinstance(exc, RateLimitError):
        return not exc.quota_exhausted
    if isinstance(exc, ProviderTimeoutError):
        return True
    if isinstance(exc, ProviderAPIError):
        code = exc.status_code or 0
        return code in (408, 409) or code >= 500
    return False


async def retry_call(
    factory: Callable[[], Awaitable[T]], policy: RetryPolicy, label: str = "provider"
) -> T:
    """Executa ``factory`` com retry de erros transitórios."""
    for attempt in range(policy.max_attempts):
        try:
            return await factory()
        except GatewayError as exc:
            if not is_retryable(exc) or attempt == policy.max_attempts - 1:
                raise
            wait = policy.delay(attempt, exc)
            logger.warning(
                "%s: %s (tentativa %d/%d). Aguardando %.1fs.",
                label, exc, attempt + 1, policy.max_attempts, wait,
            )
            await asyncio.sleep(wait)
    raise RuntimeError("unreachable")  # pragma: no cover


async def stream_with_retry(
    open_stream: Callable[[], AsyncIterator[LLMResponseChunk]],
    policy: RetryPolicy,
    label: str = "provider",
) -> AsyncIterator[LLMResponseChunk]:
    """Reabre o stream em erro transitório ANTES do primeiro chunk.

    Depois que algo foi entregue ao chamador, reiniciar duplicaria conteúdo:
    a falha vira ``StreamInterruptedError`` (quem consome decide o que fazer).
    """
    attempt = 0
    while True:
        started = False
        try:
            async for chunk in open_stream():
                started = True
                yield chunk
            return
        except (GatewayError, httpx.HTTPError) as exc:
            if started:
                if isinstance(exc, StreamInterruptedError):
                    raise
                raise StreamInterruptedError(f"{label}: stream interrompido: {exc}") from exc
            attempt += 1
            gw = exc if isinstance(exc, GatewayError) else ProviderConnectionError(str(exc))
            if not is_retryable(gw) or attempt >= policy.max_attempts:
                raise
            wait = policy.delay(attempt - 1, gw)
            logger.warning(
                "%s: %s (stream, tentativa %d/%d). Aguardando %.1fs.",
                label, gw, attempt, policy.max_attempts, wait,
            )
            await asyncio.sleep(wait)


class StreamAccumulator:
    """Monta um ``LLMResponse`` a partir de chunks tipados (usado por ``complete()``)."""

    def __init__(self) -> None:
        self.blocks: list[ContentBlock] = []
        self.usage = TokenUsage()
        self.stop_reason: str | None = None
        self._text: list[str] = []
        self._reasoning: list[str] = []

    def feed(self, chunk: LLMResponseChunk) -> None:
        if chunk.delta:
            self._text.append(chunk.delta)
        if chunk.reasoning_delta:
            self._reasoning.append(chunk.reasoning_delta)
        if chunk.block is not None:
            self.blocks.append(chunk.block)
        if chunk.usage is not None:
            self.usage = chunk.usage
        if chunk.stop_reason:
            self.stop_reason = chunk.stop_reason

    def build(
        self, model: str, provider: ProviderName, latency_ms: float, request: LLMRequest
    ) -> LLMResponse:
        return LLMResponse(
            content="".join(self._text),
            reasoning_content="".join(self._reasoning) or None,
            blocks=self.blocks,
            stop_reason=self.stop_reason,
            model=model,
            provider=provider,
            usage=self.usage,
            latency_ms=latency_ms,
            complexity_tier=request.complexity_tier,
        )


class BaseLLMProvider(ABC):
    """Interface abstrata para provedores de inferência no ORION Gateway.

    Cada provedor concreto (OpenRouter, Ollama, Anthropic direto, etc.)
    deve implementar ``complete`` e ``stream``.

    O Gateway garante que o contrato seja honrado sem conhecer detalhes
    de autenticação ou formato de API de cada provedor.
    """

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Executa inferência completa (não-streaming).

        Aguarda o modelo terminar de gerar a resposta antes de retornar.
        Use para casos onde o streaming não é necessário ou não é suportado.

        Args:
            request: Requisição normalizada com modelo, mensagens e parâmetros.

        Returns:
            ``LLMResponse`` com conteúdo completo, métricas de uso e latência.

        Raises:
            ProviderAPIError: Erro de autenticação, rate-limit ou resposta inválida.
            RateLimitError: Limite de taxa do provedor atingido (HTTP 429).
            ProviderTimeoutError: Timeout na chamada ao provedor.
        """
        ...

    @abstractmethod
    def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:
        """Streaming assíncrono token a token via SSE (Server-Sent Events).

        Emite ``LLMResponseChunk`` incrementalmente. O chunk final
        (``is_final=True``) contém o ``usage`` completo.

        Args:
            request: Requisição normalizada com ``stream=True``.

        Yields:
            ``LLMResponseChunk`` com delta de texto ou raciocínio.

        Raises:
            ProviderAPIError: Erro durante o stream.
            RateLimitError: Rate-limit detectado no início do stream.
            ProviderTimeoutError: Timeout durante o stream.
        """
        ...

    @property
    def provider_name(self) -> str:
        """Nome legível do provedor para logs e métricas."""
        return self.__class__.__name__
