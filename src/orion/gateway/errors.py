"""
O.R.I.O.N — Exceções de domínio do Gateway (v0.5.0 Sprint 1)

Extraídas de ``providers/openrouter.py`` para serem compartilhadas por todos os
provedores. ``openrouter`` as reexporta (compatibilidade retroativa).
"""

from __future__ import annotations


class GatewayError(Exception):
    """Raiz das exceções do Model Gateway."""


class ProviderAPIError(GatewayError):
    """Erro genérico retornado pelo provedor (autenticação, resposta inválida, etc.)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(ProviderAPIError):
    """Limite de taxa atingido (HTTP 429). Inclui retry_after em segundos, se disponível."""

    def __init__(
        self,
        message: str,
        retry_after: float | None = None,
        *,
        quota_exhausted: bool = False,
        reset_in_s: float | None = None,
    ) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after
        # Cota diária esgotada: esperar segundos não resolve, então não é retentável.
        self.quota_exhausted = quota_exhausted
        self.reset_in_s = reset_in_s


class ProviderTimeoutError(GatewayError):
    """Timeout na chamada ao provedor."""


class ProviderConnectionError(GatewayError):
    """Falha de conexão de rede — sinal para ativar o circuit breaker (Sprint 4)."""


class StreamInterruptedError(GatewayError):
    """Falha DEPOIS de o stream já ter entregue conteúdo ao chamador.

    Não é seguro reiniciar silenciosamente (duplicaria texto/tool_use já
    consumidos); o chamador decide (ex.: motor agêntico reenvia o turno).
    """


class DowngradeBlockedError(GatewayError):
    """Failover exigiria um modelo inferior sem autorização (sem downgrade silencioso)."""


class FailoverExhaustedError(GatewayError):
    """Todos os candidatos permitidos da cadeia de failover falharam."""

