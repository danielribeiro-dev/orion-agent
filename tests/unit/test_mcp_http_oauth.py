"""MCP 5B: streamable HTTP, headers, OAuth/PKCE, resources, prompts, list_changed, reconexão.

Usa um servidor MCP real (``tests/fixtures/mcp_http_server.py``) em subprocesso,
sem rede externa e sem custo.
"""

from __future__ import annotations

import asyncio
import io
import json
import socket
import stat
import subprocess
import sys
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import httpx
import pytest
from rich.console import Console

from orion.core.events import Action
from orion.governance.permissions import ActionLevel
from orion.mcp.adapter import build_adapters, build_resource_tools
from orion.mcp.client import MCPClient, load_server_configs
from orion.mcp.models import MCPServerConfig
from orion.mcp.oauth import FileTokenStorage, LoopbackCallback, auth_file
from orion.mcp.spawn_policy import SpawnDenied, check_remote_url
from orion.mcp.transports import MissingEnvVar, expand_env, expand_headers, server_log_path
from orion.tui.commands import CommandContext, CommandRegistry
from orion.tui.commands.mcp import parse_add
from orion.tui.session import AgentMode, AgentSession
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme
from tests.unit.test_agent_session import ScriptedProvider, call

SERVER = Path(__file__).parents[1] / "fixtures" / "mcp_http_server.py"


def _free_port() -> int:
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class FakeServer:
    def __init__(self, port: int, oauth: bool) -> None:
        self.port, self.oauth = port, oauth
        self.proc: subprocess.Popen[bytes] | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/mcp"

    def start(self) -> None:
        args = [sys.executable, str(SERVER), str(self.port)] + (["oauth"] if self.oauth else [])
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                with closing(socket.create_connection(("127.0.0.1", self.port), timeout=0.3)):
                    return
            except OSError:
                time.sleep(0.1)
        self.stop()
        raise RuntimeError("servidor MCP falso não subiu")

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


@pytest.fixture
def server() -> Iterator[FakeServer]:
    fake = FakeServer(_free_port(), oauth=False)
    fake.start()
    yield fake
    fake.stop()


@pytest.fixture
def oauth_server() -> Iterator[FakeServer]:
    fake = FakeServer(_free_port(), oauth=True)
    fake.start()
    yield fake
    fake.stop()


def _cfg(server: FakeServer, **extra: Any) -> dict[str, MCPServerConfig]:
    return {"docs": MCPServerConfig(name="docs", transport="http", url=server.url, **extra)}


@pytest.fixture
async def client(server: FakeServer, tmp_path: Path) -> AsyncIterator[MCPClient]:
    mcp = MCPClient(_cfg(server), home=tmp_path / "home", ping_interval=0.3, backoff_base=0.1)
    await mcp.start()
    yield mcp
    await mcp.close()


async def _until(predicate: Callable[[], bool], timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


# ── transporte HTTP, headers, política de URL ───────────────────────────────


class TestHttpTransport:
    async def test_conecta_e_lista_tools_resources_prompts(self, client: MCPClient) -> None:
        state = client.servers["docs"]
        assert state.status == "connected", state.error
        assert {"echo", "seen_header", "add_extra_tool"} <= {t.name for t in state.tools}
        assert [r.uri for r in state.resources] == ["docs://guide"]
        assert [p.name for p in state.prompts] == ["review"]
        assert [a.name for a in state.prompts[0].arguments] == ["topic", "tone"]

    async def test_call_tool(self, client: MCPClient) -> None:
        assert await client.call_tool("docs", "echo", {"text": "oi"}) == (True, "echo:oi")

    async def test_read_resource_e_get_prompt(self, client: MCPClient) -> None:
        ok, text = await client.read_resource("docs", "docs://guide")
        assert ok and text.startswith("GUIDE CONTENT")
        assert await client.get_prompt("docs", "review", {"topic": "X"}) == (
            True,
            "Revise X em tom neutro.",
        )

    async def test_erros_de_resource_e_prompt_nao_levantam(self, client: MCPClient) -> None:
        ok, text = await client.read_resource("docs", "docs://nao-existe")
        assert not ok and "failed" in text
        ok, text = await client.get_prompt("docs", "inexistente", {})
        assert not ok
        assert (await client.read_resource("fantasma", "x"))[0] is False

    async def test_headers_com_variavel_de_ambiente(
        self, server: FakeServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ORION_TEST_TOKEN", "segredo-123")
        mcp = MCPClient(
            _cfg(server, headers={"X-Api-Key": "${ORION_TEST_TOKEN}"}), home=tmp_path / "h"
        )
        await mcp.start()
        try:
            ok, text = await mcp.call_tool("docs", "seen_header", {"name": "x-api-key"})
            assert ok and text == "segredo-123"
        finally:
            await mcp.close()

    async def test_variavel_ausente_vira_erro_e_nao_envia_vazio(
        self, server: FakeServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ORION_NAO_EXISTE", raising=False)
        mcp = MCPClient(_cfg(server, headers={"X-K": "${ORION_NAO_EXISTE}"}), home=tmp_path / "h")
        await mcp.start()
        try:
            state = mcp.servers["docs"]
            assert state.status == "error" and "ORION_NAO_EXISTE" in state.error
        finally:
            await mcp.close()

    def test_expand_env(self) -> None:
        assert expand_env("Bearer ${T}", {"T": "x"}) == "Bearer x"
        assert expand_headers({"a": "${T}"}, {"T": "1"}) == {"a": "1"}
        with pytest.raises(MissingEnvVar):
            expand_env("${X}", {})

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"url": "ftp://x/y"},
            {"url": "http://user:pw@host/mcp"},
            {"url": "http://exemplo.com/mcp", "headers": {"Authorization": "x"}},
            {"url": "http://exemplo.com/mcp", "auth": "oauth"},
            {"url": None},
        ],
    )
    def test_politica_de_url_recusa(self, kwargs: dict[str, Any]) -> None:
        cfg = MCPServerConfig(name="s", transport="http", **kwargs)
        with pytest.raises(SpawnDenied):
            check_remote_url(cfg)

    def test_politica_de_url_aceita_https_e_loopback(self) -> None:
        check_remote_url(
            MCPServerConfig(name="s", transport="http", url="https://x.com/mcp", auth="oauth")
        )
        check_remote_url(
            MCPServerConfig(
                name="s", transport="http", url="http://localhost:9/mcp", headers={"a": "b"}
            )
        )

    def test_log_do_servidor_e_0600(self, tmp_path: Path) -> None:
        path = server_log_path("srv", tmp_path)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


# ── list_changed e reconexão ────────────────────────────────────────────────


class TestListChangedAndReconnect:
    async def test_list_changed_atualiza_tools_e_geracao(self, client: MCPClient) -> None:
        before = client.generation
        assert (await client.call_tool("docs", "add_extra_tool", {}))[0]
        assert await _until(lambda: "extra_tool" in {t.name for t in client.servers["docs"].tools})
        assert client.generation > before

    async def test_reconecta_depois_que_o_servidor_cai(
        self, server: FakeServer, tmp_path: Path
    ) -> None:
        mcp = MCPClient(_cfg(server), home=tmp_path / "h", ping_interval=0.2, backoff_base=0.1)
        await mcp.start()
        try:
            state = mcp.servers["docs"]
            assert state.status == "connected"
            server.stop()
            assert await _until(lambda: state.status in ("reconnecting", "error"), 10)
            server.start()
            assert await _until(lambda: state.status == "connected", 20)
            assert state.reconnects >= 1
            assert (await mcp.call_tool("docs", "echo", {"text": "volta"}))[0]
        finally:
            await mcp.close()

    async def test_desiste_apos_o_teto_de_tentativas(self, server: FakeServer, tmp_path: Path) -> None:
        mcp = MCPClient(
            _cfg(server),
            home=tmp_path / "h",
            ping_interval=0.2,
            backoff_base=0.05,
            max_reconnects=2,
        )
        await mcp.start()
        try:
            state = mcp.servers["docs"]
            server.stop()
            assert await _until(lambda: state.status == "error" and "esgotada" in state.error, 20)
        finally:
            await mcp.close()

    async def test_falha_inicial_nao_fica_tentando(self, tmp_path: Path) -> None:
        cfg = {
            "x": MCPServerConfig(
                name="x", transport="http", url=f"http://127.0.0.1:{_free_port()}/mcp"
            )
        }
        mcp = MCPClient(cfg, home=tmp_path / "h", connect_timeout=5)
        await mcp.start()
        assert mcp.servers["x"].status == "error"
        await mcp.close()

    async def test_stop_durante_reconexao_encerra(self, server: FakeServer, tmp_path: Path) -> None:
        mcp = MCPClient(_cfg(server), home=tmp_path / "h", ping_interval=0.2, backoff_base=5)
        await mcp.start()
        server.stop()
        state = mcp.servers["docs"]
        assert await _until(lambda: state.status == "reconnecting", 10)
        await asyncio.wait_for(mcp.close(), 10)
        assert state.status == "disabled"


# ── OAuth ───────────────────────────────────────────────────────────────────


def _browser(log: list[str]) -> Callable[[str], None]:
    """Simula o navegador: abre a URL de autorização e segue o redirect até o loopback."""

    def open_url(url: str) -> None:
        log.append(url)
        threading.Thread(
            target=lambda: httpx.get(url, follow_redirects=True, timeout=10), daemon=True
        ).start()

    return open_url


def _oauth_cfg(server: FakeServer) -> dict[str, MCPServerConfig]:
    return {"docs": MCPServerConfig(name="docs", transport="http", url=server.url, auth="oauth")}


class TestOAuth:
    async def test_sem_login_o_boot_nao_abre_navegador(
        self, oauth_server: FakeServer, tmp_path: Path
    ) -> None:
        opened: list[str] = []
        mcp = MCPClient(
            _oauth_cfg(oauth_server), home=tmp_path / "h", open_browser=_browser(opened)
        )
        await mcp.start()
        try:
            state = mcp.servers["docs"]
            assert state.status == "error"
            assert "/mcp auth docs" in state.error
            assert opened == []
        finally:
            await mcp.close()

    async def test_login_interativo_pkce_e_token_0600(
        self, oauth_server: FakeServer, tmp_path: Path
    ) -> None:
        home, opened, urls = tmp_path / "h", [], []
        mcp = MCPClient(
            _oauth_cfg(oauth_server),
            home=home,
            open_browser=_browser(opened),
            on_auth_url=lambda srv, url: urls.append(url),
        )
        await mcp.start()
        try:
            await mcp.authenticate("docs")
            state = mcp.servers["docs"]
            assert state.status == "connected", state.error
            assert len(opened) == 1 and urls == opened
            assert "code_challenge_method=S256" in opened[0]
            assert (await mcp.call_tool("docs", "echo", {"text": "autenticado"}))[0]
        finally:
            await mcp.close()
        path = auth_file(home, "docs")
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["tokens"]["access_token"].startswith("tok-") and data["obtained_at"] > 0
        assert data["client_info"]["client_id"].startswith("client-")

    async def test_token_salvo_reconecta_sem_navegador(
        self, oauth_server: FakeServer, tmp_path: Path
    ) -> None:
        home = tmp_path / "h"
        first = MCPClient(_oauth_cfg(oauth_server), home=home, open_browser=_browser([]))
        await first.start()
        await first.authenticate("docs")
        assert first.servers["docs"].status == "connected"
        await first.close()

        opened: list[str] = []
        second = MCPClient(_oauth_cfg(oauth_server), home=home, open_browser=_browser(opened))
        await second.start()
        try:
            assert second.servers["docs"].status == "connected", second.servers["docs"].error
            assert opened == []
        finally:
            await second.close()

    async def test_negar_a_autorizacao_deixa_erro_claro(
        self, oauth_server: FakeServer, tmp_path: Path
    ) -> None:
        def deny(url: str) -> None:
            redirect = httpx.URL(url).params["redirect_uri"]
            threading.Thread(
                target=lambda: httpx.get(f"{redirect}?error=access_denied", timeout=10), daemon=True
            ).start()

        mcp = MCPClient(
            _oauth_cfg(oauth_server), home=tmp_path / "h", open_browser=deny, connect_timeout=20
        )
        await mcp.start()
        try:
            await asyncio.wait_for(mcp.authenticate("docs"), 40)
            assert mcp.servers["docs"].status == "error"
        finally:
            await mcp.close()


class TestTokenStorage:
    async def test_expira_em_relacao_ao_instante_da_emissao(self, tmp_path: Path) -> None:
        from mcp.shared.auth import OAuthToken

        storage = FileTokenStorage(tmp_path, "s")
        await storage.set_tokens(OAuthToken(access_token="a", token_type="Bearer", expires_in=100))
        data = json.loads(auth_file(tmp_path, "s").read_text(encoding="utf-8"))
        data["obtained_at"] -= 60
        auth_file(tmp_path, "s").write_text(json.dumps(data), encoding="utf-8")
        token = await storage.get_tokens()
        assert token is not None and 30 <= (token.expires_in or 0) <= 40

    async def test_vencido_vira_zero(self, tmp_path: Path) -> None:
        from mcp.shared.auth import OAuthToken

        storage = FileTokenStorage(tmp_path, "s")
        await storage.set_tokens(OAuthToken(access_token="a", token_type="Bearer", expires_in=10))
        data = json.loads(auth_file(tmp_path, "s").read_text(encoding="utf-8"))
        data["obtained_at"] -= 999
        auth_file(tmp_path, "s").write_text(json.dumps(data), encoding="utf-8")
        token = await storage.get_tokens()
        assert token is not None and token.expires_in == 0

    async def test_revoke_apaga_tudo(self, tmp_path: Path) -> None:
        from mcp.shared.auth import OAuthToken

        storage = FileTokenStorage(tmp_path, "s")
        await storage.set_tokens(OAuthToken(access_token="a", token_type="Bearer"))
        assert storage.has_tokens() and storage.revoke() and not storage.has_tokens()
        assert not storage.revoke()

    def test_nome_do_servidor_nao_escapa_do_diretorio(self, tmp_path: Path) -> None:
        assert auth_file(tmp_path, "../../etc/passwd").parent == tmp_path / "mcp_auth"


class TestLoopbackCallback:
    async def test_recebe_code_e_state(self) -> None:
        cb = LoopbackCallback()
        await cb.start()
        try:
            async with httpx.AsyncClient() as http:
                await http.get(f"{cb.redirect_uri}?code=abc&state=xyz")
            result = await cb.wait(2)
            assert (result.code, result.state) == ("abc", "xyz")
        finally:
            await cb.stop()

    async def test_so_aceita_callback_em_loopback(self) -> None:
        cb = LoopbackCallback()
        await cb.start()
        try:
            async with httpx.AsyncClient() as http:
                other = await http.get(f"http://127.0.0.1:{cb.port}/outro?code=x")
            assert other.status_code == 404
            with pytest.raises(TimeoutError):
                await cb.wait(0.3)
        finally:
            await cb.stop()
        assert cb.redirect_uri.startswith("http://127.0.0.1:")


# ── adapter, sessão, comandos ───────────────────────────────────────────────


class TestAdapterAndTools:
    async def test_tools_de_resource_sao_level_1(self, client: MCPClient) -> None:
        from orion.governance.permissions import tool_action_level

        tools = build_resource_tools(client)
        assert set(tools) == {"list_mcp_resources", "read_mcp_resource"}
        assert all(tool_action_level(n) == ActionLevel.LEVEL_1 for n in tools)
        listed = await tools["list_mcp_resources"].run()
        assert "docs:docs://guide" in listed.output
        read = await tools["read_mcp_resource"].run(server="docs", uri="docs://guide")
        assert read.success and "GUIDE CONTENT" in read.output

    async def test_sem_resources_nao_registra_tools(self) -> None:
        empty = MCPClient({})
        assert build_resource_tools(empty) == {}

    async def test_tool_mcp_nao_readonly_exige_confirmacao(self, client: MCPClient) -> None:
        adapters = build_adapters(client)
        assert adapters["mcp__docs__echo"].level == ActionLevel.LEVEL_2


@pytest.fixture
def make_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def _make(provider: ScriptedProvider, answers: list[Any] | None = None) -> AgentSession:
        pending = list(answers or [])

        async def ask(action: Action, level: ActionLevel) -> Any:
            return pending.pop(0) if pending else "y"

        session = AgentSession(
            status_bar=SessionStatusBar(),
            console=Console(file=io.StringIO(), width=100, theme=get_orion_theme()),
            workspace=tmp_path / "ws",
            home=tmp_path / "home",
            provider_factory=lambda spec: provider,
            ask_pep=ask,
        )
        session.set_model("anthropic/claude-sonnet-4-5")
        return session

    (tmp_path / "ws").mkdir(exist_ok=True)
    return _make


class TestSessionIntegration:
    async def test_mencao_de_resource_chega_como_dado_nao_confiavel(
        self, make_session, client: MCPClient
    ) -> None:  # type: ignore[no-untyped-def]
        provider = ScriptedProvider(["ok"])
        session = make_session(provider)
        session.start_mcp(client)
        await session.run_turn("Resuma @docs:docs://guide, por favor")
        sent = provider.requests[0].messages[-1].text
        assert 'server="docs"' in sent and 'trust="untrusted"' in sent
        assert "GUIDE CONTENT" in sent
        assert "<<<ORION_" not in sent  # delimitador forjado neutralizado

    async def test_mencao_de_servidor_desconhecido_segue_como_arquivo(
        self, make_session, client: MCPClient, tmp_path: Path
    ) -> None:  # type: ignore[no-untyped-def]
        (tmp_path / "ws" / "notas.txt").write_text("CONTEUDO-ARQUIVO", encoding="utf-8")
        provider = ScriptedProvider(["ok"])
        session = make_session(provider)
        session.start_mcp(client)
        await session.run_turn("veja @notas.txt e @fantasma:algo")
        sent = provider.requests[0].messages[-1].text
        assert "CONTEUDO-ARQUIVO" in sent and "mcp_resource" not in sent

    async def test_prompt_mcp_vira_slash_command(self, make_session, client: MCPClient) -> None:  # type: ignore[no-untyped-def]
        provider = ScriptedProvider(["ok"])
        session = make_session(provider)
        session.start_mcp(client)
        registry = CommandRegistry.discover()
        registry.set_dynamic(session.dynamic_commands())
        assert "/mcp__docs__review" in {i.name for i in session.dynamic_slash_infos()}
        context = CommandContext(session=session, console=session.console, clear_screen=lambda: None)
        result = await registry.dispatch("/mcp__docs__review API tone=formal", context)
        assert result.success
        assert "Revise API em tom formal." in provider.requests[0].messages[-1].text

    async def test_prompt_sem_argumento_obrigatorio_mostra_uso(
        self, make_session, client: MCPClient
    ) -> None:  # type: ignore[no-untyped-def]
        session = make_session(ScriptedProvider(["ok"]))
        session.start_mcp(client)
        registry = CommandRegistry.discover()
        registry.set_dynamic(session.dynamic_commands())
        context = CommandContext(session=session, console=session.console, clear_screen=lambda: None)
        result = await registry.dispatch("/mcp__docs__review", context)
        assert not result.success and "topic" in result.output_message

    async def test_list_changed_registra_a_nova_tool_no_runtime(
        self, make_session, client: MCPClient
    ) -> None:  # type: ignore[no-untyped-def]
        session = make_session(ScriptedProvider(["ok"]))
        session.start_mcp(client)
        session.refresh_mcp()
        assert "mcp__docs__extra_tool" not in session.runtime._tools
        assert (await client.call_tool("docs", "add_extra_tool", {}))[0]
        assert await _until(lambda: "extra_tool" in {t.name for t in client.servers["docs"].tools})
        session.refresh_mcp()
        assert "mcp__docs__extra_tool" in session.runtime._tools
        assert "list_mcp_resources" in session.runtime._tools

    async def test_tool_mcp_passa_pelo_pep(self, make_session, client: MCPClient, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        provider = ScriptedProvider([call("mcp__docs__echo", text="x"), "ok"])
        session = make_session(provider, answers=["n"])
        session.set_mode(AgentMode.MANUAL)  # em accept-edits o LEVEL_2 é auto-aprovado
        session.start_mcp(client)
        session.refresh_mcp()
        await session.run_turn("use a tool")
        result = str(provider.requests[1].messages[-1].content)
        assert "echo:x" not in result and "not executed" in result.lower() or "rejected" in result.lower()

    def test_completer_oferece_resources(self) -> None:
        from prompt_toolkit.document import Document

        from orion.tui.completer import OrionCompleter

        completer = OrionCompleter(mcp_resources=lambda: [("docs:docs://guide", "guide")])
        found = [c.text for c in completer.get_completions(Document("veja @docs:do"))]
        assert "docs:docs://guide" in found


class FakeMcpClient:
    """Cliente mínimo para exercitar o /mcp sem rede."""

    def __init__(self) -> None:
        self.servers: dict[str, Any] = {}
        self.added: list[MCPServerConfig] = []
        self.removed: list[str] = []
        self.authenticated: list[str] = []

    async def add_server(self, config: MCPServerConfig) -> None:
        from types import SimpleNamespace

        self.added.append(config)
        self.servers[config.name] = SimpleNamespace(
            config=config, status="connected", error="", tools=[], resources=[], prompts=[]
        )

    async def remove_server(self, name: str) -> bool:
        self.removed.append(name)
        return self.servers.pop(name, None) is not None

    async def authenticate(self, name: str) -> None:
        self.authenticated.append(name)


class TestMcpCommand:
    def test_parse_add_url_e_comando(self) -> None:
        name, entry = parse_add(["docs", "https://x.com/mcp", "--oauth", "--scope", "read"])
        assert name == "docs" and entry == {
            "url": "https://x.com/mcp",
            "transport": "http",
            "auth": "oauth",
            "scope": "read",
        }
        _, entry = parse_add(["loc", "uvx", "pkg", "--flag"])
        assert entry == {"transport": "stdio", "command": "uvx", "args": ["pkg", "--flag"]}
        _, entry = parse_add(["s", "http://127.0.0.1:1/sse", "--transport", "sse"])
        assert entry["transport"] == "sse"

    @pytest.mark.parametrize(
        "tokens",
        [
            [],
            ["so-nome"],
            ["nome inválido", "https://x"],
            ["a", "https://x", "--header", "semigual"],
            ["a", "https://x", "--transport", "ws"],
            ["a", "uvx", "--oauth"],
        ],
    )
    def test_parse_add_recusa(self, tokens: list[str]) -> None:
        with pytest.raises(ValueError):
            parse_add(tokens)

    async def _run(self, make_session, line: str) -> tuple[Any, FakeMcpClient, AgentSession]:  # type: ignore[no-untyped-def]
        session = make_session(ScriptedProvider(["ok"]))
        fake = FakeMcpClient()
        session.start_mcp(fake)
        registry = CommandRegistry.discover()
        context = CommandContext(session=session, console=session.console, clear_screen=lambda: None)
        return await registry.dispatch(line, context), fake, session

    async def test_add_persiste_0600_e_conecta(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        result, fake, session = await self._run(
            make_session, "/mcp add docs https://x.com/mcp --header Authorization=Bearer-literal"
        )
        assert result.success and "literal" in result.output_message
        path = session.home / "mcp_servers.json"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        saved = json.loads(path.read_text(encoding="utf-8"))["servers"]["docs"]
        assert saved["url"] == "https://x.com/mcp" and fake.added[0].transport == "http"

    async def test_add_com_variavel_nao_avisa(self, make_session) -> None:  # type: ignore[no-untyped-def]
        result, _, _ = await self._run(
            make_session, "/mcp add docs https://x.com/mcp --header Authorization=${TOKEN}"
        )
        assert result.success and "literal" not in result.output_message

    async def test_add_stdio_fora_da_allowlist_e_recusado(self, make_session) -> None:  # type: ignore[no-untyped-def]
        result, fake, _ = await self._run(make_session, "/mcp add evil bash -c rm")
        assert not result.success and fake.added == []

    async def test_add_url_com_credencial_em_http_e_recusado(self, make_session) -> None:  # type: ignore[no-untyped-def]
        result, fake, _ = await self._run(
            make_session, "/mcp add x http://exemplo.com/mcp --header A=${T}"
        )
        assert not result.success and fake.added == []

    async def test_remove_apaga_config_e_tokens(self, make_session) -> None:  # type: ignore[no-untyped-def]
        session = make_session(ScriptedProvider(["ok"]))
        fake = FakeMcpClient()
        session.start_mcp(fake)
        registry = CommandRegistry.discover()
        context = CommandContext(session=session, console=session.console, clear_screen=lambda: None)
        await registry.dispatch("/mcp add docs https://x.com/mcp --oauth", context)
        from mcp.shared.auth import OAuthToken

        await FileTokenStorage(session.home, "docs").set_tokens(
            OAuthToken(access_token="a", token_type="Bearer")
        )
        result = await registry.dispatch("/mcp remove docs", context)
        assert result.success and "tokens OAuth apagados" in result.output_message
        assert "docs" not in json.loads((session.home / "mcp_servers.json").read_text())["servers"]
        assert not auth_file(session.home, "docs").exists()

    async def test_remove_do_starter_pack_manda_desativar(self, make_session) -> None:  # type: ignore[no-untyped-def]
        session = make_session(ScriptedProvider(["ok"]))
        fake = FakeMcpClient()
        from types import SimpleNamespace

        fake.servers["serena"] = SimpleNamespace(
            config=MCPServerConfig(name="serena", command="uvx", bundled=True),
            status="connected",
            error="",
            tools=[],
        )
        session.start_mcp(fake)
        registry = CommandRegistry.discover()
        context = CommandContext(session=session, console=session.console, clear_screen=lambda: None)
        result = await registry.dispatch("/mcp remove serena", context)
        assert not result.success and "disable" in result.output_message and fake.removed == []

    async def test_auth_so_para_servidor_oauth(self, make_session) -> None:  # type: ignore[no-untyped-def]
        session = make_session(ScriptedProvider(["ok"]))
        fake = FakeMcpClient()
        session.start_mcp(fake)
        registry = CommandRegistry.discover()
        context = CommandContext(session=session, console=session.console, clear_screen=lambda: None)
        await registry.dispatch("/mcp add plain https://x.com/mcp", context)
        await registry.dispatch("/mcp add secure https://x.com/mcp --oauth", context)
        assert not (await registry.dispatch("/mcp auth plain", context)).success
        result = await registry.dispatch("/mcp auth secure", context)
        assert result.success and fake.authenticated == ["secure"]

    async def test_resources_e_prompts_listados(self, make_session, client: MCPClient) -> None:  # type: ignore[no-untyped-def]
        session = make_session(ScriptedProvider(["ok"]))
        session.start_mcp(client)
        registry = CommandRegistry.discover()
        context = CommandContext(session=session, console=session.console, clear_screen=lambda: None)
        res = await registry.dispatch("/mcp resources", context)
        assert "@docs:docs://guide" in res.output_message
        prompts = await registry.dispatch("/mcp prompts docs", context)
        assert "/mcp__docs__review" in prompts.output_message


# ── configuração ────────────────────────────────────────────────────────────


class TestConfigLoading:
    def test_settings_e_plugins_entram_apos_o_catalogo(self, tmp_path: Path) -> None:
        extra = [{"docs": {"transport": "http", "url": "https://x.com/mcp", "auth": "oauth"}}]
        configs = load_server_configs(tmp_path / "home", tmp_path / "ws", extra_layers=extra)
        assert configs["docs"].auth == "oauth" and not configs["docs"].bundled

    def test_arquivo_do_usuario_vence_settings(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()
        (home / "mcp_servers.json").write_text(
            json.dumps({"servers": {"docs": {"enabled": False}}}), encoding="utf-8"
        )
        extra = [{"docs": {"transport": "http", "url": "https://x.com/mcp"}}]
        cfg = load_server_configs(home, None, extra_layers=extra)["docs"]
        assert cfg.enabled is False and cfg.url == "https://x.com/mcp"


class TestAuthExpiry:
    async def test_login_perdido_nao_entra_em_loop_de_reconexao(
        self, oauth_server: FakeServer, tmp_path: Path
    ) -> None:
        home = tmp_path / "h"
        first = MCPClient(_oauth_cfg(oauth_server), home=home, open_browser=_browser([]))
        await first.start()
        await first.authenticate("docs")
        assert first.servers["docs"].status == "connected"
        await first.close()
        # Servidor reiniciado: os tokens antigos deixam de valer (estado em memória).
        oauth_server.stop()
        oauth_server.start()
        second = MCPClient(_oauth_cfg(oauth_server), home=home, open_browser=_browser([]))
        await second.start()
        try:
            state = second.servers["docs"]
            assert state.status == "error" and "/mcp auth docs" in state.error
            assert state.reconnects == 0
        finally:
            await second.close()
