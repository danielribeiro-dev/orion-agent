"""
O.R.I.O.N — CLI Entry Point
Command-line interface using Typer + Rich with The Hunter Crest ASCII banner.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.text import Text

from orion import __version__
from orion.config import OrionConfig
from orion.tui.banner import BannerRenderer
from orion.tui.console import get_console
from orion.tui.keybindings import create_key_bindings
from orion.tui.prompt import InteractivePrompt
from orion.tui.status_bar import SessionStatusBar

if TYPE_CHECKING:
    from orion.tui.session import AgentSession

# ---------------------------------------------------------------------------
# App & Console
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="orion",
    help="O.R.I.O.N — Operational Reasoning & Intelligence Orchestration Network",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=False,
    invoke_without_command=True,
)

console = get_console()
err_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def print_banner(status_bar: SessionStatusBar | None = None) -> int:
    """Render the full ORION boot banner to the terminal and return line count."""
    renderer = BannerRenderer(status_bar=status_bar)
    console.print()
    rendered = renderer.render(terminal_width=console.width)
    console.print(rendered)
    try:
        panel_lines = len(
            list(console.render_lines(rendered, console.options.update_width(console.width)))
        )
        return panel_lines + 2
    except Exception:
        return 16


def _clear_screen(prompt: InteractivePrompt) -> None:
    """Redesenha o banner sem perder a sessão."""
    console.clear()
    prompt.dock_to_bottom(print_banner(prompt.status_bar))


def create_session(status_bar: SessionStatusBar) -> AgentSession:
    """Constrói a sessão do agente; importado aqui para manter o boot do CLI leve."""
    from orion.tui.session import AgentSession

    session = AgentSession(status_bar=status_bar, console=console)
    if os.environ.get("ORION_MCP", "1") != "0":
        session.start_mcp()
    return session


def create_prompt(status_bar: SessionStatusBar, session: AgentSession) -> InteractivePrompt:
    """Cria o prompt com os atalhos ligados à sessão."""
    bindings = create_key_bindings(
        on_cycle_mode=session.cycle_mode,
        on_cycle_effort=session.cycle_effort,
        on_toggle_fast=session.toggle_fast,
        on_expand_reasoning=session.renderer.expand_reasoning,
        on_expand_output=session.renderer.expand_output,
    )
    return InteractivePrompt(status_bar=status_bar, custom_key_bindings=bindings)


def run_interactive_repl(prompt: InteractivePrompt, session: AgentSession) -> None:
    """Loop interativo principal do terminal orion-agent."""
    from orion.tui.commands import CommandContext, CommandRegistry

    registry = CommandRegistry.discover()
    context = CommandContext(
        session=session,
        console=console,
        clear_screen=lambda: _clear_screen(prompt),
    )
    last_ctrl_c: float = 0.0

    while True:
        try:
            user_input = prompt.prompt(raise_on_interrupt=True)
            if not user_input or not user_input.strip():
                continue

            cleaned = user_input.strip()

            if cleaned in ("/exit", "/quit", "exit", "quit", ":q"):
                console.print("[text_dim]● Até logo, Senhor. Sessão finalizada.[/text_dim]\n")
                break

            is_command = cleaned.startswith("/") or registry.get(cleaned) is not None
            if is_command:
                result = asyncio.run(
                    prompt.run_turn(registry.dispatch(cleaned, context), session.session_id)
                )
                if result is not None and result.output_message:
                    style = "text_dim" if result.success else "diff_del"
                    console.print(Text(result.output_message, style=style))
            else:
                asyncio.run(prompt.run_turn(session.run_turn(cleaned), session.session_id))
            console.print()

        except EOFError:
            console.print("[text_dim]● Sessão finalizada.[/text_dim]\n")
            break
        except KeyboardInterrupt:
            now = time.monotonic()
            if now - last_ctrl_c < 2.0:
                console.print("\n[text_dim]● Até logo, Senhor. Sessão finalizada.[/text_dim]\n")
                break
            last_ctrl_c = now
            console.print("\n[text_dim]Pressione Ctrl+C novamente para sair (ou digite /exit)[/text_dim]\n")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def cli_root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show ORION version and exit.",
        is_eager=True,
    ),
) -> None:
    """O.R.I.O.N — Operational Reasoning & Intelligence Orchestration Network.

    Personal Operating Intelligence platform with Action-Observation Event Stream,
    5 Native Primitive Tools, deterministic PEP governance and structured Artifacts.
    """
    if version:
        console.print(f"[bold cyan]ORION[/bold cyan] [dim]v{__version__}[/dim]")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        status_bar = SessionStatusBar.from_environment()
        session = create_session(status_bar)
        banner_lines = print_banner(status_bar)
        prompt = create_prompt(status_bar, session)
        prompt.dock_to_bottom(banner_lines)
        run_interactive_repl(prompt, session)


@app.command(name="info")
def cmd_info() -> None:
    """Display current ORION configuration and runtime status."""
    config = OrionConfig.default()

    print_banner()

    from rich.table import Table

    table = Table(
        title="[bold cyan]Configuração Atual[/bold cyan]",
        border_style="dim blue",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Parâmetro", style="dim white", no_wrap=True)
    table.add_column("Valor", style="bright_white")

    table.add_row("Versão", f"v{__version__}")
    table.add_row("Modo de Roteamento", config.routing_mode.value)
    table.add_row("Nível de Autonomia", config.autonomy_level.value)
    table.add_row("Max Turns (Budget)", str(config.max_turns))
    table.add_row("Global Home", str(config.paths.global_home))
    table.add_row("Local Home", str(config.paths.local_home))
    table.add_row("Provedores Configurados", str(len(config.providers)))

    # Telemetria de Hardware & Ambiente (v0.2.0)
    try:
        from orion.runtime.environment import EnvironmentMonitor

        monitor = EnvironmentMonitor()
        telemetry = monitor.snapshot()
        headroom_icon = (
            "[green]✔ Seguro (>= 1.5GB)[/green]"
            if telemetry.headroom_safe
            else "[red]! Bloqueado (< 1.5GB)[/red]"
        )
        table.add_row(
            "RAM Livre / Total", f"{telemetry.ram_free_gb:.2f} GB / {telemetry.ram_total_gb:.2f} GB"
        )
        table.add_row("Carga de CPU (1m)", f"{telemetry.cpu_load_percent:.1f}%")
        table.add_row("Servidor de Display", telemetry.display_mode)
        table.add_row("Headroom Guard", headroom_icon)
    except Exception:
        pass

    # Identidade & Persona (v0.2.0)
    try:
        from orion.core.identity import IdentityManager

        identity = IdentityManager().get_identity()
        table.add_row("Origem Imutável", identity.immutable_origin)
        table.add_row("Persona Ativa", f"[bold cyan]{identity.persona_name}[/bold cyan]")
    except Exception:
        pass

    # Habilidades Descobertas (v0.2.0)
    try:
        from orion.skills.loader import SkillsLoader

        skills = SkillsLoader().discover()
        table.add_row(
            "Agent Skills Disponíveis",
            f"{len(skills)} descobertas ({', '.join(sorted(skills.keys()))})",
        )
    except Exception:
        pass

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entrypoint for orion-agent executable."""
    app()


def run() -> None:
    """Programmatic entrypoint (used by tests and direct invocation)."""
    app()


if __name__ == "__main__":
    main()
