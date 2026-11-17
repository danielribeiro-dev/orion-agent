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
from rich.text import Text

from orion import __version__
from orion.tui.theme import ORION_COLORS


class ReasoningEffort(StrEnum):
    """Níveis de esforço de raciocínio profundo."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    OFF = "OFF"


# Tipografia oficial Stellar Cyber Block (6 linhas) e versão reduzida (4 linhas, < 70 colunas)
STELLAR_CYBER_BLOCK: list[str] = [
    "  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗",
    " ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║",
    " ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║",
    " ██║   ██║██╔══██╗██║██║   ██║██║╚██╗██║",
    " ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║",
    "  ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝",
]
STELLAR_COMPACT: list[str] = [
    "  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗",
    " ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║",
    " ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║",
    " ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║",
]
_LOGO_WIDTH = max(len(row) for row in STELLAR_CYBER_BLOCK)


def _gradient(index: int, total: int) -> str:
    """Cor da linha *index* do logo no gradiente vertical cyan → azul Órion."""
    t = index / (total - 1) if total > 1 else 0.0
    start, end = ORION_COLORS["accent_cyan"], ORION_COLORS["accent_blue"]
    channels = [
        round(int(start[i : i + 2], 16) + (int(end[i : i + 2], 16) - int(start[i : i + 2], 16)) * t)
        for i in (1, 3, 5)
    ]
    return "#" + "".join(f"{c:02x}" for c in channels)


def _make_badge(label: str, value: str, dot_style: str = "accent_cyan") -> Text:
    """Cria um badge no formato '● LABEL: Valor' com cores do Design System."""
    t = Text(no_wrap=True)
    t.append("● ", style=dot_style)
    t.append(f"{label}: ", style="text_dim")
    t.append(value, style="text_primary")
    return t


_EFFORT_PT = {
    ReasoningEffort.MEDIUM: "esforço médio",
    ReasoningEffort.LOW: "esforço baixo",
    ReasoningEffort.OFF: "sem raciocínio",
}


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
    agent_mode: str = "auto"
    is_busy: bool = False
    #: tasks em segundo plano em execução / notificações ainda não mostradas (Sprint 6B)
    bg_running: int = 0
    bg_unread: int = 0
    fast_mode: bool = False
    #: % da janela de contexto em uso (calculado pela sessão após cada turno); None: oculto
    context_pct: int | None = None
    #: modal de autorização aberto (estado "Aguardando" na status line)
    awaiting: bool = False

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

    def _workspace_display(self) -> str:
        ws_display = self.workspace_path or str(Path.cwd())
        try:
            home_dir = str(Path.home())
            if ws_display.startswith(home_dir):
                ws_display = "~" + ws_display[len(home_dir) :]
        except Exception:
            pass
        return ws_display if len(ws_display) <= 36 else "…" + ws_display[-35:]

    def _state_line(self, *, workspace: bool = True) -> Text:
        """`● online · modelo · ~/projeto`, ou o aviso neutro sem provedor (V-07)."""
        line = Text(no_wrap=True, overflow="ellipsis")
        sep = ("  ·  ", "faint")
        if self.is_online:
            line.append("  ● ", style="status_ok")
            line.append("online", style="text_primary")
        else:
            line.append("  ● ", style="pep_warn")
            line.append("sem chave de provedor · /config", style="pep_warn")
        line.append(*sep)
        line.append(self.model_name, style="text_primary")
        if workspace:
            line.append(*sep)
            line.append(self._workspace_display(), style="text_dim")
        return line

    def _governance_line(self) -> Text:
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(f"  PEP {self.pep_level} supervisionado", style="pep_warn")
        line.append("  ·  ", style="faint")
        line.append("memória 5 esferas", style="text_dim")
        return line

    def _title_line(self) -> Text:
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append("  O.R.I.O.N", style=f"bold {ORION_COLORS['accent_cyan']}")
        line.append(f"  v{__version__}", style="text_dim")
        line.append("  ·  ", style="faint")
        line.append("Non Ducor, Duco", style="text_dim")
        return line

    def render_header_panel(self, width: int = 80) -> RenderableType:
        """Cabeçalho Horizon (ADR-039): logo à esquerda e informação à direita, sem badges.

        >= 100 colunas: informação ao lado do logo. 70 a 99: abaixo do logo. < 70: logo reduzido.
        """
        if width < 70:
            out = Text(no_wrap=True, overflow="crop")
            for compact in STELLAR_COMPACT:
                out.append(compact[:width] + "\n", style=f"bold {ORION_COLORS['accent_cyan']}")
            return Group(out, self._title_line(), self._state_line(workspace=False))

        logo = [
            Text(row, style=f"bold {_gradient(i, len(STELLAR_CYBER_BLOCK))}", no_wrap=True)
            for i, row in enumerate(STELLAR_CYBER_BLOCK)
        ]
        if width < 100:
            return Group(*logo, self._title_line(), self._state_line(), self._governance_line())

        desc = Text(
            "  Operational Reasoning & Intelligence Orchestration Network",
            style="text_dim", no_wrap=True,
        )
        side: list[Text | None] = [
            None, self._title_line(), desc, None, self._state_line(), self._governance_line(),
        ]
        rows: list[RenderableType] = []
        for art, info in zip(logo, side, strict=True):
            line = art.copy()
            line.pad_right(_LOGO_WIDTH - len(line.plain))
            if info is not None:
                line.append_text(info)
            line.truncate(width, overflow="ellipsis")
            rows.append(line)
        return Group(*rows)

    def _background_segment(self) -> list[tuple[str, str]]:
        """``tasks 2 ● · 1 ✔``: em execução e concluídas ainda não vistas (vazio se nada)."""
        if not (self.bg_running or self.bg_unread):
            return []
        parts = []
        if self.bg_running:
            parts.append(f"{self.bg_running} ●")
        if self.bg_unread:
            parts.append(f"{self.bg_unread} ✔")
        return [("ok", "tasks " + " ".join(parts)), ("sep", " · ")]

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
        bg = self._background_segment()
        cost = f"US$ {self.session_cost_usd:.3f}".replace(".", ",")
        short_model = self.model_name.replace("-thinking", "")
        if self.fast_mode:
            short_model += " (rápido)"
        effort = _EFFORT_PT.get(self.reasoning_effort, "")
        if effort:
            short_model += f" · {effort}"
        if not self.is_online:
            state = [("dim", "Offline "), ("pep", "●")]
        elif self.awaiting:
            state = [("dim", "Aguardando "), ("pep", "●")]
        elif self.is_busy:
            state = [("dim", "Trabalhando "), ("cyan", "●")]
        else:
            state = [("dim", "Pronto "), ("ok", "●")]
        ctx = [("dim", f"{self.context_pct}% ctx"), sep] if self.context_pct is not None else []
        # Modo e PEP nunca somem (N-04): são sinais de segurança; modelo e contexto cedem antes.
        head = [("mode", self.agent_mode), sep]
        pep = [("pep", f"PEP {self.pep_level}"), sep]
        if width >= 110:
            return [*head, ("dim", short_model), sep, *ctx, ("dim", cost), sep, *pep, *bg, *state]
        abbreviated = short_model.split("/")[-1]
        if width >= 80:
            return [*head, ("dim", abbreviated), sep, *ctx, ("dim", cost), sep, *pep, *bg, *state]
        return [*head, ("dim", cost), sep, *pep, *bg, *state]

    def render_bottom_bar(self, width: int = 80) -> RenderableType:
        """Gera a linha de status inferior sobre o fundo nativo do terminal."""
        styles = {
            "mode": f"bold {ORION_COLORS['accent_blue']}",
            "dim": "text_dim",
            "sep": "faint",
            "pep": "pep_warn",
            "ok": "status_ok",
            "cyan": "accent_cyan",
            "offline": "status_offline",
        }
        line = Text(no_wrap=True)
        for role, text in self.status_segments(width):
            line.append(text, style=styles[role])
        return line
