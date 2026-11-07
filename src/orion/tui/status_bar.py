"""
O.R.I.O.N TUI — Session Status Bar & Badges.

Modelo de dados e renderizador da barra inferior e dos badges de status da sessão.
"""

from __future__ import annotations

import os
import subprocess
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from orion import __version__
from orion.tui.theme import ORION_COLORS


class ReasoningEffort(StrEnum):
    """Níveis de esforço de raciocínio profundo."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    OFF = "OFF"


def _make_badge(label: str, value: str, dot_style: str = "accent_cyan") -> Text:
    """Cria um badge no formato '● LABEL: Valor' com cores do Design System."""
    t = Text(no_wrap=True)
    t.append("● ", style=dot_style)
    t.append(f"{label}: ", style="text_dim")
    t.append(value, style="text_primary")
    return t


class SessionStatusBar(BaseModel):
    """Estado dinâmico da sessão e renderizador de cabeçalho e rodapé do terminal."""

    is_online: bool = True
    model_name: str = "claude-3-7-sonnet-thinking"
    reasoning_effort: ReasoningEffort = ReasoningEffort.HIGH
    pep_level: int = Field(default=2, ge=0, le=3)
    github_user: str | None = None
    google_account: str | None = None
    events_count: int = 0
    workspace_path: str = ""
    session_tokens_in: int = 0
    session_tokens_out: int = 0
    session_cost_usd: float = 0.0
    usd_to_brl_rate: float = 5.75
    agent_mode: str = "accept-edits"
    is_busy: bool = False
    fast_mode: bool = False

    @property
    def session_cost_brl(self) -> float:
        """Calcula o custo total da sessão em BRL."""
        return self.session_cost_usd * self.usd_to_brl_rate

    def format_cost_usd(self) -> str:
        """Formata o custo em USD com precisão cirúrgica de 4 casas decimais."""
        return f"${self.session_cost_usd:.4f} USD"

    def format_cost_brl(self) -> str:
        """Formata o custo em BRL com 3 casas decimais (arredondamento bancário formal)."""
        dec = (Decimal(str(self.session_cost_usd)) * Decimal(str(self.usd_to_brl_rate))).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )
        return str(dec).replace(".", ",")

    @classmethod
    def from_environment(cls, config: Any | None = None) -> SessionStatusBar:
        """Extrai o estado atual do ambiente local com fallbacks resilientes e silenciosos."""
        # 1. Diretório de trabalho
        workspace_path = str(Path.cwd())

        # 2. Usuário Git local
        github_user: str | None = None
        try:
            res = subprocess.run(
                ["git", "config", "user.name"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1,
            )
            if res.returncode == 0 and res.stdout.strip():
                github_user = res.stdout.strip()
        except Exception:
            pass

        if not github_user:
            github_user = os.environ.get("GITHUB_USER") or os.environ.get("USER")

        # 3. Contagem de eventos da Timeline SQLite WAL (~/.orion/timeline.db)
        events_count = 0
        timeline_path = Path.home() / ".orion" / "timeline.db"
        if timeline_path.is_file():
            try:
                import sqlite3

                conn = sqlite3.connect(f"file:{timeline_path}?mode=ro", uri=True)
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT count(*) FROM timeline_events")
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        events_count = int(row[0])
                finally:
                    conn.close()
            except Exception:
                pass

        # 4. Custos e Tokens acumulados do livro-razão (~/.orion/metrics.db)
        session_cost_usd = 0.0
        session_tokens_in = 0
        session_tokens_out = 0
        metrics_path = Path.home() / ".orion" / "metrics.db"
        if metrics_path.is_file():
            try:
                import sqlite3

                conn = sqlite3.connect(f"file:{metrics_path}?mode=ro", uri=True)
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT sum(cost_usd), sum(tokens_in), sum(tokens_out) FROM cost_ledger"
                    )
                    row = cursor.fetchone()
                    if row:
                        if row[0] is not None:
                            session_cost_usd = float(row[0])
                        if row[1] is not None:
                            session_tokens_in = int(row[1])
                        if row[2] is not None:
                            session_tokens_out = int(row[2])
                finally:
                    conn.close()
            except Exception:
                pass

        return cls(
            github_user=github_user,
            workspace_path=workspace_path,
            events_count=events_count,
            session_cost_usd=session_cost_usd,
            session_tokens_in=session_tokens_in,
            session_tokens_out=session_tokens_out,
        )

    def render_header_panel(self, width: int = 80) -> RenderableType:
        """Gera o painel de cabeçalho formatado em Rich com layout aberto e arejado."""
        auth_val = f"GitHub [@{self.github_user}]" if self.github_user else "Local Session"
        status_text = "ONLINE (Cloud Gateway)" if self.is_online else "OFFLINE (Local Gateway)"
        status_dot = "status_ok" if self.is_online else "status_offline"

        # Abreviação elegante do caminho do workspace (~/orion-agent)
        ws_display = self.workspace_path or str(Path.cwd())
        try:
            home_dir = str(Path.home())
            if ws_display.startswith(home_dir):
                ws_display = "~" + ws_display[len(home_dir) :]
        except Exception:
            pass

        if len(ws_display) > 36:
            ws_display = "..." + ws_display[-33:]

        if width < 100:
            # 📐 Cenário A: Modo Compacto (< 100 colunas)
            cyber_block = [
                ("  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗", f"   O.R.I.O.N (ORION)  v{__version__}"),
                (" ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║", "   Sovereign Cognitive Agent"),
                (" ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║", "   Non Ducor, Duco"),
                (" ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║", ""),
            ]

            top_content = Text(no_wrap=True)
            for art, desc in cyber_block:
                top_content.append(art, style="accent_cyan")
                if width >= 75:
                    top_content.append(desc, style="text_user")
                top_content.append("\n")

            if width < 75:
                # 1 coluna para terminais estreitos (< 75 cols, ex: 60)
                grid = Table.grid(padding=(0, 1), expand=True)
                grid.add_column(ratio=1, no_wrap=True)
                grid.add_row(_make_badge("STATUS", status_text, status_dot))
                grid.add_row(_make_badge("MODEL", self.model_name))
                grid.add_row(_make_badge("WORKSPACE", ws_display))
                grid.add_row(_make_badge("PEP", f"Level {self.pep_level} (Supervised)"))
            else:
                # 2 colunas padrão (80 cols)
                grid = Table.grid(padding=(0, 2), expand=True)
                grid.add_column(ratio=1, no_wrap=True)
                grid.add_column(ratio=1, no_wrap=True)
                grid.add_row(
                    _make_badge("STATUS", status_text, status_dot),
                    _make_badge("MODEL", self.model_name),
                )
                grid.add_row(
                    _make_badge("AUTH", auth_val),
                    _make_badge("WORKSPACE", ws_display),
                )
                grid.add_row(
                    _make_badge("PEP", f"Level {self.pep_level} (Supervised)"),
                    _make_badge("MEMORY", "5 Spheres Active"),
                )

            return Group(
                top_content,
                Rule(style=ORION_COLORS["border_subtle"]),
                grid,
                Rule(style=ORION_COLORS["border_subtle"]),
            )

        # 📐 Cenário B: Modo Standard / Amplo (>= 100 colunas)
        header_text = Text(no_wrap=True)
        header_text.append(
            f"  O.R.I.O.N (ORION)  v{__version__} │ Operational Reasoning & Intelligence Orchestration Network\n",
            style="accent_cyan",
        )
        header_text.append(
            '  "Non Ducor, Duco — The Sovereign Cognitive Operating Partner"\n',
            style="text_dim",
        )

        grid_wide = Table.grid(padding=(0, 3), expand=True)
        grid_wide.add_column(ratio=1, no_wrap=True)
        grid_wide.add_column(ratio=1, no_wrap=True)

        grid_wide.add_row(
            _make_badge("STATUS", status_text, status_dot),
            _make_badge("MODEL", f"{self.model_name} [Thinking: {self.reasoning_effort.value}]"),
        )
        grid_wide.add_row(
            _make_badge("AUTH", auth_val),
            _make_badge("WORKSPACE", ws_display),
        )
        grid_wide.add_row(
            _make_badge("PEP GOVERNANCE", f"Level {self.pep_level} (Supervised)"),
            _make_badge("MEMORY", "5 Spheres Active"),
        )

        return Group(
            header_text,
            Rule(style=ORION_COLORS["border_subtle"]),
            grid_wide,
            Rule(style=ORION_COLORS["border_subtle"]),
        )

    def status_segments(self, width: int = 80) -> list[tuple[str, str]]:
        """Monta a linha de status como pares (papel, texto) por faixa de largura.

        Papéis: mode, dim, sep, pep, ok, offline. A mesma fonte alimenta o prompt
        (prompt_toolkit) e o rodapé do streaming (Rich).
        """

        def _fmt_tokens(n: int) -> str:
            if n >= 1000:
                val = n / 1000.0
                text = f"{val:.1f}k" if val < 100 else f"{round(val)}k"
                return text.replace(".0k", "k")
            return str(n)

        sep = ("sep", " · ")
        cost = f"${self.session_cost_usd:.4f}"
        short_model = self.model_name.replace("-thinking", "")
        if self.fast_mode:
            short_model += " (fast)"
        if not self.is_online:
            state = ("offline", "Offline ●")
        elif self.is_busy:
            state = ("ok", "Working ●")
        else:
            state = ("ok", "Ready ●")

        if width >= 110:
            tokens_in = _fmt_tokens(self.session_tokens_in)
            tokens_out = _fmt_tokens(self.session_tokens_out)
            return [
                ("mode", self.agent_mode),
                sep,
                ("dim", short_model),
                sep,
                ("dim", f"{tokens_in} in / {tokens_out} out"),
                sep,
                ("dim", f"{cost} / R$ {self.format_cost_brl()}"),
                sep,
                ("dim", f"thinking: {self.reasoning_effort.value.lower()}"),
                sep,
                ("pep", f"PEP: {self.pep_level}"),
                sep,
                state,
            ]

        abbreviated = short_model.split("/")[-1]
        if width >= 80:
            total = _fmt_tokens(self.session_tokens_in + self.session_tokens_out)
            return [
                ("dim", abbreviated),
                sep,
                ("dim", f"{total} tok"),
                sep,
                ("dim", cost),
                sep,
                state,
            ]
        return [("dim", abbreviated), sep, ("dim", cost), sep, state]

    def render_bottom_bar(self, width: int = 80) -> RenderableType:
        """Gera a linha de status inferior sobre o fundo nativo do terminal."""
        styles = {
            "mode": "accent_blue",
            "dim": "text_dim",
            "sep": "border_subtle",
            "pep": "pep_warn",
            "ok": "status_ok",
            "offline": "status_offline",
        }
        line = Text(no_wrap=True)
        for role, text in self.status_segments(width):
            line.append(text, style=styles[role])
        return line
