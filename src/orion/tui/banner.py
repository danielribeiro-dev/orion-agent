"""
O.R.I.O.N TUI — Adaptive Cosmic Banner & Horizon Renderer.

Renderizador dinâmico da Mão Cósmica com o Buraco Negro e da tipografia Stellar Cyber Block,
adaptando-se cirurgicamente para 80, 120 e 200+ colunas sem qualquer estouro ou flickering.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Group, RenderableType
from rich.text import Text

from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import ORION_COLORS


def _interpolate_color(start_hex: str, end_hex: str, t: float) -> str:
    """Interpola linearmente entre duas cores hexadecimais no espaço RGB."""
    r1, g1, b1 = int(start_hex[1:3], 16), int(start_hex[3:5], 16), int(start_hex[5:7], 16)
    r2, g2, b2 = int(end_hex[1:3], 16), int(end_hex[3:5], 16), int(end_hex[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------------------------------------------------------------
# Tipografia Oficial Stellar Cyber Block (6 linhas, 42 colunas)
# ---------------------------------------------------------------------------

STELLAR_CYBER_BLOCK: list[str] = [
    "  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗",
    " ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║",
    " ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║",
    " ██║   ██║██╔══██╗██║██║   ██║██║╚██╗██║",
    " ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║",
    "  ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝",
]


class BannerRenderer:
    """Motor de renderização do banner adaptativo do O.R.I.O.N."""

    def __init__(
        self,
        ascii_art_path: Path | None = None,
        status_bar: SessionStatusBar | None = None,
    ) -> None:
        """Inicializa o renderizador carregando a arte ASCII de inicialização."""
        self.status_bar = status_bar or SessionStatusBar.from_environment()
        self.raw_lines: list[str] = []

        if ascii_art_path is not None:
            self._load_art(ascii_art_path)
        else:
            # Tenta descobrir o caminho padrão no repositório
            candidate_paths = [
                Path(__file__).resolve().parents[3] / "docs" / "design" / "ascii-art.txt",
                Path.cwd() / "docs" / "design" / "ascii-art.txt",
            ]
            for candidate in candidate_paths:
                if candidate.is_file():
                    self._load_art(candidate)
                    break

    def _load_art(self, path: Path) -> None:
        """Carrega as linhas de arte ASCII de forma segura."""
        try:
            if path.is_file():
                with open(path, encoding="utf-8") as f:
                    self.raw_lines = [line.rstrip() for line in f.readlines()]
        except Exception:
            self.raw_lines = []

    def render_art(self, terminal_width: int | None = None) -> RenderableType:
        """Renderiza o logo ASCII oficial adaptado para a largura especificada.

        - width < 100: Retorna Stellar Cyber Block monocromático cyan.
        - width >= 100: Retorna Stellar Cyber Block com gradiente cósmico TrueColor (#00D2FF -> #3A7BD5).
        """
        width = terminal_width or shutil.get_terminal_size((80, 24)).columns

        if width < 100:
            art_text = Text(no_wrap=True)
            for line in STELLAR_CYBER_BLOCK:
                art_text.append(line[:width] + "\n", style="accent_cyan")
            return art_text

        # width >= 100: Stellar Cyber Block com Gradiente TrueColor (#00D2FF -> #3A7BD5)
        grad_text = Text(no_wrap=True)
        num_rows = len(STELLAR_CYBER_BLOCK)
        for idx, line in enumerate(STELLAR_CYBER_BLOCK):
            t = idx / (num_rows - 1) if num_rows > 1 else 0.0
            color = _interpolate_color(ORION_COLORS["accent_cyan"], ORION_COLORS["accent_blue"], t)
            grad_text.append(line[:width] + "\n", style=color)

        return grad_text

    def render(self, terminal_width: int | None = None) -> RenderableType:
        """Renderiza o banner adaptativo completo com cabeçalho e dica rápida.

        Regras de Largura:
        - width < 100: Retorna o layout compacto (Stellar Cyber Block + Badges de 2 colunas).
        - width >= 100: Retorna o layout standard/amplo com gradiente cyan/azul cósmico.
        """
        width = terminal_width or shutil.get_terminal_size((80, 24)).columns

        header_panel = self.status_bar.render_header_panel(width=width)

        if width < 75:
            hint_text = "  Dica: Digite / para comandos, @ para arquivos, Esc para limpar."
            if len(hint_text) > width:
                hint_text = hint_text[:width]
            hint = Text(hint_text, style="text_dim", no_wrap=True)
            return Group(header_panel, hint)

        if width < 100:
            hint_text = "  Dica: Digite / para comandos, @ para arquivos, Esc para limpar/voltar e Ctrl+C duplo para sair."
            if len(hint_text) > width:
                hint_text = hint_text[:width]
            hint = Text(hint_text, style="text_dim", no_wrap=True)
            return Group(header_panel, hint)

        art = self.render_art(terminal_width=width)
        hint_wide_text = "  Dica: Digite / para comandos rápidos, @ para anexar arquivos locais, Esc para limpar/voltar e Ctrl+C duplo para sair."
        if len(hint_wide_text) > width:
            hint_wide_text = hint_wide_text[:width]
        hint_wide = Text(hint_wide_text, style="text_dim", no_wrap=True)
        return Group(art, header_panel, hint_wide)
