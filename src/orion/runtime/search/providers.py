"""Provedores da cadeia de busca (ADR-049): Brave API, ddgs, SearXNG e DuckDuckGo HTML."""

from __future__ import annotations

import asyncio
import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httpx

from orion.runtime.search import SearchBlocked, SearchResult, SearchUnavailable

API_USER_AGENT = "orion-agent/0.5 (+local)"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
DDG_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
_TAGS = re.compile(r"<[^>]+>")
_DDG_RESULT = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'(?:.*?class="result__snippet"[^>]*>(?P<snippet>.*?)</a>)?',
    re.S,
)


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAGS.sub("", fragment or ""))).strip()


def _client(transport: Any, user_agent: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(15.0),
        headers={"User-Agent": user_agent, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"},
        follow_redirects=True,
    )


def _raise_for_refusal(response: httpx.Response) -> None:
    if response.status_code in (401, 403):
        raise SearchUnavailable(f"HTTP {response.status_code}: chave recusada")
    if response.status_code == 429 or response.status_code >= 500:
        raise SearchBlocked(f"HTTP {response.status_code}")
    if response.status_code >= 400:
        raise SearchBlocked(f"HTTP {response.status_code}")


class BraveSearch:
    """Brave Search API (plano gratuito com chave em ``BRAVE_API_KEY``)."""

    name = "brave"

    def __init__(self, api_key: str | None, transport: Any = None) -> None:
        self._key = (api_key or "").strip()
        self._transport = transport

    async def search(self, query: str, count: int) -> list[SearchResult]:
        if not self._key:
            raise SearchUnavailable("sem BRAVE_API_KEY")
        try:
            async with _client(self._transport, API_USER_AGENT) as client:
                response = await client.get(
                    BRAVE_ENDPOINT,
                    params={"q": query, "count": min(count, 20)},
                    headers={"Accept": "application/json", "X-Subscription-Token": self._key},
                )
        except httpx.HTTPError as exc:
            raise SearchBlocked(type(exc).__name__) from exc
        _raise_for_refusal(response)
        try:
            items = response.json().get("web", {}).get("results", []) or []
        except ValueError as exc:
            raise SearchBlocked("resposta inválida") from exc
        return [
            SearchResult(_clean(i.get("title", "")), str(i.get("url", "")), _clean(i.get("description", "")))
            for i in items
            if i.get("url")
        ]


class DdgsSearch:
    """Biblioteca ``ddgs`` (metabusca sem chave)."""

    name = "ddgs"

    def __init__(self, factory: Any = None) -> None:
        self._factory = factory

    def _make(self) -> Any:
        if self._factory is not None:
            return self._factory()
        try:
            from ddgs import DDGS
        except ImportError as exc:
            raise SearchUnavailable("biblioteca ddgs não instalada") from exc
        return DDGS(timeout=12)

    async def search(self, query: str, count: int) -> list[SearchResult]:
        engine = self._make()

        def run() -> list[dict[str, Any]]:
            return list(engine.text(query, max_results=count) or [])

        try:
            rows = await asyncio.to_thread(run)
        except SearchUnavailable:
            raise
        except Exception as exc:  # ddgs levanta RatelimitException/DDGSException/TimeoutException
            raise SearchBlocked(type(exc).__name__) from exc
        return [
            SearchResult(_clean(str(r.get("title", ""))), str(r.get("href") or r.get("url") or ""), _clean(str(r.get("body", ""))))
            for r in rows
            if r.get("href") or r.get("url")
        ]


class SearxngSearch:
    """Instância SearXNG do Senhor (``settings.web.searxng_url``), API JSON."""

    name = "searxng"

    def __init__(self, base_url: str | None, transport: Any = None) -> None:
        self._base = (base_url or "").strip().rstrip("/")
        self._transport = transport

    async def search(self, query: str, count: int) -> list[SearchResult]:
        if not self._base:
            raise SearchUnavailable("sem settings.web.searxng_url")
        try:
            async with _client(self._transport, API_USER_AGENT) as client:
                response = await client.get(
                    f"{self._base}/search", params={"q": query, "format": "json"}
                )
        except httpx.HTTPError as exc:
            raise SearchBlocked(type(exc).__name__) from exc
        _raise_for_refusal(response)
        try:
            items = response.json().get("results", []) or []
        except ValueError as exc:
            raise SearchBlocked("resposta não é JSON (format=json habilitado?)") from exc
        return [
            SearchResult(_clean(i.get("title", "")), str(i.get("url", "")), _clean(i.get("content", "")))
            for i in items[:count]
            if i.get("url")
        ]


def _ddg_real_url(href: str) -> str:
    """Resolve o redirecionador do DuckDuckGo (``//duckduckgo.com/l/?uddg=<url>``)."""
    if "uddg=" in href:
        target = parse_qs(urlsplit(href).query).get("uddg", [""])[0]
        return unquote(target)
    return href


def parse_ddg_html(html: str) -> list[SearchResult]:
    return [
        SearchResult(
            _clean(m.group("title")),
            _ddg_real_url(unescape(m.group("href"))),
            _clean(m.group("snippet") or ""),
        )
        for m in _DDG_RESULT.finditer(html)
    ]


class DuckDuckGoHtmlSearch:
    """Raspagem do HTML do DuckDuckGo: última reserva, sujeita a anti-bot."""

    name = "duckduckgo"

    def __init__(self, transport: Any = None) -> None:
        self._transport = transport

    async def search(self, query: str, count: int) -> list[SearchResult]:
        try:
            async with _client(self._transport, BROWSER_USER_AGENT) as client:
                response = await client.post(DDG_HTML_ENDPOINT, data={"q": query})
        except httpx.HTTPError as exc:
            raise SearchBlocked(type(exc).__name__) from exc
        if response.status_code == 202 or "anomaly" in response.text[:4000].lower():
            raise SearchBlocked(f"desafio anti-bot (HTTP {response.status_code})")
        _raise_for_refusal(response)
        return parse_ddg_html(response.text)[:count]
