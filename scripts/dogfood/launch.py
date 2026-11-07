"""ORION real (sessão, engine, tools, PEP, TUI) com o modelo trocado pela ponte. Roda dentro do pty."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", required=True)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--mcp", action="store_true")
    args = ap.parse_args()

    # Chave FALSA: só faz o roteador usar os tiers Anthropic (caminho nativo). Nunca é enviada.
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-bridge-dummy-never-sent"
    os.environ["ORION_MCP"] = "1" if args.mcp else "0"
    os.chdir(args.workspace)

    from bridge_provider import BridgeProvider

    from orion import cli
    from orion.tui.session import AgentSession
    from orion.tui.status_bar import SessionStatusBar

    home = Path(args.home)
    cli.configure_logging(home)
    provider = BridgeProvider(Path(args.bridge))
    status_bar = SessionStatusBar.from_environment()
    session = AgentSession(
        status_bar=status_bar,
        console=cli.console,
        workspace=Path(args.workspace),
        home=home,
        provider_factory=lambda spec: provider,
    )
    session.set_model(args.model)
    if args.mcp:
        session.start_mcp()
    if cli.console.is_terminal:
        cli.console.clear()
    lines = cli.print_banner(status_bar)
    prompt = cli.create_prompt(status_bar, session)
    prompt.dock_to_bottom(lines)
    cli.run_interactive_repl(prompt, session)


if __name__ == "__main__":
    main()
