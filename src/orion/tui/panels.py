"""
O.R.I.O.N TUI — Panels.

Renderizadores puros (sem E/S de teclado) dos blueprints de CLI_DESIGN_SYSTEM §4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich import box
from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from orion.governance.permissions import ActionLevel
from orion.tui.theme import ORION_COLORS


def orion_panel(body: RenderableType, title: Text, border: str = "border_subtle") -> Panel:
    """Moldura padrão: borda arredondada fina com título embutido."""
    return Panel(
        body,
        title=title,
        title_align="left",
        box=box.ROUNDED,
        border_style=border,
        padding=(1, 2),
    )


def brand_title(text: str) -> Text:
    """Título `O.R.I.O.N — texto`."""
    title = Text()
    title.append(" O.R.I.O.N", style="accent_cyan")
    title.append(f" — {text} ", style="text_primary")
    return title


def plain_title(text: str) -> Text:
    """Título simples do painel."""
    return Text(f" {text} ", style="text_primary")


def key_hints(*pairs: tuple[str, str]) -> Text:
    """Linha de atalhos: `[Enter] Confirmar │ [Esc] Cancelar`."""
    line = Text("   ")
    for index, (key, label) in enumerate(pairs):
        if index:
            line.append(" │ ", style="border_subtle")
        line.append(f"[{key}]", style="accent_cyan")
        line.append(f" {label}", style="text_dim")
    return line


def _grid(*columns: tuple[str, int | None, str]) -> Table:
    """Tabela sem bordas, com cabeçalho atenuado e régua sutil."""
    table = Table(
        box=box.SIMPLE_HEAD,
        expand=True,
        show_edge=False,
        pad_edge=False,
        header_style="text_dim",
        border_style="border_subtle",
    )
    for header, width, justify in columns:
        table.add_column(header, width=width, no_wrap=True, justify=justify)  # type: ignore[arg-type]
    return table


_PROVIDER_NAMES = {"openrouter": "OpenRouter", "ollama": "Ollama"}

# ── /model ──────────────────────────────────────────────────────────────


def render_model_picker(rows: list[Any], selected: int, current: str, query: str = "") -> Group:
    """Blueprint B. *rows* são ModelSpec do registry."""
    table = _grid(
        ("  Provedor", 14, "left"),
        ("Modelo", None, "left"),
        ("Contexto", 10, "left"),
        ("Custo (In/Out 1M)", 20, "left"),
    )
    for index, spec in enumerate(rows):
        active = index == selected
        style = "accent_cyan" if active else "text_primary"
        marker = "● " if spec.id == current else "  "
        cost = (
            "$0.00 (Offline)"
            if spec.cost_input_m == 0 and spec.cost_output_m == 0
            else f"${spec.cost_input_m:.2f} / ${spec.cost_output_m:.2f}"
        )
        window = f"{spec.context_window // 1000}k"
        provider = _PROVIDER_NAMES.get(spec.provider.value, spec.provider.value)
        table.add_row(
            Text(marker + provider, style=style),
            Text(spec.id, style=style),
            Text(window, style=style),
            Text(cost, style=style),
        )
    if not rows:
        table.add_row(Text("  Nenhum modelo", style="text_dim"), "", "", "")
    hint = Text(f"   Filtro: {query}" if query else "   Digite para filtrar", style="text_dim")
    hint.append(" │ ", style="border_subtle")
    hint.append("[Enter]", style="accent_cyan")
    hint.append(" Confirmar", style="text_dim")
    hint.append(" │ ", style="border_subtle")
    hint.append("[Esc]", style="accent_cyan")
    hint.append(" Cancelar", style="text_dim")
    return Group(orion_panel(table, plain_title("Seleção de Modelo de IA")), hint)


# ── /memory ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SphereRow:
    """Linha do inspetor de esferas cognitivas."""

    name: str
    status: str
    items: str
    storage: str


def render_memory(rows: list[SphereRow]) -> Group:
    """Blueprint C."""
    table = _grid(
        ("  Esfera", 22, "left"),
        ("Status", 10, "left"),
        ("Itens", 14, "left"),
        ("Armazenamento", None, "left"),
    )
    for row in rows:
        name = Text()
        name.append("● ", style="accent_blue")
        name.append(row.name, style="text_primary")
        ok = row.status == "Ativa"
        table.add_row(
            name,
            Text(row.status, style="status_ok" if ok else "pep_warn"),
            Text(row.items, style="text_primary"),
            Text(row.storage, style="text_dim"),
        )
    return Group(orion_panel(table, brand_title("Inspetor das 5 Esferas Cognitivas")))


# ── /context ────────────────────────────────────────────────────────────

_CONTEXT_STYLES = {
    "sistema": "text_dim",
    "ferramentas": ORION_COLORS["accent_blue"],
    "memória": ORION_COLORS["accent_cyan"],
    "arquivos": "text_primary",
    "conversa": ORION_COLORS["status_ok"],
}


def render_context(parts: dict[str, int], window: int, bar_width: int = 72) -> Panel:
    """Blueprint E: barra de composição e legenda com percentuais."""
    used = sum(parts.values())
    free = max(window - used, 0)
    bar = Text(no_wrap=True)
    filled = 0
    for name, tokens in parts.items():
        cells = round(tokens / window * bar_width) if window else 0
        if tokens and not cells:
            cells = 1
        bar.append("█" * cells, style=_CONTEXT_STYLES.get(name, "text_dim"))
        filled += cells
    bar.append("░" * max(bar_width - filled, 0), style="text_dim")

    legend = Text()
    for name, tokens in parts.items():
        legend.append("█ ", style=_CONTEXT_STYLES.get(name, "text_dim"))
        legend.append(_legend_row(name, tokens, window) + "\n", style="text_dim")
    legend.append("░ ", style="text_dim")
    legend.append(_legend_row("livre", free, window), style="text_dim")

    title = plain_title("Janela de Contexto")
    percent = used / window * 100 if window else 0.0
    title.append(f"{_fmt_k(used)} / {_fmt_k(window)} ({percent:.0f}%) ", style="accent_cyan")
    return orion_panel(Group(bar, Text(""), legend), title)


def _legend_row(name: str, tokens: int, window: int) -> str:
    percent = tokens / window * 100 if window else 0.0
    return f"{name:<14}{_fmt_k(tokens):>7}{percent:>7.1f}%"


def _fmt_k(value: int) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f}k".replace(".0k", "k")
    return str(value)


# ── /cost ───────────────────────────────────────────────────────────────


def render_cost(
    tokens_in: int,
    tokens_out: int,
    tokens_cached: int,
    cost_in: float,
    cost_out: float,
    cost_total: float,
    cost_brl: str,
) -> Panel:
    """Blueprint F: livro-razão da sessão."""
    table = _grid(("Tipo", 18, "left"), ("Tokens", 10, "right"), ("USD", 12, "right"), ("", None, "left"))
    table.add_row("Entrada", f"{tokens_in:,}", f"${cost_in:.4f}", "")
    table.add_row("Saída", f"{tokens_out:,}", f"${cost_out:.4f}", "")
    table.add_row("Cache", f"{tokens_cached:,}", "incluso", "")
    table.add_row(
        Text("Total", style="accent_cyan"),
        Text(f"{tokens_in + tokens_out:,}", style="accent_cyan"),
        Text(f"${cost_total:.4f}", style="accent_cyan"),
        Text(f"  R$ {cost_brl}", style="text_dim"),
    )
    return orion_panel(table, plain_title("Livro-Razão da Sessão"))


# ── /config ─────────────────────────────────────────────────────────────


def render_config(
    categories: list[str],
    category: int,
    settings: list[tuple[str, str]],
    setting: int,
    focus_right: bool,
    notes: list[str],
) -> Panel:
    """Blueprint A: master-detail com categorias à esquerda e opções à direita."""
    left = Text(no_wrap=True)
    for index, name in enumerate(categories):
        active = index == category
        left.append("● " if active else "  ", style="accent_cyan")
        left.append(name + "\n", style="accent_cyan" if active else "text_primary")

    right = Text(no_wrap=True)
    for index, (label, value) in enumerate(settings):
        active = focus_right and index == setting
        right.append(f"{label:<22}", style="text_dim")
        right.append(f"[ {value} ]\n", style="accent_cyan" if active else "text_primary")
    if notes:
        right.append("\n")
        for note in notes:
            right.append(f"• {note}\n", style="text_dim")

    columns = Table.grid(padding=(0, 4))
    columns.add_column(no_wrap=True)
    columns.add_column(no_wrap=True)
    columns.add_row(Text("Categorias (↑/↓)", style="text_dim"), Text(f"Configuração: {categories[category]}", style="text_user"))
    columns.add_row(left, right)

    return orion_panel(
        Group(
            columns,
            Rule(style="border_subtle"),
            key_hints(("↑/↓", "Navegar"), ("Tab", "Alternar Painel"), ("Enter", "Alterar"), ("Esc/q", "Sair")),
        ),
        brand_title("Painel de Configurações Operacionais"),
    )


# ── PEP ─────────────────────────────────────────────────────────────────

_ACTION_NAMES = {
    "run_command": "Execução de Comando no Sistema Operacional",
    "write_file": "Escrita de Arquivo",
    "edit_file": "Edição Cirúrgica de Arquivo",
}


def describe_action(tool: str, params: dict[str, Any]) -> tuple[str, str, str]:
    """Traduz a ação para os campos do diálogo: ação, alvo e impacto."""
    name = _ACTION_NAMES.get(tool, f"Ferramenta {tool}")
    if tool == "run_command":
        impact = "Executa o comando no workspace atual"
        if params.get("run_in_background"):
            impact = "Executa o comando em segundo plano; continua rodando após a aprovação"
        return name, str(params.get("command", "")), impact
    target = str(params.get("path", params))
    return name, target, "Modifica o arquivo no workspace"


def render_pep_dialog(tool: str, params: dict[str, Any], level: ActionLevel) -> Group:
    """Blueprint D: autorização operacional."""
    action, target, impact = describe_action(tool, params)
    body = Text()
    body.append("Ação Solicitada: ", style="text_dim")
    body.append(action + "\n", style="text_primary")
    body.append("Comando:         " if tool == "run_command" else "Alvo:            ", style="text_dim")
    body.append(target + "\n", style="accent_cyan")
    body.append("Impacto:         ", style="text_dim")
    body.append(impact, style="text_primary")

    title = Text()
    title.append(f" [PEP NÍVEL {int(level)}]", style="pep_warn")
    title.append(" Autorização Operacional Requerida ", style="text_primary")

    keys = Text("   ")
    keys.append("[y]", style="status_ok")
    keys.append(" Aprovar   ", style="text_dim")
    keys.append("[n]", style="diff_del")
    keys.append(" Rejeitar   ", style="text_dim")
    if tool == "run_command":
        keys.append("[e]", style="accent_cyan")
        keys.append(" Editar Comando   ", style="text_dim")
    keys.append("[a]", style="pep_warn")
    keys.append(" Sempre Permitir na Sessão", style="text_dim")
    return Group(orion_panel(body, title, border=ORION_COLORS["pep_warn"]), keys)


def render_question(
    question: str,
    options: list[dict[str, str]],
    selected: int,
    checked: set[int],
    multi: bool,
) -> Group:
    """Pergunta do agente ao Senhor (ask_user): opções navegáveis + resposta livre."""
    body = Text()
    body.append(question + "\n", style="text_primary")
    rows = [*options, {"label": "Outro (digitar resposta)", "description": ""}]
    for index, option in enumerate(rows):
        body.append("\n")
        cursor = "❯" if index == selected else " "
        mark = ""
        if multi and index < len(options):
            mark = "[x] " if index in checked else "[ ] "
        style = "accent_cyan" if index == selected else "text_primary"
        body.append(f"{cursor} {index + 1}. {mark}{option['label']}", style=style)
        if option.get("description"):
            body.append(f"  · {option['description']}", style="text_dim")
    keys = key_hints(("↑↓", "Navegar"), ("Enter", "Escolher"), ("Esc", "Cancelar"))
    if multi:
        keys = key_hints(("↑↓", "Navegar"), ("Espaço", "Marcar"), ("Enter", "Confirmar"), ("Esc", "Cancelar"))
    return Group(orion_panel(body, brand_title("Pergunta do agente")), keys)


def render_plan_approval(plan: str, mode_label: str) -> Group:
    """Plano proposto pelo agente (exit_plan_mode) aguardando aprovação."""
    title = Text()
    title.append(" [PEP]", style="pep_warn")
    title.append(" Plano para aprovação ", style="text_primary")
    keys = Text("   ")
    keys.append("[y]", style="status_ok")
    keys.append(f" Aprovar e sair do modo plano ({mode_label})   ", style="text_dim")
    keys.append("[n]", style="diff_del")
    keys.append(" Continuar planejando", style="text_dim")
    return Group(orion_panel(Markdown(plan.strip()), title, border=ORION_COLORS["pep_warn"]), keys)
