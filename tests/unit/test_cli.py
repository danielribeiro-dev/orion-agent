"""
Unit tests for src/orion/cli.py
Covers: banner rendering, --version flag, --help, subcommand `info`.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from orion import __version__
from orion.cli import app, print_banner
from rich.console import Console
import io


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
