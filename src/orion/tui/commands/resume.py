"""Comandos ``/resume`` e ``/rename``: sessões por nome e data, em árvore (v0.5.3 Sprint 3, ADR-051).

``/resume`` abre um seletor com campo de busca. Filtros: ``hoje``, ``ontem``, ``semana``,
``semana passada``, ``mês``, ``nov``/``novembro``, ``2026-11``, ``2026``, ``16/11``, ``daily``,
``thread``, ``@.`` (workspace atual) e ``@nome``; o resto busca no título e no cartão. A lista
é uma árvore ano › mês › dia, com a daily e as threads do dia aninhadas. Global por padrão.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Group, RenderableType
from rich.text import Text

from orion.sessions import SessionNotFoundError
from orion.sessions.clock import parse_iso, to_local
from orion.sessions.index import SessionRecord
from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult
from orion.tui.modal import is_interactive, run_modal
from orion.tui.panels import orion_panel, plain_title
from orion.tui.screen.host import active_host

if TYPE_CHECKING:
    from orion.sessions.navigator import SessionNavigator

_MONTHS = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
_WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


@dataclass(frozen=True)
class TreeRow:
    """Uma linha da árvore; ``record`` None = cabeçalho (ano, mês ou dia)."""

    depth: int
    label: str
    record: SessionRecord | None = None


def _when(record: SessionRecord) -> str:
    try:
        return to_local(parse_iso(record.updated_at)).strftime("%H:%M")
    except ValueError:
        return ""


def _detail(record: SessionRecord) -> str:
    parts = [f"{record.turn_count} pedido(s)"]
    if record.workspace:
        parts.append(Path(record.workspace).name)
    if when := _when(record):
        parts.append(when)
    if record.closed_at and record.kind == "thread":
        parts.append("fechada")
    parts.append(record.id[:8])
    return " · ".join(parts)


def build_tree(records: list[SessionRecord]) -> list[TreeRow]:
    """Ano › mês › dia; no dia, a daily primeiro e as threads aninhadas nela."""
    by_day: dict[str, list[SessionRecord]] = {}
    for record in records:
        by_day.setdefault(record.local_date, []).append(record)
    rows: list[TreeRow] = []
    year = month = None
    for day_text in sorted(by_day, reverse=True):
        try:
            day = date.fromisoformat(day_text)
        except ValueError:
            continue
        if day.year != year:
            year, month = day.year, None
            rows.append(TreeRow(0, str(day.year)))
        if day.month != month:
            month = day.month
            rows.append(TreeRow(1, _MONTHS[day.month - 1]))
        rows.append(TreeRow(2, f"{day:%d/%m} {_WEEKDAYS[day.weekday()]}"))
        items = by_day[day_text]
        dailies = [r for r in items if r.kind == "daily"]
        threads = sorted((r for r in items if r.kind == "thread"), key=lambda r: r.updated_at, reverse=True)
        for daily in dailies:
            rows.append(TreeRow(3, daily.display_title, daily))
        nested = 4 if dailies else 3
        for thread in threads:
            rows.append(TreeRow(nested, thread.display_title, thread))
    return rows


def tree_text(rows: list[TreeRow]) -> str:
    """Árvore em texto simples (sem terminal interativo)."""
    lines: list[str] = []
    for row in rows:
        indent = "  " * row.depth
        if row.record is None:
            lines.append(f"{indent}{row.label}")
        else:
            glyph = "●" if row.record.kind == "daily" else "›"
            lines.append(f"{indent}{glyph} {row.label}  ({_detail(row.record)})")
    return "\n".join(lines)


class ResumePicker:
    """Seletor: busca por digitação, setas entre sessões, Enter retoma, Esc cancela."""

    def __init__(self, nav: SessionNavigator, query: str = "", current: str = "") -> None:
        self.nav = nav
        self.query = query
        self.current = current
        self.selected = 0
        self.chosen: str | None = None
        self.records: list[SessionRecord] = []
        self.rows: list[TreeRow] = []
        self.refresh()

    def refresh(self) -> None:
        self.records = self.nav.index.search(self.nav.parse(self.query), limit=300)
        self.rows = build_tree(self.records)
        self.selected = 0

    @property
    def selectable(self) -> list[int]:
        return [i for i, row in enumerate(self.rows) if row.record is not None]

    def selected_record(self) -> SessionRecord | None:
        selectable = self.selectable
        if not selectable:
            return None
        return self.rows[selectable[min(self.selected, len(selectable) - 1)]].record

    def on_key(self, key: str) -> bool:
        selectable = self.selectable
        if key == "escape":
            return True
        if key == "enter":
            record = self.selected_record()
            if record is not None:
                self.chosen = record.id
            return True
        if key == "up" and selectable:
            self.selected = (self.selected - 1) % len(selectable)
        elif key == "down" and selectable:
            self.selected = (self.selected + 1) % len(selectable)
        elif key == "backspace":
            self.query = self.query[:-1]
            self.refresh()
        elif len(key) == 1 and key.isprintable():
            self.query += key
            self.refresh()
        return False

    def render(self) -> RenderableType:
        rows = self.rows
        selectable = self.selectable
        focus = selectable[min(self.selected, len(selectable) - 1)] if selectable else -1
        height = max(8, shutil.get_terminal_size((100, 30)).lines - 12)
        start = max(0, min(focus - height // 2, len(rows) - height))
        lines: list[Text] = []
        search = Text("  Buscar: ", style="text_dim")
        search.append(self.query or "", style="text_primary")
        description = self.nav.parse(self.query).describe() if self.query else ""
        if description:
            search.append(f"   {description}", style="text_dim")
        lines.extend([search, Text("")])
        for index in range(start, min(len(rows), start + height)):
            row = rows[index]
            indent = "  " * row.depth
            if row.record is None:
                lines.append(Text(f"  {indent}{row.label}", style="text_dim" if row.depth == 2 else "text_primary"))
                continue
            active = index == focus
            marker = "❯ " if active else "  "
            glyph = "●" if row.record.kind == "daily" else "›"
            if row.record.id == self.current:
                glyph = "✔"
            line = Text(f"{marker}{indent}", style="accent_cyan" if active else "text_primary")
            line.append(f"{glyph} ", style="accent_cyan" if row.record.kind == "daily" else "text_dim")
            line.append(row.label, style="accent_cyan" if active else "text_primary")
            line.append(f"  {_detail(row.record)}", style="text_dim")
            lines.append(line)
        if not selectable:
            lines.append(Text("  Nenhuma sessão casa com a busca.", style="text_dim"))
        count = f"{len(self.records)} sessão(ões)"
        hint = Text(f"   {count}", style="text_dim")
        for key, label in (("[Enter]", " Retomar"), ("[Esc]", " Cancelar")):
            hint.append(" │ ", style="border_subtle")
            hint.append(key, style="accent_cyan")
            hint.append(label, style="text_dim")
        hint.append(" │ ", style="border_subtle")
        hint.append("hoje ontem semana nov 2026 daily thread @.", style="text_dim")
        return Group(orion_panel(Group(*lines), plain_title("Retomar sessão")), hint)


class ResumeCommand(BaseSlashCommand):
    name = "/resume"
    description = "Busca e retoma sessões por nome ou data (hoje, ontem, nov, @.)"
    usage = "/resume [id | filtro]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        session = context.session
        nav = session.nav
        query = args.strip()
        filtered = nav is not None and bool(query) and self._is_filter(nav, query)
        if query and not filtered:
            try:
                return CommandResult(success=True, output_message=session.resume(query))
            except SessionNotFoundError as exc:
                if nav is None:
                    return CommandResult(success=False, output_message=str(exc))
        if nav is None:
            return self._legacy_listing(context)
        picker = ResumePicker(nav, query, current=session.session_id)
        if active_host() is None and not is_interactive():
            if not picker.records:
                what = f" com '{query}'" if query else ""
                return CommandResult(success=False, output_message=f"Nenhuma sessão casa{what}.")
            return CommandResult(
                success=True,
                output_message="Sessões (use /resume <id>):\n" + tree_text(picker.rows),
                data=picker.records,
            )
        await run_modal(picker, context.console)
        if picker.chosen is None:
            return CommandResult(success=True)
        if picker.chosen == session.session_id:
            return CommandResult(success=True, output_message="Esta já é a sessão ativa.")
        try:
            return CommandResult(success=True, output_message=session.resume(picker.chosen))
        except SessionNotFoundError as exc:
            return CommandResult(success=False, output_message=str(exc))

    @staticmethod
    def _is_filter(nav: SessionNavigator, text: str) -> bool:
        parsed = nav.parse(text)
        return parsed.has_dates or bool(parsed.kind or parsed.workspace or parsed.workspace_name) or " " in text

    @staticmethod
    def _legacy_listing(context: CommandContext) -> CommandResult:
        sessions = context.session.list_sessions()
        if not sessions:
            return CommandResult(success=True, output_message="Nenhuma sessão anterior neste workspace.")
        lines = [
            f"{m.session_id[:8]}  {m.updated_at[:16].replace('T', ' ')}  {m.turns:>3} pedido(s)  {m.preview}"
            for m in sessions[:15]
        ]
        return CommandResult(
            success=True, output_message="Sessões (use /resume <id>):\n" + "\n".join(lines), data=sessions
        )


class RenameCommand(BaseSlashCommand):
    name = "/rename"
    description = "Dá título à sessão atual (o automático nunca o sobrescreve)"
    usage = "/rename <título>"
    requires_args = True

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        try:
            return CommandResult(success=True, output_message=context.session.rename_session(args))
        except ValueError as exc:
            return CommandResult(success=False, output_message=str(exc))
