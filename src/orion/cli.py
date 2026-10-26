"""
O.R.I.O.N — CLI Entry Point
Command-line interface using Typer + Rich with The Hunter Crest ASCII banner.
"""

from __future__ import annotations

import typer
from rich.console import Console

from orion import __version__
from orion.config import OrionConfig
from orion.tui.banner import BannerRenderer
from orion.tui.console import get_console
from orion.tui.status_bar import SessionStatusBar

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


def print_banner() -> None:
    """Render the full ORION boot banner to the terminal."""
    renderer = BannerRenderer()
    console.print()
    console.print(renderer.render(terminal_width=console.width))


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
        print_banner()
        status_bar = SessionStatusBar.from_environment()
        console.print(status_bar.render_bottom_bar(width=console.width))
        console.print()


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
            "[green]✓ Seguro (>= 1.5GB)[/green]"
            if telemetry.headroom_safe
            else "[red]⚠ Bloqueado (< 1.5GB)[/red]"
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
