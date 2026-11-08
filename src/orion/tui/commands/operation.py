"""Comandos de operação e governança."""

from __future__ import annotations

import os
import platform
import shutil
from typing import Any

from rich.table import Table
from rich.text import Text

from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult
from orion.tui.diff_viewer import DiffViewer
from orion.tui.modal import ConfigPanel, ConfigSetting, ModelPicker, run_modal
from orion.tui.panels import brand_title, orion_panel, render_cost


class DiffCommand(BaseSlashCommand):
    name = "/diff"
    description = "Painel com todas as modificações da sessão"
    usage = "/diff"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        diffs = context.session.tracker.session_diffs()
        if not diffs:
            return CommandResult(success=True, output_message="Nenhuma modificação nesta sessão.")
        viewer = DiffViewer()
        for diff in diffs:
            context.console.print(viewer.render(diff))
        return CommandResult(success=True, data=diffs)


class UndoCommand(BaseSlashCommand):
    name = "/undo"
    description = "Desfaz atomicamente a última mutação de arquivo da sessão"
    usage = "/undo"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        change = context.session.tracker.undo()
        if change is None:
            return CommandResult(success=True, output_message="Nada para desfazer.")
        path = change.path
        if path.is_relative_to(context.session.workspace):
            path = path.relative_to(context.session.workspace)
        return CommandResult(success=True, output_message=f"Desfeito: {path}")


class RunCommand(BaseSlashCommand):
    name = "/run"
    description = "Executa um comando no SO sob o crivo do PEP"
    usage = "/run <comando>"
    requires_args = True

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        ok = await context.session.run_tool("run_command", {"command": args})
        return CommandResult(success=ok)


def _anthropic_status(home: Any) -> Any:
    from orion.gateway.credentials import inspect_anthropic_key

    return inspect_anthropic_key(home)


class DoctorCommand(BaseSlashCommand):
    name = "/doctor"
    description = "Diagnóstico do ambiente: Python, hardware, Ollama e chaves"
    usage = "/doctor"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        session = context.session
        checks: list[tuple[str, bool, str]] = [
            ("Python", True, platform.python_version()),
            ("Git", shutil.which("git") is not None, shutil.which("git") or "não encontrado"),
            ("ANTHROPIC_API_KEY", _anthropic_status(session.home).ok, _anthropic_status(session.home).detail),
            (
                "OPENROUTER_API_KEY",
                bool(os.environ.get("OPENROUTER_API_KEY")),
                "configurada" if os.environ.get("OPENROUTER_API_KEY") else "ausente",
            ),
        ]
        try:
            from orion.gateway.providers.local_ollama import LocalOllamaProvider

            ollama = await LocalOllamaProvider().is_available()
        except Exception:
            ollama = False
        checks.append(("Ollama", ollama, "disponível" if ollama else "indisponível"))
        try:
            from orion.runtime.environment import EnvironmentMonitor

            snap = EnvironmentMonitor().snapshot()
            checks.append(("RAM livre", snap.headroom_safe, f"{snap.ram_free_gb:.1f} GB"))
        except Exception:
            checks.append(("RAM livre", False, "indisponível"))
        checks.append(("Memória (fatos)", session.facts is not None, str(session.home / "facts.db")))

        table = Table.grid(padding=(0, 2))
        table.add_column(no_wrap=True)
        table.add_column(no_wrap=True)
        table.add_column()
        for name, ok, detail in checks:
            table.add_row(
                Text("✔" if ok else "✖", style="status_ok" if ok else "diff_del"),
                Text(name, style="text_primary"),
                Text(detail, style="text_dim"),
            )
        context.console.print(orion_panel(table, brand_title("Diagnóstico do Ambiente")))
        return CommandResult(success=all(ok for _, ok, _ in checks), data=checks)


class CostCommand(BaseSlashCommand):
    name = "/cost"
    description = "Livro-razão da sessão em USD e BRL"
    usage = "/cost"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        session = context.session
        context.console.print(
            render_cost(
                session.tokens_in,
                session.tokens_out,
                session.tokens_cached,
                session.cost_in,
                session.cost_out,
                session.cost_total,
                session.status_bar.format_cost_brl(),
            )
        )
        return CommandResult(success=True)


class ModelCommand(BaseSlashCommand):
    name = "/model"
    description = "Seletor interativo de modelos de IA"
    usage = "/model [id]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        session = context.session
        if args:
            if args == "auto":
                session.set_model(None)
            elif args in {m.id for m in session.available_models()}:
                session.set_model(args)
            else:
                return CommandResult(success=False, output_message=f"Modelo indisponível: {args}")
            session.save_settings()
            return CommandResult(success=True, output_message=f"Modelo: {args}")

        picker = ModelPicker(session.available_models(), session.status_bar.model_name)
        await run_modal(picker, context.console)
        if picker.chosen is None:
            return CommandResult(success=True)
        session.set_model(picker.chosen)
        session.save_settings()
        return CommandResult(success=True, output_message=f"Modelo: {picker.chosen}")


class ConfigCommand(BaseSlashCommand):
    name = "/config"
    description = "Painel interativo de modelo, raciocínio, PEP e custos"
    usage = "/config"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        from orion.tui.session import MODE_CYCLE, AgentMode
        from orion.tui.status_bar import ReasoningEffort

        session = context.session
        bar = session.status_bar

        def set_effort(value: str) -> None:
            bar.reasoning_effort = ReasoningEffort(value)

        def set_routing(value: str) -> None:
            session.set_model(None if value == "auto" else bar.model_name)

        models = [m.id for m in session.available_models()]
        panel = ConfigPanel(
            {
                "Modelo & IA": [
                    ConfigSetting("Modelo Ativo:", lambda: bar.model_name, models, session.set_model),
                    ConfigSetting(
                        "Roteamento:",
                        lambda: "fixo" if session.selected_model else "auto",
                        ["auto", "fixo"],
                        set_routing,
                    ),
                ],
                "Raciocínio & Thinking": [
                    ConfigSetting(
                        "Esforço:",
                        lambda: bar.reasoning_effort.value,
                        [e.value for e in ReasoningEffort],
                        set_effort,
                    ),
                ],
                "Governança PEP": [
                    ConfigSetting(
                        "Modo do Agente:",
                        lambda: session.mode.value,
                        [m.value for m in MODE_CYCLE],
                        lambda value: session.set_mode(AgentMode(value)),
                    ),
                    ConfigSetting("Nível PEP:", lambda: bar.pep_level),
                ],
                "Custos & Orçamento": [
                    ConfigSetting(
                        "Teto Diário (USD):",
                        lambda: f"{session.budget.daily_budget_usd:.2f}",
                        ["1.00", "2.00", "5.00", "10.00", "20.00"],
                        lambda value: session.budget.update_budget(float(value)),
                    ),
                    ConfigSetting("Câmbio USD/BRL:", lambda: f"{bar.usd_to_brl_rate:.2f}"),
                ],
            }
        )
        await run_modal(panel, context.console)
        session.save_settings()
        return CommandResult(success=True)


class VoiceCommand(BaseSlashCommand):
    name = "/voice"
    description = "Controla o daemon de voz (previsto para a v0.5.0)"
    usage = "/voice"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        return CommandResult(success=True, output_message="O daemon de voz chega na v0.5.0.")


class ClearCommand(BaseSlashCommand):
    name = "/clear"
    description = "Limpa a tela preservando contexto e memórias"
    usage = "/clear"
    aliases = ("clear", "cls")

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        context.clear_screen()
        return CommandResult(success=True)


class HelpCommand(BaseSlashCommand):
    name = "/help"
    description = "Catálogo de comandos e atalhos de teclado"
    usage = "/help"
    aliases = ("help",)

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        from orion.tui.completer import OFFICIAL_SLASH_COMMANDS

        table = Table.grid(padding=(0, 2))
        table.add_column(no_wrap=True)
        table.add_column(no_wrap=True)
        table.add_column()
        dynamic = getattr(context.session, "dynamic_slash_infos", None)
        extra = dynamic() if callable(dynamic) else []
        for command in [*OFFICIAL_SLASH_COMMANDS, *extra]:
            table.add_row(
                Text(command.name, style="accent_cyan"),
                Text(command.category, style="text_dim"),
                Text(command.description, style="text_primary"),
            )
        keys = Text(
            "\nShift+Tab modo · Alt+T raciocínio · Alt+O fast · Alt+R expandir raciocínio · "
            "Alt+E expandir saída · Alt+Enter nova linha · Ctrl+C cancelar",
            style="text_dim",
        )
        context.console.print(orion_panel(table, brand_title("Catálogo de Slash Commands")))
        context.console.print(keys)
        return CommandResult(success=True)
