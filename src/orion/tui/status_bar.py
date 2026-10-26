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
from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

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
        """Gera o painel de cabeçalho formatado em Rich com bordas arredondadas."""
        auth_val = f"GitHub [@{self.github_user}]" if self.github_user else "Local (Not connected)"
        google_val = self.google_account or "Not connected"
        gateway_status = "Online (Auto-Routing)" if self.is_online else "Offline (Local Only)"
        status_dot = "status_ok" if self.is_online else "status_offline"

        if width < 100:
            # 📐 Cenário A: Modo Compacto (< 100 colunas)
            # Tipografia Stellar Cyber Block
            cyber_block = [
                ("  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗", "   O.R.I.O.N (ORION)  v0.4.0"),
                (" ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║", "   Sovereign Cognitive Agent"),
                (" ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║", "   github.com/danielribeiro-dev"),
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
                grid.add_row(_make_badge("GATEWAY", gateway_status, status_dot))
                grid.add_row(_make_badge("MODEL", self.model_name))
                grid.add_row(_make_badge("REASONING", self.reasoning_effort.value))
                grid.add_row(_make_badge("PEP", f"Level {self.pep_level} (Supervised)"))
            else:
                # 2 colunas padrão (80 cols)
                grid = Table.grid(padding=(0, 1), expand=True)
                grid.add_column(ratio=1, no_wrap=True)
                grid.add_column(ratio=1, no_wrap=True)
                grid.add_row(
                    _make_badge("GATEWAY", gateway_status, status_dot),
                    _make_badge("MODEL", self.model_name),
                )
                grid.add_row(
                    _make_badge("REASONING", f"{self.reasoning_effort.value} (Depth Thinking)"),
                    _make_badge("AUTH", auth_val),
                )
                grid.add_row(
                    _make_badge("MEMORY", f"5 Spheres ({self.events_count} Events)"),
                    _make_badge("PEP", f"Level {self.pep_level} (Supervised)"),
                )

            return Panel(
                Group(top_content, Rule(style=ORION_COLORS["border_subtle"]), grid),
                box=box.ROUNDED,
                width=width,
                border_style=ORION_COLORS["border_subtle"],
            )

        # 📐 Cenário B: Modo Standard / Amplo (>= 100 colunas)
        header_text = Text(no_wrap=True)
        header_text.append(
            "  O.R.I.O.N (ORION)  v0.4.0 │ Operational Reasoning & Intelligence Orchestration Network\n",
            style="accent_cyan",
        )
        header_text.append(
            '  "Non Ducor, Duco — The Sovereign Cognitive Operating Partner"\n',
            style="text_dim",
        )

        grid_wide = Table.grid(padding=(0, 2), expand=True)
        grid_wide.add_column(ratio=1, no_wrap=True)
        grid_wide.add_column(ratio=1, no_wrap=True)

        status_text = "ONLINE (Cloud Gateway)" if self.is_online else "OFFLINE (Local Gateway)"
        grid_wide.add_row(
            _make_badge("STATUS", status_text, status_dot),
            _make_badge("REASONING", f"{self.reasoning_effort.value} (Depth Thinking Active)"),
        )
        grid_wide.add_row(
            _make_badge("MODEL", self.model_name),
            _make_badge("GATEWAY", "Auto-Routing (Fast/Deep Dynamic)"),
        )
        grid_wide.add_row(
            _make_badge("AUTH", auth_val),
            _make_badge("GOOGLE", google_val),
        )
        grid_wide.add_row(
            _make_badge("TIMELINE", f"{self.events_count} events in SQLite WAL"),
            _make_badge("MEMORY", "5 Spheres Active (FTS5 + ONNX Embeddings)"),
        )
        ws_display = self.workspace_path or "/home/danieldev/orion-agent"
        if len(ws_display) > 35:
            ws_display = "..." + ws_display[-32:]
        grid_wide.add_row(
            _make_badge("PEP GOVERNANCE", f"Level {self.pep_level} (Supervised)"),
            _make_badge("WORKSPACE", ws_display),
        )

        return Panel(
            Group(header_text, Rule(style=ORION_COLORS["border_subtle"]), grid_wide),
            box=box.ROUNDED,
            width=width,
            border_style=ORION_COLORS["border_subtle"],
        )

    def render_bottom_bar(self, width: int = 80) -> RenderableType:
        """Gera a linha de status inferior com tokens e custos em USD e BRL sem estouro."""
        cost_str = f"{self.format_cost_usd()} (~R$ {self.format_cost_brl()})"
        status_dot_str = "Ready ●" if self.is_online else "Offline ●"
        status_dot_style = "status_ok" if self.is_online else "status_offline"

        # Cenário 1: Largura Ampla (>= 115 colunas — Cenário C completo)
        full_candidate_len = (
            len(self.model_name)
            + len(self.reasoning_effort.value)
            + len(cost_str)
            + len(status_dot_str)
            + 70
        )
        if width >= full_candidate_len:
            t = Text(no_wrap=True)
            t.append(f"[{self.model_name}]", style="accent_cyan")
            t.append(" ")
            t.append(f"[Thinking: {self.reasoning_effort.value}]", style="accent_blue")
            t.append(" ")
            t.append(f"[PEP: Level {self.pep_level}]", style="pep_warn")
            t.append(" │ ", style="border_subtle")
            t.append(
                f"Tokens: {self.session_tokens_in:,} in / {self.session_tokens_out:,} out",
                style="text_dim",
            )
            t.append(" │ ", style="border_subtle")
            t.append(cost_str, style="text_primary")
            t.append(" │ ", style="border_subtle")
            t.append(status_dot_str, style=status_dot_style)
            return t

        short_model = self.model_name.replace("-thinking", "")

        # Cenário 2: Largura Média (>= 90 colunas)
        med_candidate_len = len(short_model) + len(cost_str) + len(status_dot_str) + 50
        if width >= med_candidate_len:
            t = Text(no_wrap=True)
            t.append(f"[{short_model}]", style="accent_cyan")
            t.append(" ")
            t.append(f"[{self.reasoning_effort.value}]", style="accent_blue")
            t.append(" ")
            t.append(f"[PEP:{self.pep_level}]", style="pep_warn")
            t.append(" │ ", style="border_subtle")
            t.append(
                f"Tokens: {self.session_tokens_in:,}/{self.session_tokens_out:,}",
                style="text_dim",
            )
            t.append(" │ ", style="border_subtle")
            t.append(cost_str, style="text_primary")
            t.append(" │ ", style="border_subtle")
            t.append(status_dot_str, style=status_dot_style)
            return t

        # Cenário 3: Terminal Padrão 80 Colunas (>= 72 colunas)
        std_candidate_len = len(short_model) + len(cost_str) + len(status_dot_str) + 26
        if width >= std_candidate_len:
            t = Text(no_wrap=True)
            t.append(f"[{short_model}]", style="accent_cyan")
            t.append(" │ ", style="border_subtle")
            t.append(
                f"{self.session_tokens_in:,}/{self.session_tokens_out:,} tok",
                style="text_dim",
            )
            t.append(" │ ", style="border_subtle")
            t.append(cost_str, style="text_primary")
            t.append(" │ ", style="border_subtle")
            t.append(status_dot_str, style=status_dot_style)
            return t

        # Cenário 4: Terminal Estreito (60 colunas)
        t = Text(no_wrap=True)
        t.append(
            f"{self.session_tokens_in:,}/{self.session_tokens_out:,} tok",
            style="text_dim",
        )
        t.append(" │ ", style="border_subtle")
        t.append(cost_str, style="text_primary")
        t.append(" │ ", style="border_subtle")
        t.append(status_dot_str, style=status_dot_style)
        return t
