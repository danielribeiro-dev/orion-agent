"""Roda dentro do pty: o mesmo caminho do ``orion-agent`` interativo, com o provider trocado.

Uso: ``python tests/lab/launcher.py --workspace W --home H --scripts S.json``.
A chave de API é falsa e nunca é enviada: só faz o roteador escolher os tiers Anthropic.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--scripts", required=True)
    parser.add_argument("--model", default="claude-sonnet-5-5")
    parser.add_argument("--fullscreen", action="store_true", help="tela cheia (ADR-043)")
    args = parser.parse_args()

    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-lab-dummy-never-sent"
    os.environ["ORION_MCP"] = "0"
    os.chdir(args.workspace)

    from orion import cli
    from orion.tui.session import AgentSession
    from orion.tui.status_bar import SessionStatusBar
    from tests.lab.scripted_provider import ScriptBook, ScriptedProvider

    home = Path(args.home)
    cli.configure_logging(home)
    provider = ScriptedProvider(ScriptBook.load(Path(args.scripts)))
    status_bar = SessionStatusBar.from_environment()
    if args.fullscreen:
        from orion.tui.screen.app import ScreenApp, build_parts

        parts = build_parts(status_bar)
        session = AgentSession(
            status_bar=status_bar,
            console=parts.console,
            workspace=Path(args.workspace),
            home=home,
            provider_factory=lambda spec: provider,
            sink=parts.renderer,
        )
        session.set_model(args.model)
        screen = ScreenApp(session, parts, status_bar, home=home)
        try:
            screen.run()
        finally:
            session.shutdown()
        cli.console.print(screen.summary())
        return
    session = AgentSession(
        status_bar=status_bar,
        console=cli.console,
        workspace=Path(args.workspace),
        home=home,
        provider_factory=lambda spec: provider,
    )
    session.set_model(args.model)
    if cli.console.is_terminal:
        cli.console.clear()
    cli.print_banner(status_bar)
    prompt = cli.create_prompt(status_bar, session)
    try:
        cli.run_interactive_repl(prompt, session)
    finally:
        session.shutdown()


if __name__ == "__main__":
    main()
