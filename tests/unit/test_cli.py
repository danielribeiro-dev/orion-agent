"""
Unit tests for src/orion/cli.py
Covers: banner rendering, --version flag, --help, subcommand `info`.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

from rich.console import Console

from orion import __version__
from orion.cli import print_banner, run_interactive_repl

# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------


class TestVersionFlag:
    def test_version_exits_zero(self, invoke) -> None:
        result = invoke("--version")
        assert result.exit_code == 0

    def test_version_displays_string(self, invoke) -> None:
        result = invoke("--version")
        assert __version__ in result.output

    def test_version_contains_orion(self, invoke) -> None:
        result = invoke("--version")
        assert "ORION" in result.output or "orion" in result.output.lower()

    def test_version_shortflag(self, invoke) -> None:
        result = invoke("-V")
        assert result.exit_code == 0
        assert __version__ in result.output


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


class TestHelpFlag:
    def test_help_exits_zero(self, invoke) -> None:
        result = invoke("--help")
        assert result.exit_code == 0

    def test_help_mentions_orion(self, invoke) -> None:
        result = invoke("--help")
        output = result.output.lower()
        assert "orion" in output or "operational" in output

    def test_help_lists_info_command(self, invoke) -> None:
        result = invoke("--help")
        assert "info" in result.output


# ---------------------------------------------------------------------------
# Default invocation (no subcommand)
# ---------------------------------------------------------------------------


class TestDefaultInvocation:
    def test_no_args_exits_zero(self, invoke) -> None:
        result = invoke()
        assert result.exit_code == 0

    def test_no_args_shows_hint(self, invoke) -> None:
        result = invoke()
        # Should show some kind of usage hint
        assert result.output.strip() != ""

    def test_no_args_renders_banner_and_status(self, invoke) -> None:
        result = invoke()
        assert "ORION" in result.output
        assert "GATEWAY" in result.output or "STATUS" in result.output

    def test_main_entrypoint_calls_app(self, monkeypatch) -> None:
        from orion.cli import main
        called = False

        def _mock_app() -> None:
            nonlocal called
            called = True

        monkeypatch.setattr("orion.cli.app", _mock_app)
        main()
        assert called is True


# ---------------------------------------------------------------------------
# `info` subcommand
# ---------------------------------------------------------------------------


class TestInfoCommand:
    def test_info_exits_zero(self, invoke) -> None:
        result = invoke("info")
        assert result.exit_code == 0

    def test_info_shows_version(self, invoke) -> None:
        result = invoke("info")
        assert __version__ in result.output

    def test_info_shows_routing_mode(self, invoke) -> None:
        result = invoke("info")
        # Default is AUTO
        assert "auto" in result.output.lower()

    def test_info_shows_autonomy_level(self, invoke) -> None:
        result = invoke("info")
        assert "supervised" in result.output.lower()

    def test_info_shows_max_turns(self, invoke) -> None:
        result = invoke("info")
        assert "20" in result.output


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


class TestBanner:
    def test_print_banner_runs_without_error(self) -> None:
        """print_banner() must not raise any exception."""
        buf = io.StringIO()
        # Redirect Rich output to a buffer for isolation
        from orion import cli as cli_module
        original_console = cli_module.console
        cli_module.console = Console(file=buf, highlight=False)
        try:
            print_banner()
        finally:
            cli_module.console = original_console

    def test_banner_contains_orion_text(self) -> None:
        buf = io.StringIO()
        from orion import cli as cli_module
        original_console = cli_module.console
        cli_module.console = Console(file=buf, highlight=False, no_color=True)
        try:
            print_banner()
        finally:
            cli_module.console = original_console
        output = buf.getvalue()
        assert "ORION" in output or "PERSONAL OPERATING INTELLIGENCE" in output


# ---------------------------------------------------------------------------
# Interactive REPL
# ---------------------------------------------------------------------------


class TestInteractiveRepl:
    """Valida o loop interativo run_interactive_repl."""

    @staticmethod
    def _session() -> MagicMock:
        session = MagicMock()
        session.session_id = "test"
        session.run_turn = AsyncMock(return_value="ok")
        return session

    @staticmethod
    def _prompt(*inputs: object) -> MagicMock:
        async def _run_turn(coro, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return await coro

        prompt = MagicMock()
        prompt.prompt.side_effect = list(inputs)
        prompt.run_turn = _run_turn
        return prompt

    def test_repl_exits_on_exit_command(self) -> None:
        prompt = self._prompt("/exit")
        run_interactive_repl(prompt, self._session())
        assert prompt.prompt.call_count == 1

    def test_repl_dispatches_slash_commands_to_registry(self) -> None:
        prompt = self._prompt("/help", "/exit")
        session = self._session()
        run_interactive_repl(prompt, session)
        session.run_turn.assert_not_called()

    def test_repl_sends_instructions_to_the_agent(self) -> None:
        prompt = self._prompt("", "   ", "Please check @README.md", "/quit")
        session = self._session()
        run_interactive_repl(prompt, session)
        session.run_turn.assert_awaited_once_with("Please check @README.md")

    def test_repl_reports_unknown_command(self, capsys) -> None:  # type: ignore[no-untyped-def]
        prompt = self._prompt("/naoexiste", "/exit")
        run_interactive_repl(prompt, self._session())
        assert prompt.prompt.call_count == 2

    def test_repl_handles_keyboard_interrupt_gracefully(self) -> None:
        prompt = self._prompt(KeyboardInterrupt(), "/exit")
        run_interactive_repl(prompt, self._session())
        assert prompt.prompt.call_count == 2

    def test_double_ctrl_c_exits(self) -> None:
        prompt = self._prompt(KeyboardInterrupt(), KeyboardInterrupt(), "nunca")
        run_interactive_repl(prompt, self._session())
        assert prompt.prompt.call_count == 2
