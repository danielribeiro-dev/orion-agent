"""Comandos de operação e governança."""

from __future__ import annotations

import platform
import shutil
import sys
from typing import Any

from rich.table import Table
from rich.text import Text

from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult
from orion.tui.diff_viewer import DiffViewer
from orion.tui.menu import CATEGORY_LABELS
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
    description = "Desfaz a última mutação (edição ou lixo do ORION); list mostra os snapshots"
    usage = "/undo [list | <id>]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        session = context.session
        arg = args.strip()
        if arg in ("list", "ls", "lista"):
            return self._list(context)
        if arg:
            summary = await session._undo_snapshot(arg)
            if summary is None:
                return CommandResult(success=False, output_message=f"Snapshot '{arg}' não encontrado. Veja /undo list.")
            return CommandResult(success=True, output_message=summary)
        summary = await session.undo_latest()
        return CommandResult(success=True, output_message=summary or "Nada para desfazer.")

    @staticmethod
    def _list(context: CommandContext) -> CommandResult:
        from datetime import datetime

        snaps = context.session.reversibility.list()
        if not snaps:
            return CommandResult(success=True, output_message="O lixo do ORION está vazio.")
        table = Table(box=None, show_header=True, header_style="text_dim", pad_edge=False)
        for column in ("id", "quando", "itens", "comando", ""):
            table.add_column(column, style="text_primary" if column == "id" else "text_dim", overflow="fold")
        for snap in snaps[:20]:
            when = datetime.fromtimestamp(snap.created_at).strftime("%d/%m %H:%M")
            table.add_row(snap.id, when, snap.summary(), snap.command[:60], "✔ restaurado" if snap.restored else "")
        context.console.print(table)
        return CommandResult(success=True, data=snaps)


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


def _color_label() -> str:
    from orion.tui.theme import color_depth

    return {
        "truecolor": "truecolor (paleta exata)",
        "256": "256 cores (tokens aproximados)",
        "none": "sem cor (NO_COLOR ou sem terminal)",
    }[color_depth(is_tty=sys.stdout.isatty())]


def _openrouter_status(home: Any) -> tuple[bool, str]:
    from orion.gateway.credentials import openrouter_key_status

    return openrouter_key_status(home)


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
            ("OPENROUTER_API_KEY", *_openrouter_status(session.home)),
            ("Cores", True, _color_label()),
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
        checks.extend(_freedom_checks(session.home))
        checks.extend(_governance_checks(session))
        from orion.install import diagnose

        checks.extend(diagnose())

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


def _governance_checks(session: Any) -> list[tuple[str, bool, str]]:
    """Modo, classificador e lixo do ORION (v0.5.3 Sprint 2, ADR-046/047)."""
    from orion.tui.session import MODE_ALIASES

    out: list[tuple[str, bool, str]] = []
    raw_mode = str(session.settings.effective.mode or "")
    if raw_mode in MODE_ALIASES:
        out.append(
            (
                "Modo",
                False,
                f"settings.json usa '{raw_mode}' (nome antigo); vale como '{MODE_ALIASES[raw_mode].value}'. "
                "Troque pelo nome novo: plan, ask, auto ou full.",
            )
        )
    else:
        out.append(("Modo", True, f"{session.mode.value} (faixas: livre, classificada, presença, nuclear)"))
    stage2 = "modelo FAST (cego a saídas de tool)" if session.online else "sem modelo: dúvidas vão ao Senhor"
    cap = session.budget.origin_budget_usd.get("classifier")
    out.append(("Classificador", True, f"regras + ledger + {stage2}" + (f" · teto US$ {cap:.2f}/dia".replace(".", ",") if cap else "")))
    try:
        snaps = session.reversibility.list()
        used = sum(s.bytes for s in snaps) / 1024**3
        out.append(("Lixo do ORION", True, f"{len(snaps)} snapshot(s) · {used:.2f} GiB de 10 GiB · 7 dias (/undo list)".replace(".", ",", 1)))
    except OSError as exc:
        out.append(("Lixo do ORION", False, f"indisponível: {exc}"))
    return out


def _freedom_checks(home: Any) -> list[tuple[str, bool, str]]:
    """sudo, presença, web e busca (v0.5.3 Sprint 1, ADR-048/049). Nada aqui lê segredos."""
    import os

    from orion.gateway.credentials import read_env_file
    from orion.governance.askpass import SUDO_KEYRING_MARKER
    from orion.runtime.tools.web_policy import legacy_allowlist_notice, load_blocklist

    out: list[tuple[str, bool, str]] = []
    sudo = shutil.which("sudo")
    out.append(
        (
            "sudo (askpass)",
            sudo is not None,
            "sudo -A pela sessão; o sudo guarda a autorização por terminal (timestamp_type), "
            "então sem chaveiro cada comando pede a senha" if sudo else "sudo não encontrado",
        )
    )
    keyring = (home / SUDO_KEYRING_MARKER).exists()
    out.append(
        (
            "Senha do sudo lembrada",
            True,
            "no chaveiro do sistema (orion setup sudo --forget desfaz)"
            if keyring
            else "não (opcional: orion setup sudo)",
        )
    )
    display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    polkit = shutil.which("pkexec") is not None and display
    try:
        import pam  # noqa: F401

        pam_ok = True
    except ImportError:
        pam_ok = False
    out.append(
        (
            "Presença nuclear",
            polkit or pam_ok,
            "polkit (diálogo do sistema)" if polkit else "PAM com senha mascarada" if pam_ok else "indisponível: nuclear será negado",
        )
    )
    blocked = load_blocklist(home)
    out.append(("Web", True, f"aberta · {len(blocked)} domínio(s) bloqueado(s) (/web list)"))
    notice = legacy_allowlist_notice(home)
    if notice:
        out.append(("Allowlist antiga", False, notice))
    providers = []
    if os.environ.get("BRAVE_API_KEY") or read_env_file(home).get("BRAVE_API_KEY"):
        providers.append("brave")
    try:
        import ddgs  # noqa: F401

        providers.append("ddgs")
    except ImportError:
        pass
    providers.append("duckduckgo")
    out.append(("Busca web", True, " › ".join(providers) + " (BRAVE_API_KEY no ~/.orion/.env melhora)"))
    return out


class WebCommand(BaseSlashCommand):
    name = "/web"
    description = "Web aberta: bloquear, desbloquear e listar domínios"
    usage = "/web list · /web block <domínio> · /web unblock <domínio>"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        from orion.runtime.tools.web_policy import load_blocklist, normalize_domain, save_blocklist

        home = context.session.home
        verb, _, rest = args.strip().partition(" ")
        verb = verb.lower() or "list"
        blocked = list(load_blocklist(home))
        if verb in ("block", "bloquear", "unblock", "desbloquear"):
            domain = normalize_domain(rest)
            if domain is None:
                context.console.print(Text(f"✖ domínio inválido: {rest.strip() or '(vazio)'}", style="diff_del"))
                return CommandResult(success=False, output_message="domínio inválido")
            if verb in ("block", "bloquear"):
                blocked = sorted({*blocked, domain})
                message = f"✔ {domain} bloqueado (vale na hora, inclusive subdomínios)"
            else:
                if domain not in blocked:
                    context.console.print(Text(f"● {domain} não estava bloqueado", style="text_dim"))
                    return CommandResult(success=True, output_message="sem mudança")
                blocked = [d for d in blocked if d != domain]
                message = f"✔ {domain} desbloqueado"
            save_blocklist(blocked, home)
            context.console.print(Text(message, style="status_ok"))
            return CommandResult(success=True, data=blocked)
        if verb not in ("list", "listar"):
            context.console.print(Text(f"uso: {self.usage}", style="text_dim"))
            return CommandResult(success=False, output_message="uso inválido")
        if not blocked:
            context.console.print(Text("● web aberta, nenhum domínio bloqueado · /web block <domínio>", style="text_dim"))
        else:
            for domain in blocked:
                context.console.print(Text(f"✖ {domain}", style="text_primary"))
        return CommandResult(success=True, data=blocked)


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
                agents_tokens=session.agent_usage.prompt_tokens + session.agent_usage.completion_tokens,
                agents_cost=session.agent_usage.cost_usd,
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
    description = "Controla a voz (prevista para a v0.6.0)"
    usage = "/voice"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        return CommandResult(success=True, output_message="A voz chega na v0.6.0 (Ambient Mode).")


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
                Text(CATEGORY_LABELS.get(command.category, command.category), style="text_dim"),
                Text(command.description, style="text_primary"),
            )
        keys = Text(
            "\nShift+Tab modo · Alt+T esforço · Alt+O rápido · Alt+R raciocínio · Alt+E saída · "
            "Ctrl+O transcrição · PgUp/PgDn rola · Alt+Enter nova linha · Esc interrompe",
            style="text_dim",
        )
        context.console.print(orion_panel(table, brand_title("Catálogo de Slash Commands")))
        context.console.print(keys)
        return CommandResult(success=True)


class TuiCommand(BaseSlashCommand):
    name = "/tui"
    description = "Modo da tela: cheia (padrão) ou clássico"
    usage = "/tui [fullscreen|classic]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        from orion.tui.screen.mode import save_preference

        session = context.session
        current = "fullscreen" if getattr(session, "tui", None) is not None else "classic"
        wanted = {"fullscreen": "fullscreen", "cheia": "fullscreen", "classic": "classic", "classico": "classic",
                  "clássico": "classic", "default": "classic"}.get(args.strip().lower())
        labels = {"fullscreen": "tela cheia", "classic": "clássico"}
        if not args.strip():
            return CommandResult(success=True, output_message=f"Modo atual: {labels[current]} · {self.usage}")
        if wanted is None:
            return CommandResult(success=False, output_message=f"Uso: {self.usage}")
        save_preference(session.home, wanted)  # type: ignore[arg-type]
        if wanted == current:
            return CommandResult(success=True, output_message=f"Já está no modo {labels[current]}.")
        relaunch = getattr(getattr(session, "tui", None), "request_relaunch", None)
        if callable(relaunch):
            relaunch()
            return CommandResult(success=True, output_message=f"Reabrindo no modo {labels[wanted]}…")
        return CommandResult(
            success=True,
            output_message=f"Preferência salva: {labels[wanted]}. Vale na próxima vez que o ORION abrir.",
        )
