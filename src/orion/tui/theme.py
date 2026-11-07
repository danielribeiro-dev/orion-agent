"""
Design System Oficial do O.R.I.O.N — Paleta Deep Cosmos & Glacial Platinum.

Calibrada para conforto ergonômico em sessões prolongadas de trabalho (12h+ sem fadiga visual),
com contraste WCAG AAA superior a 13:1 e fidelidade harmônica com a temática cósmica do O.R.I.O.N.
"""

from __future__ import annotations

from pygments.token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    String,
    Token,
)
from rich.style import Style
from rich.syntax import ANSISyntaxTheme
from rich.theme import Theme

# Paleta oficial Deep Cosmos & Glacial Platinum
ORION_COLORS: dict[str, str] = {
    # Fundos e Superfícies
    "bg_canvas": "#0B0E14",  # Fundo do terminal (Preto Cosmos Suave)
    "surface_panel": "#151B23",  # Fundo de cards, caixas e diffs (Grafite Estelar)
    "border_subtle": "#262F3D",  # Bordas e separadores discretos
    # Textos e Leitura Prolongada (WCAG AAA > 13:1)
    "text_primary": "#E6EDF3",  # Branco Glacial para respostas do agente
    "text_dim": "#8B949E",  # Cinza Titânio Fosco para metadados e logs
    "text_user": "#F0F6FC",  # Branco Iluminado para input do usuário
    # Identidade Cósmica do ORION
    "accent_cyan": "#00D2FF",  # Cyan Cósmico (Buraco Negro, logos e badges)
    "accent_blue": "#3A7BD5",  # Azul Órion Profundo (links e modos)
    # Acentos Semânticos Funcionais
    "diff_add": "#3FB950",  # Verde Aurora Suave (Linhas adicionadas)
    "diff_del": "#F85149",  # Vermelho Alerta Suave (Linhas removidas)
    "diff_add_tint": "#12261C",  # diff_add a 14% sobre bg_canvas (fundo de linha adicionada)
    "diff_del_tint": "#2C171B",  # diff_del a 14% sobre bg_canvas (fundo de linha removida)
    "pep_warn": "#D29922",  # Âmbar de Ignição (Avisos de permissão PEP)
    "status_ok": "#2EA043",  # Verde de Conectividade Online
    "status_offline": "#DA3633",  # Vermelho de Modo Offline / Failover
}


def get_syntax_theme() -> ANSISyntaxTheme:
    """Tema de realce sintático restrito às cores de ORION_COLORS."""
    c = ORION_COLORS
    return ANSISyntaxTheme(
        {
            Token: Style(color=c["text_primary"]),
            Comment: Style(color=c["text_dim"], italic=True),
            Keyword: Style(color=c["accent_cyan"]),
            Name.Function: Style(color=c["accent_blue"]),
            Name.Class: Style(color=c["accent_blue"], bold=True),
            Name.Decorator: Style(color=c["pep_warn"]),
            String: Style(color=c["diff_add"]),
            Number: Style(color=c["pep_warn"]),
            Operator: Style(color=c["text_dim"]),
        }
    )


def get_orion_theme() -> Theme:
    """Retorna a instância Theme do Rich com todos os estilos semânticos do ORION."""
    return Theme(
        {
            # Estilos com prefixo 'orion.'
            "orion.bg": f"on {ORION_COLORS['bg_canvas']}",
            "orion.panel": f"on {ORION_COLORS['surface_panel']}",
            "orion.border": ORION_COLORS["border_subtle"],
            "orion.text": ORION_COLORS["text_primary"],
            "orion.text_primary": ORION_COLORS["text_primary"],
            "orion.text_dim": ORION_COLORS["text_dim"],
            "orion.text_user": f"bold {ORION_COLORS['text_user']}",
            "orion.cyan": f"bold {ORION_COLORS['accent_cyan']}",
            "orion.blue": ORION_COLORS["accent_blue"],
            "orion.diff_add": f"bold {ORION_COLORS['diff_add']}",
            "orion.diff_del": f"bold {ORION_COLORS['diff_del']}",
            "orion.pep_warn": f"bold {ORION_COLORS['pep_warn']}",
            "orion.status_ok": f"bold {ORION_COLORS['status_ok']}",
            "orion.status_offline": f"bold {ORION_COLORS['status_offline']}",
            # Aliases diretos por chave de cor
            "bg_canvas": f"on {ORION_COLORS['bg_canvas']}",
            "surface_panel": f"on {ORION_COLORS['surface_panel']}",
            "border_subtle": ORION_COLORS["border_subtle"],
            "text_primary": ORION_COLORS["text_primary"],
            "text_dim": ORION_COLORS["text_dim"],
            "text_user": f"bold {ORION_COLORS['text_user']}",
            "accent_cyan": f"bold {ORION_COLORS['accent_cyan']}",
            "accent_cyan bold": f"bold {ORION_COLORS['accent_cyan']}",
            "accent_blue": ORION_COLORS["accent_blue"],
            "accent_blue bold": f"bold {ORION_COLORS['accent_blue']}",
            "diff_add": f"bold {ORION_COLORS['diff_add']}",
            "diff_del": f"bold {ORION_COLORS['diff_del']}",
            "pep_warn": f"bold {ORION_COLORS['pep_warn']}",
            "status_ok": f"bold {ORION_COLORS['status_ok']}",
            "status_offline": f"bold {ORION_COLORS['status_offline']}",
            "diff_add_line": f"on {ORION_COLORS['diff_add_tint']}",
            "diff_del_line": f"on {ORION_COLORS['diff_del_tint']}",
            # Markdown renderizado no streaming
            "markdown.h1": f"bold {ORION_COLORS['text_user']}",
            "markdown.h2": f"bold {ORION_COLORS['text_user']}",
            "markdown.h3": f"bold {ORION_COLORS['text_primary']}",
            "markdown.h4": f"bold {ORION_COLORS['text_primary']}",
            "markdown.code": ORION_COLORS["accent_cyan"],
            "markdown.link": ORION_COLORS["accent_blue"],
            "markdown.link_url": ORION_COLORS["accent_blue"],
            "markdown.item.bullet": ORION_COLORS["accent_cyan"],
            "markdown.item.number": ORION_COLORS["accent_cyan"],
            "markdown.block_quote": ORION_COLORS["text_dim"],
            "markdown.hr": ORION_COLORS["border_subtle"],
        }
    )
