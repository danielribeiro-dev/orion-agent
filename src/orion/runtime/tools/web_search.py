"""
O.R.I.O.N — Tool: web_search
Pesquisa na web (DuckDuckGo HTML, sem chave de API) e devolve título, URL e trecho.

ActionLevel: LEVEL_2 (rede de saída)

Resultados são DADOS NÃO CONFIÁVEIS: passam pelos mesmos filtros anti-injeção do web_fetch.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httpx

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool
from orion.runtime.tools.web_policy import label

ENDPOINT = "https://html.duckduckgo.com/html/"
MAX_RESULTS = 10
_RESULT = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'(?:.*?class="result__snippet"[^>]*>(?P<snippet>.*?)</a>)?',
    re.S,
)
_TAGS = re.compile(r"<[^>]+>")


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAGS.sub("", fragment))).strip()


def _real_url(href: str) -> str:
    """Resolve o redirecionador do DuckDuckGo (``//duckduckgo.com/l/?uddg=<url>``)."""
    if "uddg=" in href:
        target = parse_qs(urlsplit(href).query).get("uddg", [""])[0]
        return unquote(target)
    return href


def parse_results(html: str) -> list[dict[str, str]]:
    results = []
    for m in _RESULT.finditer(html):
        results.append(
            {
                "title": _clean(m.group("title")),
                "url": _real_url(unescape(m.group("href"))),
                "snippet": _clean(m.group("snippet") or ""),
            }
        )
    return results


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Search the web. Returns up to 10 results (title, URL, snippet) as UNTRUSTED data. "
        "Use web_fetch to read a result (the domain must be allowlisted)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 2},
            "allowed_domains": {"type": "array", "items": {"type": "string"}},
            "blocked_domains": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["query"],
    }

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def run(
        self,
        query: str,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
        **_: Any,
    ) -> RuntimeResult:
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=httpx.Timeout(20.0),
                headers={"User-Agent": "Mozilla/5.0 (compatible; orion-agent)"},
            ) as client:
                response = await client.post(ENDPOINT, data={"q": query})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            return RuntimeResult.fail(f"web_search: request failed: {type(exc).__name__}: {exc}")

        if response.status_code == 202 or "anomaly" in response.text[:4000].lower():
            return RuntimeResult.fail(
                "web_search: o buscador bloqueou a requisição automatizada (desafio anti-bot, "
                f"HTTP {response.status_code}); isto NÃO significa que não há resultados. "
                "Use web_fetch com uma URL conhecida (domínio na allowlist)."
            )

        def host_matches(url: str, domains: list[str]) -> bool:
            host = (urlsplit(url).hostname or "").lower()
            return any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)

        results = [
            r for r in parse_results(response.text)
            if r["url"].startswith(("http://", "https://"))
            and (not allowed_domains or host_matches(r["url"], allowed_domains))
            and not (blocked_domains and host_matches(r["url"], blocked_domains))
        ][:MAX_RESULTS]
        if not results:
            return RuntimeResult.ok("(no results)", count=0)
        body = "\n\n".join(
            f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}".rstrip()
            for i, r in enumerate(results, 1)
        )
        labelled, removed = label(f"web_search '{query}'", body)
        return RuntimeResult.ok(labelled, count=len(results), suspected_injection=removed > 0)
