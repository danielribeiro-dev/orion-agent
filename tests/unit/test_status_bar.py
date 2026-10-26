"""
Unit tests for O.R.I.O.N TUI SessionStatusBar and Badges.
Covers: CA-01 (Larguras de Terminal), CA-02 (Validação Monetária),
CA-03 (Fallback de Identidade) e CA-04 (Zero Quebras ANSI).
"""

from __future__ import annotations

import io
import re

import pytest
from pydantic import ValidationError
from rich.console import Console
from rich.text import Text

from orion.tui.status_bar import ReasoningEffort, SessionStatusBar


class TestSessionStatusBarModel:
    """Valida o modelo de dados Pydantic v2 do SessionStatusBar."""

    def test_default_values(self) -> None:
        bar = SessionStatusBar()
        assert bar.is_online is True
        assert bar.model_name == "claude-3-7-sonnet-thinking"
        assert bar.reasoning_effort == ReasoningEffort.HIGH
        assert bar.pep_level == 2
        assert bar.github_user is None
        assert bar.google_account is None
        assert bar.events_count == 0
        assert bar.session_tokens_in == 0
        assert bar.session_tokens_out == 0
        assert bar.session_cost_usd == 0.0
        assert bar.usd_to_brl_rate == 5.75

    def test_pep_level_validation(self) -> None:
        # 0 <= pep_level <= 3 são válidos
        for lvl in [0, 1, 2, 3]:
            bar = SessionStatusBar(pep_level=lvl)
            assert bar.pep_level == lvl

        # Fora do intervalo deve levantar ValidationError
        with pytest.raises(ValidationError):
            SessionStatusBar(pep_level=-1)

        with pytest.raises(ValidationError):
            SessionStatusBar(pep_level=4)

    def test_reasoning_effort_enum(self) -> None:
        assert ReasoningEffort.HIGH.value == "HIGH"
        assert ReasoningEffort.MEDIUM.value == "MEDIUM"
        assert ReasoningEffort.LOW.value == "LOW"
        assert ReasoningEffort.OFF.value == "OFF"


class TestMonetaryFormatting:
    """Valida o Critério de Aceite CA-02 (Validação Monetária)."""

    def test_ca02_monetary_validation_exact(self) -> None:
        """CA-02: Com session_cost_usd = 0.0100 e taxa de 5.75, exibe $0.0100 USD e R$ 0,058."""
        bar = SessionStatusBar(session_cost_usd=0.0100, usd_to_brl_rate=5.75)
        assert bar.session_cost_brl == pytest.approx(0.0575, rel=1e-4)

        assert bar.format_cost_usd() == "$0.0100 USD"
        assert bar.format_cost_brl() == "0,058"

        # Validar que a barra de status inferior contém ambas as strings
        buf = io.StringIO()
        console = Console(file=buf, width=80, force_terminal=True)
        console.print(bar.render_bottom_bar(width=80))
        output = buf.getvalue()

        assert "$0.0100 USD" in output
        assert "R$ 0,058" in output


class TestTerminalWidthsCA01:
    """Valida o Critério de Aceite CA-01 (Larguras de Terminal 60, 80, 100, 120 e 200)."""

    @pytest.mark.parametrize("width", [60, 80, 100, 120, 200])
    def test_render_bottom_bar_no_overflow(self, width: int) -> None:
        bar = SessionStatusBar(
            session_cost_usd=0.0100,
            usd_to_brl_rate=5.75,
            session_tokens_in=1840,
            session_tokens_out=420,
        )
        buf = io.StringIO()
        console = Console(
            file=buf,
            width=width,
            force_terminal=True,
            _environ={"COLUMNS": str(width)},
        )
        console.print(bar.render_bottom_bar(width=width))

        lines = buf.getvalue().splitlines()
        for idx, line in enumerate(lines):
            visual_len = Text.from_ansi(line).cell_len
            assert visual_len <= width, (
                f"Largura {width}: linha {idx} estourou com tamanho {visual_len}"
            )

    @pytest.mark.parametrize("width", [60, 80, 100, 120, 200])
    def test_render_header_panel_no_overflow(self, width: int) -> None:
        bar = SessionStatusBar(
            github_user="danieldev",
            workspace_path="/home/danieldev/orion-agent",
            events_count=838,
        )
        buf = io.StringIO()
        console = Console(
            file=buf,
            width=width,
            force_terminal=True,
            _environ={"COLUMNS": str(width), "COLORTERM": "truecolor"},
        )
        console.print(bar.render_header_panel(width=width))

        lines = buf.getvalue().splitlines()
        for idx, line in enumerate(lines):
            visual_len = Text.from_ansi(line).cell_len
            assert visual_len <= width, (
                f"Largura {width}: linha {idx} estourou com tamanho {visual_len}"
            )


class TestIdentityFallbackCA03:
    """Valida o Critério de Aceite CA-03 (Fallback de Identidade)."""

    def test_from_environment_silent_fallback(self) -> None:
        bar = SessionStatusBar.from_environment()
        assert bar.workspace_path != ""
        assert isinstance(bar.events_count, int)
        assert isinstance(bar.session_cost_usd, float)
        assert isinstance(bar.session_tokens_in, int)

    def test_header_panel_fallback_unconnected(self) -> None:
        bar = SessionStatusBar(github_user=None, google_account=None, is_online=False)
        buf = io.StringIO()
        console = Console(file=buf, width=120, force_terminal=True)
        console.print(bar.render_header_panel(width=120))
        output = buf.getvalue()

        assert "Not connected" in output or "Local" in output
        assert "OFFLINE" in output or "Offline" in output

    def test_from_environment_with_mocked_databases(self, tmp_path, monkeypatch) -> None:
        import sqlite3
        from pathlib import Path

        # Criar ~/.orion simulado
        orion_home = tmp_path / ".orion"
        orion_home.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Timeline DB
        tl_db = orion_home / "timeline.db"
        conn_tl = sqlite3.connect(tl_db)
        try:
            conn_tl.execute("CREATE TABLE timeline_events (id INTEGER PRIMARY KEY, content TEXT)")
            conn_tl.execute("INSERT INTO timeline_events (content) VALUES ('ev1')")
            conn_tl.execute("INSERT INTO timeline_events (content) VALUES ('ev2')")
            conn_tl.commit()
        finally:
            conn_tl.close()

        # Metrics DB
        m_db = orion_home / "metrics.db"
        conn_m = sqlite3.connect(m_db)
        try:
            conn_m.execute(
                "CREATE TABLE cost_ledger (cost_usd REAL, tokens_in INTEGER, tokens_out INTEGER)"
            )
            conn_m.execute("INSERT INTO cost_ledger VALUES (0.025, 1200, 300)")
            conn_m.commit()
        finally:
            conn_m.close()

        bar = SessionStatusBar.from_environment()
        assert bar.events_count == 2
        assert bar.session_cost_usd == pytest.approx(0.025)
        assert bar.session_tokens_in == 1200
        assert bar.session_tokens_out == 300

    def test_from_environment_git_error(self, monkeypatch) -> None:
        import subprocess

        def _fail(*args, **kwargs):
            raise OSError("Git not found")

        monkeypatch.setattr(subprocess, "run", _fail)
        monkeypatch.delenv("GITHUB_USER", raising=False)
        bar = SessionStatusBar.from_environment()
        assert bar is not None

    def test_long_workspace_path_truncation(self) -> None:
        long_ws = (
            "/home/developer/super/deeply/nested/repository/name/that/exceeds/thirty/five/chars"
        )
        bar = SessionStatusBar(workspace_path=long_ws)
        buf = io.StringIO()
        console = Console(file=buf, width=120, force_terminal=True, _environ={"COLUMNS": "120"})
        console.print(bar.render_header_panel(width=120))
        output = buf.getvalue()
        assert "..." in output


class TestZeroAnsiBreakagesCA04:
    """Valida o Critério de Aceite CA-04 (Zero Quebras ANSI)."""

    @pytest.mark.parametrize("width", [60, 80, 120])
    def test_ansi_escape_sequences_well_formed(self, width: int) -> None:
        bar = SessionStatusBar(session_cost_usd=0.0031, session_tokens_in=1000)
        buf = io.StringIO()
        console = Console(file=buf, width=width, force_terminal=True)
        console.print(bar.render_bottom_bar(width=width))
        console.print(bar.render_header_panel(width=width))
        raw = buf.getvalue()

        # Não deve haver caractere ESC isolado sem terminação de sequência ANSI
        # Sequências ANSI válidas iniciam com \x1b[ e terminam com letra (ex: m, K, H, J)
        ansi_regex = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
        stripped = ansi_regex.sub("", raw)
        assert "\x1b" not in stripped, "Código de escape ANSI quebrado ou não terminado detectado"
