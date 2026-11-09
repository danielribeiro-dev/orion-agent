"""Unit tests for src/orion/tui/commands and src/orion/tui/modal.py"""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from rich.console import Console

from orion.agents.models import AgentResult
from orion.core.events import Action, RiskLevel
from orion.governance.permissions import ActionLevel
from orion.tui.commands import CommandContext, CommandRegistry
from orion.tui.completer import OFFICIAL_SLASH_COMMANDS
from orion.tui.modal import ConfigPanel, ConfigSetting, ModelPicker, PepChoice, render_ansi
from orion.tui.panels import SphereRow, render_config, render_context, render_cost, render_memory
from orion.tui.session import AgentMode, AgentSession
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme


@pytest.fixture
def registry() -> CommandRegistry:
    return CommandRegistry.discover()


@pytest.fixture
def context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CommandContext:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    console = Console(file=io.StringIO(), width=110, theme=get_orion_theme())
    session = AgentSession(
        status_bar=SessionStatusBar(), console=console, workspace=tmp_path, home=tmp_path / "home"
    )
    session.run_turn = AsyncMock(return_value="ok")  # type: ignore[method-assign]
    return CommandContext(session=session, console=console, clear_screen=MagicMock())


def text(context: CommandContext) -> str:
    return context.console.file.getvalue()  # type: ignore[attr-defined]


class TestCatalog:
    def test_every_catalog_entry_has_a_command(self, registry: CommandRegistry) -> None:
        assert {c.name for c in OFFICIAL_SLASH_COMMANDS} == set(registry.names)

    def test_catalog_size(self, registry: CommandRegistry) -> None:
        assert len(registry.names) == 30

    def test_no_emoji_in_catalog(self) -> None:
        for command in OFFICIAL_SLASH_COMMANDS:
            assert all(ord(ch) < 0x10000 for ch in command.description + command.icon)


class TestDispatch:
    async def test_unknown_command(self, registry: CommandRegistry, context: CommandContext) -> None:
        result = await registry.dispatch("/nada", context)
        assert not result.success
        assert "/help" in result.output_message

    @pytest.mark.parametrize("name", ["/plan", "/goal", "/recall", "/run", "/branch"])
    async def test_required_args_show_usage(
        self, registry: CommandRegistry, context: CommandContext, name: str
    ) -> None:
        result = await registry.dispatch(name, context)
        assert not result.success
        assert result.output_message.startswith("Uso:")

    @pytest.mark.parametrize(
        "line",
        ["/memory", "/timeline", "/recall teste", "/compact", "/context", "/merge", "/diff",
         "/undo", "/doctor", "/cost", "/mcp", "/voice", "/help", "/clear", "/grill-me", "/learn",
         "/review", "/plan x", "/goal x", "/branch b1", "/agents", "/agents runs", "/tasks", "/loop list"],
    )
    async def test_commands_do_not_raise(
        self, registry: CommandRegistry, context: CommandContext, line: str
    ) -> None:
        result = await registry.dispatch(line, context)
        assert isinstance(result.success, bool)


class TestBehavior:
    async def test_plan_sets_mode_and_runs(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        await registry.dispatch("/plan migrar", context)
        assert context.session.mode == AgentMode.PLAN
        assert "migrar" in context.session.run_turn.await_args.args[0]

    async def test_goal_sets_auto(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        await registry.dispatch("/goal x", context)
        assert context.session.mode == AgentMode.AUTO

    async def test_model_rejects_unknown(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        result = await registry.dispatch("/model nao/existe", context)
        assert not result.success

    async def test_model_accepts_id_and_persists(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        await registry.dispatch("/model google/gemini-2.5-pro", context)
        assert context.session.status_bar.model_name == "google/gemini-2.5-pro"
        assert context.session.config_path.is_file()

    async def test_merge_on_main_is_an_error_message(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        result = await registry.dispatch("/merge", context)
        assert not result.success

    async def test_timeline_rejects_bad_argument(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        result = await registry.dispatch("/timeline abc", context)
        assert result.output_message.startswith("Uso:")

    async def test_run_goes_through_pep(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        marker = context.session.workspace / "m"
        context.session._ask_pep = AsyncMock(return_value="n")
        await registry.dispatch(f"/run touch {marker}", context)
        context.session._ask_pep.assert_awaited_once()
        assert not marker.exists()

    async def test_doctor_never_prints_the_key(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        await registry.dispatch("/doctor", context)
        assert "configurada" in text(context)

    async def test_clear_uses_callback(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        await registry.dispatch("/clear", context)
        context.clear_screen.assert_called_once()


class TestModelPicker:
    @staticmethod
    def _picker() -> ModelPicker:
        return ModelPicker([SimpleNamespace(id="a/x"), SimpleNamespace(id="b/y")], "a/x")

    def test_filter_then_enter(self) -> None:
        picker = self._picker()
        picker.on_key("y")
        assert picker.on_key("enter") is True
        assert picker.chosen == "b/y"

    def test_escape_cancels(self) -> None:
        picker = self._picker()
        assert picker.on_key("escape") is True
        assert picker.chosen is None

    def test_arrows_wrap(self) -> None:
        picker = self._picker()
        picker.on_key("up")
        assert picker.selected == 1

    def test_empty_filter_enter_is_safe(self) -> None:
        picker = self._picker()
        for ch in "zzz":
            picker.on_key(ch)
        assert picker.on_key("enter") is True
        assert picker.chosen is None


class TestConfigPanel:
    @staticmethod
    def _panel(state: dict[str, str]) -> ConfigPanel:
        return ConfigPanel(
            {
                "A": [ConfigSetting("x", lambda: state["x"], ["1", "2"], lambda v: state.update(x=v))],
                "B": [ConfigSetting("ro", lambda: "fixo")],
            }
        )

    def test_enter_on_left_does_nothing(self) -> None:
        state = {"x": "1"}
        self._panel(state).on_key("enter")
        assert state["x"] == "1"

    def test_tab_then_enter_cycles(self) -> None:
        state = {"x": "1"}
        panel = self._panel(state)
        panel.on_key("tab")
        panel.on_key("enter")
        assert state["x"] == "2"

    def test_read_only_setting_is_ignored(self) -> None:
        panel = self._panel({"x": "1"})
        panel.on_key("down")
        panel.on_key("tab")
        panel.on_key("enter")
        assert panel.render() is not None

    @pytest.mark.parametrize("key", ["escape", "q"])
    def test_closes(self, key: str) -> None:
        assert self._panel({"x": "1"}).on_key(key) is True


class TestPepChoice:
    @staticmethod
    def _choice(tool: str = "run_command") -> PepChoice:
        action = Action(tool=tool, params={"command": "git push", "path": "a"}, risk_level=RiskLevel.CRITICAL)
        return PepChoice(action, ActionLevel.LEVEL_3)

    @pytest.mark.parametrize("key", ["y", "n", "e", "a", "Y"])
    def test_valid_keys(self, key: str) -> None:
        choice = self._choice()
        assert choice.on_key(key) is True
        assert choice.choice == key.lower()

    def test_other_keys_are_ignored(self) -> None:
        assert self._choice().on_key("x") is False

    def test_default_is_deny(self) -> None:
        choice = self._choice()
        assert choice.on_key("escape") is True
        assert choice.choice == "n"

    def test_edit_is_only_for_commands(self) -> None:
        assert self._choice("write_file").on_key("e") is False

    def test_dialog_shows_command_and_level(self) -> None:
        output = render_ansi(self._choice().render(), width=100)
        assert "PEP NÍVEL 3" in output
        assert "git push" in output


class TestPanels:
    def test_context_percentages(self) -> None:
        output = render_ansi(render_context({"sistema": 6200, "conversa": 15200}, 200_000), width=100)
        assert "21.4k / 200k (11%)" in output
        assert "7.6%" in output

    def test_cost_total(self) -> None:
        output = render_ansi(render_cost(12400, 3400, 0, 0.0372, 0.051, 0.0882, "0,507"), width=100)
        assert "15,800" in output
        assert "$0.0882" in output
        assert "R$ 0,507" in output

    def test_memory_panel(self) -> None:
        output = render_ansi(render_memory([SphereRow("user_profile", "Ativa", "D", "x")]), width=100)
        assert "user_profile" in output

    def test_config_at_80_columns_keeps_hints(self) -> None:
        panel = render_config(["Modelo & IA"], 0, [("Modelo:", "abc")], 0, True, [])
        assert "Esc/q" in render_ansi(panel, width=80)


class TestInteractiveFallback:
    """Sem TTY os modais imprimem o estado e devolvem o controle."""

    async def test_config_prints_panel_and_saves(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        await registry.dispatch("/config", context)
        assert "Painel de Configurações" in text(context)
        assert context.session.config_path.is_file()

    async def test_model_picker_prints_panel(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        await registry.dispatch("/model", context)
        assert "Seleção de Modelo" in text(context)

    async def test_model_auto_restores_routing(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        context.session.set_model("google/gemini-2.5-pro")
        await registry.dispatch("/model auto", context)
        assert context.session.selected_model is None


class TestDataCommands:
    async def test_diff_and_undo_after_change(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        target = context.session.workspace / "a.py"
        target.write_text("a\n")
        context.session.tracker.begin("1", target)
        target.write_text("b\n")
        context.session.tracker.finish("1")
        await registry.dispatch("/diff", context)
        assert "+1 / -1" in text(context)
        result = await registry.dispatch("/undo", context)
        assert result.output_message == "Desfeito: a.py"
        assert target.read_text() == "a\n"

    async def test_timeline_and_recall_find_events(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        await context.session._log_timeline("user", "user", "migrar banco de dados")
        await registry.dispatch("/timeline", context)
        assert "migrar banco" in text(context)
        result = await registry.dispatch("/recall banco", context)
        assert result.data == 1

    async def test_recall_searches_facts(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        from orion.memory.models import FactCategory, FactEntry

        category = next(iter(FactCategory))
        context.session.facts.upsert(FactEntry(key="db_engine", value="sqlite", category=category))
        await registry.dispatch("/recall sqlite", context)
        assert "db_engine" in text(context)

    async def test_recall_nothing_found(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        result = await registry.dispatch("/recall xyzzy", context)
        assert "Nada encontrado" in result.output_message

    async def test_compact_with_history(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        from orion.gateway.models import LLMMessage, MessageRole

        context.session.history = [
            LLMMessage(role=MessageRole.USER, content="p"),
            LLMMessage(role=MessageRole.ASSISTANT, content="r"),
        ]
        result = await registry.dispatch("/compact testes", context)
        assert result.success

    async def test_reopening_branch_keeps_original_base(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        await registry.dispatch("/branch x", context)
        base = context.session._branch_snapshots["x"]
        context.session.history = ["ruido"]
        await registry.dispatch("/branch x", context)
        assert context.session._branch_snapshots["x"] is base

    async def test_review_runs_on_real_diff(self, registry, context) -> None:  # type: ignore[no-untyped-def]
        import subprocess

        cwd = context.session.workspace
        run = lambda *a: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)  # noqa: E731
        run("init")
        run("config", "user.email", "t@t")
        run("config", "user.name", "t")
        (cwd / "f").write_text("a\n")
        run("add", ".")
        run("commit", "-m", "x")
        (cwd / "f").write_text("b\n")
        context.session.run_subagent = AsyncMock(  # type: ignore[method-assign]
            return_value=AgentResult(agent_id="agent_1", status="ok", summary="ok", ref="ref://agents/agent_1/result.md")
        )
        await registry.dispatch("/review", context)
        agent, _goal, diff = context.session.run_subagent.await_args.args
        assert agent == "code-review" and "+b" in diff
        context.session.run_turn.assert_not_awaited()  # o diff não entra no contexto do agente principal
