"""
O.R.I.O.N — Busca web em cadeia (v0.5.3 Sprint 1, ADR-049)

Cada ``SearchProvider`` devolve resultados ou levanta um motivo tipado para a cadeia passar ao
próximo: sem configuração (``SearchUnavailable``) ou recusado pelo serviço (``SearchBlocked``:
429, anti-bot, cota). O primeiro que responder vence e o resultado informa quem respondeu.

Ordem padrão: Brave (``BRAVE_API_KEY``) → ``ddgs`` → SearXNG (``settings.web.searxng_url``) →
DuckDuckGo HTML (reserva sem dependência).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

DEFAULT_ORDER: tuple[str, ...] = ("brave", "ddgs", "searxng", "duckduckgo")
PROVIDER_TIMEOUT = 20.0


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


class SearchUnavailable(Exception):
    """O provedor não está configurado (sem chave, sem URL, biblioteca ausente)."""


class SearchBlocked(Exception):
    """O provedor recusou agora (429, anti-bot, cota, erro de rede): tente o próximo."""


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, count: int) -> list[SearchResult]: ...


@dataclass
class SearchOutcome:
    provider: str | None
    results: list[SearchResult]
    attempts: list[tuple[str, str]] = field(default_factory=list)

    def describe_attempts(self) -> str:
        return "; ".join(f"{name}: {why}" for name, why in self.attempts)


class SearchChain:
    """Tenta os provedores em ordem até um responder (lista vazia também é resposta)."""

    def __init__(self, providers: Sequence[SearchProvider], timeout: float = PROVIDER_TIMEOUT) -> None:
        self._providers = list(providers)
        self._timeout = timeout

    @property
    def names(self) -> list[str]:
        return [p.name for p in self._providers]

    async def search(self, query: str, count: int = 10) -> SearchOutcome:
        attempts: list[tuple[str, str]] = []
        for provider in self._providers:
            try:
                results = await asyncio.wait_for(provider.search(query, count), self._timeout)
            except SearchUnavailable as exc:
                attempts.append((provider.name, f"indisponível ({exc})"))
                continue
            except SearchBlocked as exc:
                attempts.append((provider.name, f"recusou ({exc})"))
                continue
            except TimeoutError:
                attempts.append((provider.name, f"sem resposta em {self._timeout:.0f}s"))
                continue
            except Exception as exc:  # noqa: BLE001 - provedor quebrado não derruba a busca
                logger.warning("search: provedor %s falhou", provider.name, exc_info=True)
                attempts.append((provider.name, f"erro ({type(exc).__name__})"))
                continue
            return SearchOutcome(provider.name, results[:count], attempts)
        return SearchOutcome(None, [], attempts)


def build_chain(
    *,
    brave_key: str | None = None,
    searxng_url: str | None = None,
    order: Sequence[str] = DEFAULT_ORDER,
    transport: object | None = None,
) -> SearchChain:
    """Cadeia padrão a partir da configuração (provedores sem configuração ficam de fora)."""
    from orion.runtime.search.providers import (
        BraveSearch,
        DdgsSearch,
        DuckDuckGoHtmlSearch,
        SearxngSearch,
    )

    available: dict[str, SearchProvider] = {
        "brave": BraveSearch(brave_key, transport=transport),
        "ddgs": DdgsSearch(),
        "searxng": SearxngSearch(searxng_url, transport=transport),
        "duckduckgo": DuckDuckGoHtmlSearch(transport=transport),
    }
    return SearchChain([available[name] for name in order if name in available])


__all__ = [
    "DEFAULT_ORDER",
    "SearchBlocked",
    "SearchChain",
    "SearchOutcome",
    "SearchProvider",
    "SearchResult",
    "SearchUnavailable",
    "build_chain",
]
