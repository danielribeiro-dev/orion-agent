"""Aplicação em tela cheia dirigida por teclado simulado (ADR-043, v0.5.2 Sprint 2)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.text import Text

from orion.tui import modal
from orion.tui.commands.base import CommandContext, CommandResult
from orion.tui.screen import host as host_registry
from orion.tui.screen.app import ScreenApp, build_parts, user_cell
from orion.tui.screen.transcript import plain
from orion.tui.status_bar import SessionStatusBar


class FakeSession:
    def __init__(self, renderer: Any, home: Path) -> None:
        self.renderer = renderer
        self.home = home
        self.workspace = home
        self.session_id = "abcdef0123456789"
        self.turns: list[str] = []
        self.release = asyncio.Event()
        self.block = False
        self.notes: list[str] = []
        self.mode_cycles = 0

    def dynamic_slash_infos(self) -> list[Any]:
        return []

    def mcp_resource_choices(self) -> list[tuple[str, str]]:
        return []

    def dynamic_commands(self) -> list[Any]:
        return []

    def cycle_mode(self) -> None:
        self.mode_cycles += 1

    def cycle_effort(self) -> None:
        return None

    def toggle_fast(self) -> None:
        return None

    def pop_notifications(self) -> list[str]:
        out, self.notes = self.notes, []
        return out

    def format_notification(self, event: str) -> str:
        return event

    async def run_turn(self, text: str) -> str:
        self.turns.append(text)
        self.renderer.begin_thinking()
        self.renderer.add_reasoning("pensando no pedido do Senhor com calma, " * 3)
        self.renderer.add_text(f"resposta para {text}")
        if self.block:
            await self.release.wait()
        self.renderer.end_message()
        self.renderer.close()
        return "ok"


class Echo:  # não herda de BaseSlashCommand: não entra no registro global
    name = "/eco"
    description = "teste"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        context.console.print(f"eco {args}")
        return CommandResult(success=True, output_message="feito")


class Boom:
    name = "/boom"
    description = "teste"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        raise RuntimeError("explodiu")


class Registry:
    def __init__(self) -> None:
        self.commands = {c.name: c for c in (Echo(), Boom())}

    def set_dynamic(self, commands: Any) -> None:
        return None

    def get(self, name: str) -> Any:
        return self.commands.get(name)

    async def dispatch(self, line: str, context: CommandContext) -> CommandResult:
        name, _, args = line.partition(" ")
        command = self.commands.get(name)
        if command is None:
            return CommandResult(success=False, output_message=f"desconhecido: {name}")
        return await command.execute(args, context)


@asynccontextmanager
async def running(tmp_path: Path, **kwargs: Any) -> AsyncIterator[tuple[ScreenApp, FakeSession, Callable[[str], None]]]:
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        status = SessionStatusBar()
        parts = build_parts(status)
        session = FakeSession(parts.renderer, tmp_path)
        screen = ScreenApp(session, parts, status, registry=Registry(), home=tmp_path, mouse=False, **kwargs)
        task = asyncio.ensure_future(screen.run_async())
        await asyncio.sleep(0.15)
        try:
            yield screen, session, pipe.send_text
        finally:
            screen.exit()
            await asyncio.wait_for(task, 5)


async def settle(seconds: float = 0.2) -> None:
    await asyncio.sleep(seconds)


def text_of(screen: ScreenApp) -> str:
    lines, _, _ = screen.transcript.window(80, 500, 0)
    return plain(lines)


@pytest.mark.asyncio
async def test_submit_runs_turn_and_records_user_cell(tmp_path: Path) -> None:
    async with running(tmp_path) as (screen, session, send):
        assert host_registry.active_host() is screen
        send("olá ORION\r")
        await settle(0.4)
        assert session.turns == ["olá ORION"]
        body = text_of(screen)
        assert "❯ olá ORION" in body and "resposta para olá ORION" in body and "▸ Raciocínio" in body
        assert screen.turn is None and screen.turns == 1
    assert host_registry.active_host() is None


@pytest.mark.asyncio
async def test_enter_during_turn_queues_and_runs_next(tmp_path: Path) -> None:
    async with running(tmp_path) as (screen, session, send):
        session.block = True
        send("primeiro\r")
        await settle()
        assert screen.turn is not None
        assert "Enter enfileira" in screen._placeholder()
        send("segundo\r")
        await settle()
        assert screen.queue == ["segundo"]
        assert "na fila: segundo" in "".join(t for _, t in screen._queue_fragments())
        session.block = False
        session.release.set()
        await settle(0.5)
        assert session.turns == ["primeiro", "segundo"] and screen.queue == []


@pytest.mark.asyncio
async def test_up_takes_queue_back_for_editing(tmp_path: Path) -> None:
    async with running(tmp_path) as (screen, session, send):
        session.block = True
        send("primeiro\r")
        await settle()
        send("a\rb\r")
        await settle()
        assert screen.queue == ["a", "b"]
        send("\x1b[A")  # seta para cima
        await settle()
        assert screen.queue == [] and screen.buffer.text == "a\nb"
        session.release.set()


@pytest.mark.asyncio
async def test_escape_interrupts_turn_and_keeps_text(tmp_path: Path) -> None:
    async with running(tmp_path) as (screen, session, send):
        session.block = True
        send("longo\r")
        await settle()
        send("\x1b")
        await settle(0.6)  # o Esc espera 0,25 s por uma tecla Alt
        assert screen.turn is None
        body = text_of(screen)
        assert "Turno interrompido" in body and "resposta para longo" in body


@pytest.mark.asyncio
async def test_ctrl_c_clears_then_exits_twice(tmp_path: Path) -> None:
    async with running(tmp_path) as (screen, session, send):
        send("rascunho")
        await settle()
        send("\x03")
        await settle()
        assert screen.buffer.text == "" and not screen.exited
        send("\x03")
        await settle()
        assert screen.flash is not None and "de novo" in screen.flash[0]
        assert screen._activity_lines()
        send("\x03")
        await settle()
        assert screen.exited


@pytest.mark.asyncio
async def test_commands_errors_and_exit_word(tmp_path: Path) -> None:
    async with running(tmp_path) as (screen, session, send):
        send("/eco oi\r")
        await settle()
        send("/boom\r")
        await settle()
        send("/nada\r")
        await settle()
        body = text_of(screen)
        assert "eco oi" in body and "feito" in body and "✖ explodiu" in body and "desconhecido" in body
        screen.clear()
        assert "eco oi" not in text_of(screen)
        send("/exit\r")
        await settle()
        assert screen.exited


@pytest.mark.asyncio
async def test_modal_host_and_text_answers(tmp_path: Path) -> None:
    class Picker:
        def __init__(self) -> None:
            self.keys: list[str] = []

        def render(self) -> Text:
            return Text("escolha: y/n")

        def on_key(self, key: str) -> bool:
            self.keys.append(key)
            return key in ("y", "n", "escape")

    async with running(tmp_path) as (screen, session, send):
        picker = Picker()
        waiting = asyncio.ensure_future(modal.run_modal(picker, screen.console, keep_on_screen=True))
        await settle()
        assert screen.modal is picker and screen.buffer.read_only()
        assert "escolha" in "".join(t for _, t in screen._modal_fragments())
        send("xy")
        await asyncio.wait_for(waiting, 2)
        assert picker.keys == ["x", "y"] and screen.modal is None
        assert "escolha: y/n" in text_of(screen)

        answer = asyncio.ensure_future(modal._ask_text("qual o nome?", "ORI"))
        await settle()
        assert screen._placeholder() == "qual o nome?" and screen._prompt_symbol()[0][1] == "› "
        send("ON\r")
        assert await asyncio.wait_for(answer, 2) == "ORION"

        skipped = asyncio.ensure_future(modal._ask_text("pergunta"))
        await settle()
        send("\x1b")
        assert await asyncio.wait_for(skipped, 2) == ""


@pytest.mark.asyncio
async def test_scroll_indicator_and_notifications(tmp_path: Path) -> None:
    async with running(tmp_path) as (screen, session, send):
        for n in range(80):
            screen.transcript.add_renderables("print", Text(f"linha {n}"))
        screen.visible_lines(80, 10)
        screen.scroll(5)
        screen.visible_lines(80, 10)
        assert screen.offset == 5
        screen.transcript.add_renderables("print", Text("nova"))
        screen.visible_lines(80, 10)
        assert screen.offset == 6 and screen.unseen == 1
        hint = plain(screen._activity_lines())
        assert "1 linha nova" in hint and "Ctrl+End" in hint
        screen.scroll(-100)
        screen.visible_lines(80, 10)
        assert screen.offset == 0 and screen.unseen == 0
        session.notes.append("task pronta")
        await settle(0.7)
        assert "● task pronta" in text_of(screen)
        screen.request_relaunch()
        assert screen.relaunch
        assert "retome com orion --resume abcdef01" in screen.summary().plain


def test_user_cell_has_no_rules() -> None:
    cell = user_cell("pedido")
    rendered = plain(cell.lines(40))
    assert "❯ pedido" in rendered and "─" not in rendered


@pytest.mark.asyncio
async def test_tui_command(tmp_path: Path) -> None:
    from orion.tui.commands.operation import TuiCommand
    from orion.tui.screen.mode import read_state

    class Ctx:
        def __init__(self, session: Any) -> None:
            self.session = session

    class Sess:
        home = tmp_path
        tui: Any = None

    command = TuiCommand()
    session = Sess()
    ctx: Any = Ctx(session)
    assert "clássico" in (await command.execute("", ctx)).output_message
    assert not (await command.execute("xyz", ctx)).success
    assert "Já está" in (await command.execute("classic", ctx)).output_message
    assert "próxima vez" in (await command.execute("fullscreen", ctx)).output_message
    assert read_state(tmp_path)["mode"] == "fullscreen"

    relaunched: list[bool] = []

    class Tui:
        def request_relaunch(self) -> None:
            relaunched.append(True)

    session.tui = Tui()
    assert "tela cheia" in (await command.execute("", ctx)).output_message
    assert "Reabrindo" in (await command.execute("classic", ctx)).output_message and relaunched
