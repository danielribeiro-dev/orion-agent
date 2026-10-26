"""
O.R.I.O.N — BaseLLMProvider (v0.3.0 Sprint 1)

Interface abstrata que todo provedor de inferência deve implementar.
Garante que o Gateway seja totalmente agnóstico de provedor.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from orion.gateway.models import LLMRequest, LLMResponse, LLMResponseChunk


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
