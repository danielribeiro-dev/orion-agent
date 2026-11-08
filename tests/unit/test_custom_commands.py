"""Comandos custom .md, /skills, plugin mínimo e confiança de projeto no CLI."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from rich.console import Console

from orion.core.events import Action
from orion.governance.permissions import ActionLevel
from orion.memory.models import SkillMetadata
from orion.plugins import discover_plugins
from orion.settings import ProjectTrust, project_settings_path
from orion.skills.loader import SkillsLoader
from orion.tui.commands import CommandContext, CommandRegistry
from orion.tui.commands.custom import (
    load_custom_commands,
    register_custom_commands,
    render_body,
)
from orion.tui.completer import OFFICIAL_SLASH_COMMANDS, SlashCommandCompleter, SlashCommandInfo
from orion.tui.session import AgentSession
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme
from tests.unit.test_agent_session import ScriptedProvider


def _md(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    path = tmp_path / "ws"
    path.mkdir()
    return path


RESERVED = {c.name for c in OFFICIAL_SLASH_COMMANDS}


class TestRender:
    def test_arguments_e_posicionais(self) -> None:
        body = "Corrija $1 na branch $2. Contexto: $ARGUMENTS"
        assert render_body(body, "bug-12 main") == "Corrija bug-12 na branch main. Contexto: bug-12 main"

    def test_argumento_ausente_vira_vazio(self) -> None:
        assert render_body("a=$1 b=$2", "x") == "a=x b="

    def test_aspas_agrupam(self) -> None:
        assert render_body("$1|$2", '"duas palavras" fim') == "duas palavras|fim"

    def test_sem_marcador_anexa_ao_fim(self) -> None:
        assert render_body("Revise o diff.", "foco em testes") == "Revise o diff.\n\nARGUMENTS: foco em testes"

    def test_sem_argumentos_nao_anexa(self) -> None:
        assert render_body("Revise o diff.", "") == "Revise o diff."


class TestLoading:
    def test_frontmatter_e_nome(self, home: Path, ws: Path) -> None:
        _md(
            ws / ".orion/commands/fix-issue.md",
            "---\ndescription: Corrige issue\nargument-hint: <n>\nallowed-tools: read_file, grep\n---\nCorrija $1",
        )
        (spec,) = load_custom_commands(home, ws, reserved=RESERVED)
        assert spec.name == "/fix-issue" and spec.source == "project"
        assert spec.description == "Corrige issue" and spec.argument_hint == "<n>"
        assert spec.allowed_tools == ("read_file", "grep")

    def test_subpasta_vira_namespace(self, home: Path, ws: Path) -> None:
        _md(home / "commands/team/deploy.md", "Faça deploy")
        (spec,) = load_custom_commands(home, ws, reserved=RESERVED)
        assert spec.name == "/team:deploy" and spec.source == "user"

    def test_projeto_vence_user(self, home: Path, ws: Path) -> None:
        _md(home / "commands/x.md", "do user")
        _md(ws / ".orion/commands/x.md", "do projeto")
        specs = load_custom_commands(home, ws, reserved=RESERVED)
        assert [(s.name, s.body) for s in specs] == [("/x", "do projeto")]

    def test_nome_de_comando_nativo_e_reservado(self, home: Path, ws: Path) -> None:
        _md(ws / ".orion/commands/plan.md", "sequestro")
        assert load_custom_commands(home, ws, reserved=RESERVED) == []

    def test_nome_invalido_e_arquivo_vazio_sao_ignorados(self, home: Path, ws: Path) -> None:
        _md(ws / ".orion/commands/Bad Name.md", "x")
        _md(ws / ".orion/commands/vazio.md", "---\ndescription: a\n---\n")
        _md(ws / ".orion/commands/ok.md", "ok")
        assert [s.name for s in load_custom_commands(home, ws, reserved=RESERVED)] == ["/ok"]

    def test_yaml_quebrado_e_ignorado(self, home: Path, ws: Path) -> None:
        _md(ws / ".orion/commands/q.md", "---\n: : :\n  - [\n---\ncorpo")
        assert load_custom_commands(home, ws, reserved=RESERVED) == []


class TestPlugins:
    def _plugin(self, home: Path, name: str = "acme") -> Path:
        root = home / "plugins" / name
        root.mkdir(parents=True)
        (root / "plugin.json").write_text(json.dumps({"name": name, "version": "1.2"}), encoding="utf-8")
        return root

    def test_descobre_plugin(self, home: Path) -> None:
        self._plugin(home)
        (plugin,) = discover_plugins(home)
        assert (plugin.name, plugin.version) == ("acme", "1.2")

    def test_manifesto_ou_nome_invalido_e_ignorado(self, home: Path) -> None:
        bad = home / "plugins" / "bad"
        bad.mkdir(parents=True)
        (bad / "plugin.json").write_text(json.dumps({"name": "Bad Name"}), encoding="utf-8")
        (home / "plugins" / "semmanifest").mkdir()
        assert discover_plugins(home) == []

    def test_comandos_ganham_namespace_do_plugin(self, home: Path, ws: Path) -> None:
        root = self._plugin(home)
        _md(root / "commands/audit.md", "Audite $ARGUMENTS")
        specs = load_custom_commands(home, ws, discover_plugins(home), RESERVED)
        assert [(s.name, s.source) for s in specs] == [("/acme:audit", "plugin")]

    def test_hooks_e_mcp_viram_camada_de_settings(self, home: Path) -> None:
        root = self._plugin(home)
        (root / "hooks.json").write_text(
            json.dumps({"Stop": [{"command": "echo oi"}, {"naoecommand": 1}]}), encoding="utf-8"
        )
        (root / "mcp.json").write_text(json.dumps({"servers": {"db": {"command": "uvx"}}}), encoding="utf-8")
        layer = discover_plugins(home)[0].settings_layer()
        assert [h.command for h in layer.hooks["Stop"]] == ["echo oi"]
        assert list(layer.mcp) == ["acme:db"]

    def test_skills_do_plugin_entram_no_loader(self, home: Path) -> None:
        root = self._plugin(home)
        _md(root / "skills/lint/SKILL.md", "---\nname: lint\ndescription: Lint\n---\ncorpo")
        loader = SkillsLoader(None, home / "skills", builtin_dir=None, extra_dirs=[root / "skills"])
        assert "lint" in loader.discover()

    def test_plugin_nao_derruba_se_hooks_json_for_lixo(self, home: Path) -> None:
        root = self._plugin(home)
        (root / "hooks.json").write_text("{lixo", encoding="utf-8")
        assert discover_plugins(home)[0].settings_layer().hooks == {}


class TestSkillMetadata:
    def test_aceita_allowed_tools_com_hifen_e_string(self) -> None:
        meta = SkillMetadata.model_validate(
            {"name": "x", "description": "d", "allowed-tools": "Read, Grep", "argument-hint": "<f>"}
        )
        assert meta.allowed_tools == ["Read", "Grep"] and meta.argument_hint == "<f>"

    def test_continua_aceitando_underscore(self) -> None:
        meta = SkillMetadata(name="x", description="d", allowed_tools=["a"])
        assert meta.allowed_tools == ["a"]


@pytest.fixture
def make_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def _make(provider: ScriptedProvider | None = None) -> AgentSession:
        async def ask(action: Action, level: ActionLevel) -> Any:
            return "y"

        session = AgentSession(
            status_bar=SessionStatusBar(),
            console=Console(file=io.StringIO(), width=100, theme=get_orion_theme()),
            workspace=tmp_path / "ws",
            home=tmp_path / "home",
            provider_factory=lambda spec: provider or ScriptedProvider(["ok"]),
            ask_pep=ask,
        )
        session.set_model("anthropic/claude-sonnet-4-5")
        return session

    return _make


class TestSessionIntegration:
    async def test_dispatch_envia_corpo_renderizado_ao_agente(self, make_session, ws: Path) -> None:  # type: ignore[no-untyped-def]
        _md(ws / ".orion/commands/greet.md", "---\ndescription: Saudar\n---\nDiga oi para $1")
        provider = ScriptedProvider(["feito"])
        session = make_session(provider)
        registry = CommandRegistry.discover()
        assert register_custom_commands(registry, session.custom_commands) == 1
        context = CommandContext(session=session, console=session.console, clear_screen=lambda: None)
        result = await registry.dispatch("/greet Ana", context)
        assert result.success
        assert "Diga oi para Ana" in provider.requests[0].messages[-1].text

    def test_infos_dinamicas_aparecem_no_completer_e_no_help(self, make_session, ws: Path) -> None:  # type: ignore[no-untyped-def]
        _md(ws / ".orion/commands/greet.md", "---\ndescription: Saudar\nargument-hint: <nome>\n---\nx")
        session = make_session()
        infos = session.dynamic_slash_infos()
        assert [(i.name, i.category) for i in infos] == [("/greet", "project")]
        assert "<nome>" in infos[0].description
        completer = SlashCommandCompleter(dynamic=session.dynamic_slash_infos)
        assert "/greet" in {c.name for c in completer.commands}
        assert all(c.icon in ("❯", "●", "›") for c in infos)

    def test_dinamico_nao_duplica_nativo(self) -> None:
        completer = SlashCommandCompleter(dynamic=lambda: [SlashCommandInfo("/plan", "x")])
        assert [c.name for c in completer.commands].count("/plan") == 1

    async def test_skills_lista_e_ativa(self, make_session, ws: Path) -> None:  # type: ignore[no-untyped-def]
        _md(ws / ".orion/skills/lint/SKILL.md", "---\nname: lint\ndescription: Roda lint\n---\ncorpo")
        provider = ScriptedProvider(["ok"])
        session = make_session(provider)
        registry = CommandRegistry.discover()
        context = CommandContext(session=session, console=session.console, clear_screen=lambda: None)
        assert (await registry.dispatch("/skills", context)).success
        assert "lint" in session.console.file.getvalue()  # type: ignore[attr-defined]
        assert (await registry.dispatch("/skills lint src/", context)).success
        assert "use_skill" in provider.requests[0].messages[-1].text
        assert not (await registry.dispatch("/skills nada", context)).success

    def test_plugin_com_hook_alimenta_os_settings_efetivos(self, make_session, home_plugin) -> None:  # type: ignore[no-untyped-def]
        session = make_session()
        assert [h.command for h in session.settings.effective.hooks["Stop"]] == ["echo plugin"]


@pytest.fixture
def home_plugin(tmp_path: Path) -> Path:
    root = tmp_path / "home" / "plugins" / "acme"
    root.mkdir(parents=True)
    (root / "plugin.json").write_text(json.dumps({"name": "acme"}), encoding="utf-8")
    (root / "hooks.json").write_text(json.dumps({"Stop": [{"command": "echo plugin"}]}), encoding="utf-8")
    return root


class TestProjectTrustPrompt:
    def _session(self, make_session, ws: Path) -> AgentSession:  # type: ignore[no-untyped-def]
        path = project_settings_path(ws)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"hooks": {"Stop": [{"command": "echo x"}]}}), encoding="utf-8")
        return make_session()

    def test_sessao_ignora_hooks_de_projeto_nao_confiavel(self, make_session, ws: Path) -> None:  # type: ignore[no-untyped-def]
        session = self._session(make_session, ws)
        assert session.settings.project_needs_trust
        assert session.settings.effective.hooks == {}

    def test_trust_project_libera_e_persiste(self, make_session, ws: Path, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        session = self._session(make_session, ws)
        session.trust_project()
        assert not session.settings.project_needs_trust
        assert "Stop" in session.settings.effective.hooks
        assert ProjectTrust(tmp_path / "home").is_trusted(ws, session.settings.project_digest or "")

    def test_cli_pergunta_e_confia(self, make_session, ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
        from orion import cli

        session = self._session(make_session, ws)
        monkeypatch.setattr("orion.tui.modal.is_interactive", lambda: True)

        async def confiar(console: Any, question: str, options: Any, multi: bool = False) -> list[str]:
            return ["Confiar"]

        monkeypatch.setattr("orion.tui.modal.ask_user_choice", confiar)
        cli._ask_project_trust(session)
        assert "Stop" in session.settings.effective.hooks

    def test_cli_nao_confiar_mantem_restrito(self, make_session, ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
        from orion import cli

        session = self._session(make_session, ws)
        monkeypatch.setattr("orion.tui.modal.is_interactive", lambda: True)

        async def negar(console: Any, question: str, options: Any, multi: bool = False) -> list[str]:
            return ["Não confiar"]

        monkeypatch.setattr("orion.tui.modal.ask_user_choice", negar)
        cli._ask_project_trust(session)
        assert session.settings.effective.hooks == {}

    def test_cli_sem_terminal_nao_confia(self, make_session, ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
        from orion import cli

        session = self._session(make_session, ws)
        monkeypatch.setattr("orion.tui.modal.is_interactive", lambda: False)
        cli._ask_project_trust(session)
        assert session.settings.project_needs_trust

    def test_cli_sem_pendencia_nao_pergunta(self, make_session, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
        from orion import cli

        session = make_session()
        called = SimpleNamespace(n=0)
        monkeypatch.setattr("orion.tui.modal.is_interactive", lambda: called.__setattr__("n", 1) or True)
        cli._ask_project_trust(session)
        assert called.n == 0
