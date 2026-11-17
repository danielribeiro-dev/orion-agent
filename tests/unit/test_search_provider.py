"""v0.5.3 Sprint 1 — busca web em cadeia (ADR-049): CA-05 (parte). Sem rede."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from orion.runtime.search import (
    SearchBlocked,
    SearchChain,
    SearchResult,
    SearchUnavailable,
    build_chain,
)
from orion.runtime.search.providers import BraveSearch, DdgsSearch, SearxngSearch
from orion.runtime.tools.web_search import WebSearchTool


class Fake:
    def __init__(self, name: str, outcome: Any) -> None:
        self.name = name
        self.outcome = outcome
        self.calls = 0

    async def search(self, query: str, count: int) -> list[SearchResult]:
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        if self.outcome == "slow":
            await asyncio.sleep(10)
        return list(self.outcome)


HIT = [SearchResult("Python", "https://docs.python.org/3/", "docs")]


class TestChain:
    async def test_first_that_answers_wins(self) -> None:
        a, b, c = Fake("a", SearchUnavailable("sem chave")), Fake("b", HIT), Fake("c", HIT)
        outcome = await SearchChain([a, b, c]).search("x")
        assert outcome.provider == "b" and outcome.results == HIT and c.calls == 0
        assert outcome.attempts == [("a", "indisponível (sem chave)")]

    async def test_blocked_errors_and_timeouts_pass_to_the_next(self) -> None:
        chain = SearchChain(
            [Fake("a", SearchBlocked("HTTP 429")), Fake("b", RuntimeError("bug")), Fake("c", "slow"), Fake("d", HIT)],
            timeout=0.05,
        )
        outcome = await chain.search("x")
        assert outcome.provider == "d"
        assert [name for name, _ in outcome.attempts] == ["a", "b", "c"]
        assert "recusou" in outcome.describe_attempts() and "sem resposta" in outcome.describe_attempts()

    async def test_empty_list_is_an_answer(self) -> None:
        outcome = await SearchChain([Fake("a", []), Fake("b", HIT)]).search("x")
        assert outcome.provider == "a" and outcome.results == []

    async def test_nobody_answers(self) -> None:
        outcome = await SearchChain([Fake("a", SearchUnavailable("x"))]).search("q")
        assert outcome.provider is None and outcome.results == []

    def test_default_order_and_custom_order(self) -> None:
        assert build_chain().names == ["brave", "ddgs", "searxng", "duckduckgo"]
        assert build_chain(order=["searxng", "nada", "brave"]).names == ["searxng", "brave"]


class TestBrave:
    async def test_without_key_is_unavailable(self) -> None:
        with pytest.raises(SearchUnavailable):
            await BraveSearch(None).search("x", 5)

    async def test_parses_results_and_sends_key_header(self) -> None:
        seen: dict[str, Any] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            seen["key"] = req.headers.get("X-Subscription-Token")
            seen["q"] = req.url.params.get("q")
            body = {"web": {"results": [{"title": "<b>Py</b>", "url": "https://py.org", "description": "d"}]}}
            return httpx.Response(200, json=body)

        results = await BraveSearch("k-123", transport=httpx.MockTransport(handler)).search("python", 5)
        assert results == [SearchResult("Py", "https://py.org", "d")]
        assert seen == {"key": "k-123", "q": "python"}

    @pytest.mark.parametrize(("status", "exc"), [(429, SearchBlocked), (503, SearchBlocked), (401, SearchUnavailable)])
    async def test_refusals(self, status: int, exc: type[Exception]) -> None:
        t = httpx.MockTransport(lambda r: httpx.Response(status))
        with pytest.raises(exc):
            await BraveSearch("k", transport=t).search("x", 5)

    async def test_network_error_and_bad_json(self) -> None:
        def boom(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        with pytest.raises(SearchBlocked):
            await BraveSearch("k", transport=httpx.MockTransport(boom)).search("x", 5)
        with pytest.raises(SearchBlocked):
            await BraveSearch("k", transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>"))).search("x", 5)


class TestSearxng:
    async def test_without_url_is_unavailable(self) -> None:
        with pytest.raises(SearchUnavailable):
            await SearxngSearch(None).search("x", 5)

    async def test_parses_json(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            assert req.url.path == "/search" and req.url.params["format"] == "json"
            return httpx.Response(200, json={"results": [{"title": "T", "url": "https://t.io", "content": "c"}]})

        results = await SearxngSearch("http://localhost:8888/", transport=httpx.MockTransport(handler)).search("x", 5)
        assert results == [SearchResult("T", "https://t.io", "c")]

    async def test_html_instead_of_json(self) -> None:
        t = httpx.MockTransport(lambda r: httpx.Response(200, text="<html>"))
        with pytest.raises(SearchBlocked, match="format=json"):
            await SearxngSearch("http://s", transport=t).search("x", 5)


class TestDdgs:
    async def test_uses_library_results(self) -> None:
        class Engine:
            def text(self, query: str, max_results: int) -> list[dict[str, str]]:
                return [{"title": "A", "href": "https://a.io", "body": "b"}, {"title": "sem url"}]

        results = await DdgsSearch(factory=Engine).search("x", 5)
        assert results == [SearchResult("A", "https://a.io", "b")]

    async def test_rate_limit_becomes_blocked(self) -> None:
        class Engine:
            def text(self, query: str, max_results: int) -> list[dict[str, str]]:
                raise RuntimeError("Ratelimit")

        with pytest.raises(SearchBlocked):
            await DdgsSearch(factory=Engine).search("x", 5)

    async def test_tests_never_touch_the_real_library(self) -> None:
        with pytest.raises(SearchUnavailable):
            await DdgsSearch().search("x", 5)


class TestToolIntegration:
    async def test_reports_provider_and_falls_back(self, tmp_path: Path) -> None:
        chain = SearchChain([Fake("brave", SearchUnavailable("sem chave")), Fake("ddgs", HIT)])
        result = await WebSearchTool(chain=chain, home=tmp_path).run(query="python")
        assert result.success and result.metadata["provider"] == "ddgs"
        assert "via ddgs" in result.output and "docs.python.org" in result.output

    async def test_all_fail_explains_how_to_fix(self, tmp_path: Path) -> None:
        chain = SearchChain([Fake("brave", SearchUnavailable("sem chave")), Fake("ddgs", SearchBlocked("429"))])
        result = await WebSearchTool(chain=chain, home=tmp_path).run(query="python")
        assert not result.success
        assert "BRAVE_API_KEY" in (result.error or "") and "NÃO significa" in (result.error or "")

    async def test_brave_key_comes_from_env_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        tool = WebSearchTool(env_reader=lambda: {"BRAVE_API_KEY": "do-env"}, home=tmp_path)
        assert tool._brave_key() == "do-env"
        (tmp_path / ".env").write_text("BRAVE_API_KEY=do-arquivo\n")
        assert WebSearchTool(home=tmp_path)._brave_key() == "do-arquivo"
        monkeypatch.setenv("BRAVE_API_KEY", "do-shell")
        assert WebSearchTool(home=tmp_path)._brave_key() == "do-shell"

    async def test_configure_applies_settings(self, tmp_path: Path) -> None:
        seen: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            seen.append(str(req.url))
            return httpx.Response(200, content=json.dumps({"results": []}).encode())

        tool = WebSearchTool(transport=httpx.MockTransport(handler), env_reader=dict, home=tmp_path)
        tool.configure(searxng_url="http://searx.local", order=["searxng"], home=tmp_path)
        result = await tool.run(query="x")
        assert result.success and result.metadata["provider"] == "searxng"
        assert seen and seen[0].startswith("http://searx.local/search")
