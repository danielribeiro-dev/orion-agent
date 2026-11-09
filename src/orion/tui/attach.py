"""
O.R.I.O.N TUI — ``orion-agent attach`` (v0.5.0 Sprint 7, ADR-032).

Anexa o terminal ao daemon: mostra estado e Inbox, recebe o stream de eventos e envia prompts à
sessão do daemon. A saída do turno chega como eventos de sink e é reaplicada num ``RichSink``
local, então o que se vê é a mesma renderização da TUI. Sair (``/detach``, Ctrl+D) não derruba
nada: o daemon continua; se ele reiniciar, o stream reconecta sozinho.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from rich.console import Console

from orion.daemon import ipc
from orion.daemon.client import DaemonUnavailable, call_once, follow
from orion.daemon.control import format_status
from orion.tui.sink import RichSink, SessionSink, apply_sink_event

ATTACH_HELP = "/inbox · /approve <id> · /deny <id> · /status · /detach  (texto livre vai para a sessão do daemon)"
PROMPT_TIMEOUT_S = 1800.0

ReadLine = Callable[[], Awaitable[str]]


class EventPrinter:
    """Traduz eventos do daemon em linhas no terminal (glifos permitidos, sem emojis)."""

    def __init__(self, console: Console, sink: SessionSink) -> None:
        self.console = console
        self.sink = sink

    def __call__(self, payload: dict[str, Any]) -> None:
        if apply_sink_event(self.sink, payload):
            return
        kind = str(payload.get("kind", ""))
        if kind == "notify":
            message = payload.get("message") or {}
            line = f"● {message.get('title', '')}"
            body = str(message.get("body") or "").strip()
            self.console.print(line, style="accent_cyan", highlight=False)
            if body:
                self.console.print(f"  {body[:400]}", style="text_dim", highlight=False)
            if message.get("kind") == "approval":
                self.console.print(
                    f"  [PEP] /approve {message.get('id')} · /deny {message.get('id')}", style="pep_warn"
                )
        elif kind == "agent_event":
            event = payload.get("event") or {}
            self.console.print(f"· {event.get('kind')} · {event.get('agent_id')}", style="text_dim")
        elif kind == "job.finished":
            self.console.print(
                f"· job {payload.get('job_id')} · {payload.get('status')} {payload.get('reason') or ''}".rstrip(),
                style="text_dim",
            )


async def print_status(path: Path, console: Console) -> dict[str, Any]:
    status = await call_once(path, "status", timeout_s=5.0)
    pseudo = {"enabled": True, "autostart": "?", "service": {}, "daemon": status}
    for line in format_status(pseudo)[2:]:
        console.print(line, style="text_dim")
    return dict(status)


async def print_inbox(path: Path, console: Console) -> int:
    items = await call_once(path, "inbox.list", {"status": "pending"}, timeout_s=5.0)
    if not items:
        console.print("Inbox vazia.", style="text_dim")
        return 0
    for item in items:
        console.print(f"● {item['id']} · {item['kind']} · {item['title']}", style="text_dim", highlight=False)
    return len(items)


async def handle_line(line: str, path: Path, console: Console) -> bool:
    """Processa uma linha do Senhor. ``False`` encerra o attach (o daemon segue vivo)."""
    text = line.strip()
    if not text:
        return True
    if text in ("/detach", "/exit", "/quit"):
        return False
    try:
        if text == "/help":
            console.print(ATTACH_HELP, style="text_dim")
        elif text == "/status":
            await print_status(path, console)
        elif text == "/inbox":
            await print_inbox(path, console)
        elif text.split()[0] in ("/approve", "/deny"):
            parts = text.split()
            if len(parts) != 2:
                console.print(f"Uso: {parts[0]} <id>", style="pep_warn")
                return True
            action = "approve" if parts[0] == "/approve" else "deny"
            outcome = await call_once(path, "inbox.resolve", {"id": parts[1], "action": action})
            ok = bool(outcome and outcome.get("resolved"))
            console.print(f"✔ {parts[1]}: {action}" if ok else f"! {parts[1]} não está pendente", style="text_dim")
        elif text.startswith("/"):
            console.print(f"! comando do attach desconhecido. {ATTACH_HELP}", style="pep_warn")
        else:
            await call_once(path, "prompt", {"text": text}, timeout_s=PROMPT_TIMEOUT_S)
    except ipc.IpcError as exc:
        console.print(f"✖ {exc.message}", style="pep_warn")
    except (DaemonUnavailable, TimeoutError):
        console.print("! daemon indisponível; tentando reconectar...", style="pep_warn")
    return True


async def _prompt_toolkit_reader() -> ReadLine:
    from prompt_toolkit import PromptSession

    prompt: PromptSession[str] = PromptSession()

    async def read() -> str:
        return await prompt.prompt_async("❯ ")

    return read


async def run_attach(
    home: Path,
    console: Console,
    *,
    socket: Path | None = None,
    read_line: ReadLine | None = None,
) -> int:
    path = socket or ipc.socket_path(home)
    try:
        await print_status(path, console)
    except (DaemonUnavailable, ipc.IpcError, TimeoutError):
        console.print("✖ daemon não está em execução. Use /daemon start ou orion-agent daemon start.", style="pep_warn")
        return 1
    await print_inbox(path, console)
    console.print(ATTACH_HELP, style="text_dim")
    with contextlib.suppress(DaemonUnavailable, ipc.IpcError, TimeoutError):
        await call_once(path, "activity", timeout_s=5.0)

    printer = EventPrinter(console, RichSink(console))
    stop = asyncio.Event()

    def on_state(state: str) -> None:
        if state == "disconnected":
            console.print("! conexão com o daemon perdida; reconectando...", style="pep_warn")

    follower = asyncio.create_task(follow(path, printer, client_name="attach", on_state=on_state, stop=stop))
    reader = read_line or await _prompt_toolkit_reader()
    patch: Any = contextlib.nullcontext()
    if read_line is None:
        from prompt_toolkit.patch_stdout import patch_stdout

        patch = patch_stdout()
    try:
        with patch:
            while True:
                try:
                    line = await reader()
                except (EOFError, KeyboardInterrupt):
                    break
                if not await handle_line(line, path, console):
                    break
    finally:
        stop.set()
        follower.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await follower
    console.print("Desanexado; o daemon continua ativo.", style="text_dim")
    return 0
