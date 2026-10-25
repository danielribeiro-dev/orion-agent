"""
O.R.I.O.N — CLI Entry Point
Command-line interface using Typer + Rich with The Hunter Crest ASCII banner.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.text import Text
from rich.rule import Rule

from orion import __version__
from orion.config import OrionConfig

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

console = Console()
err_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

# The Hunter Crest — Opção C (Recomendada), conforme ASCII_ART_IDENTITY.md
_HUNTER_CREST = """\

             ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗
            ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║
            ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║
            ██║   ██║██╔══██╗██║██║   ██║██║╚██╗██║
            ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║
            ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝

            [ PERSONAL OPERATING INTELLIGENCE ]\
"""

_STATUS_LINE = (
    f"[dim]v{__version__}[/dim]  ·  "
    "[dim]Modo:[/dim] [yellow]Supervisionado[/yellow]  ·  "
    "[dim]Autonomia:[/dim] [cyan]AUTO[/cyan]  ·  "
    "[dim]PEP:[/dim] [green]Ativo[/green]"
)

_HINT = "[dim]Dica: Digite [bold white]/help[/bold white] para ver os comandos disponíveis. Use [bold white]Ctrl+C[/bold white] para sair.[/dim]"


def print_banner() -> None:
    """Render the full ORION boot banner to the terminal."""
    console.print()

    # ASCII art — cyan cósmico
    art = Text(_HUNTER_CREST, style="bold cyan")
    console.print(art)

    console.print()
    console.print(Rule(style="dim blue"))
    console.print(_STATUS_LINE, justify="center")
    console.print(Rule(style="dim blue"))
    console.print(_HINT, justify="center")
    console.print()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
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
        console.print(
            f"[bold cyan]ORION[/bold cyan] [dim]v{__version__}[/dim]"
        )
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        print_banner()
        console.print(
            "[dim]Nenhum subcomando fornecido. Use [bold white]orion --help[/bold white] para ver as opções.[/dim]\n"
        )


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

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def run() -> None:
    """Programmatic entrypoint (used by tests and direct invocation)."""
    app()


if __name__ == "__main__":
    run()
