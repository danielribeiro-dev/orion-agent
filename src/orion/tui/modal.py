"""
O.R.I.O.N TUI — Interactive Modals.

Telas inline com teclado sobre prompt_toolkit, desenhadas com os painéis Rich do
Design System. Sem TTY, o modal apenas imprime o estado atual.
"""

from __future__ import annotations

import asyncio
import io
import shutil
import sys
from dataclasses import dataclass
from typing import Any, Protocol

from prompt_toolkit import Application, PromptSession
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from rich.console import Console, Group, RenderableType
from rich.text import Text

from orion.core.events import Action
from orion.governance.permissions import ActionLevel
from orion.tui.console import silence_cpr_warning
from orion.tui.panels import (
    render_config,
    render_model_picker,
    render_pep_dialog,
    render_plan_approval,
    render_question,
)
from orion.tui.screen.host import active_host
from orion.tui.theme import get_orion_theme


class ModalController(Protocol):
    """Estado de um modal, independente do terminal."""

    def render(self) -> RenderableType: ...

    def on_key(self, key: str) -> bool:
        """Processa a tecla; True fecha o modal."""
        ...


def render_ansi(renderable: RenderableType, width: int | None = None) -> str:
    """Rasteriza um renderable Rich para ANSI TrueColor."""
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        theme=get_orion_theme(),
        force_terminal=True,
        color_system="truecolor",
        width=width or shutil.get_terminal_size((100, 24)).columns,
    )
    console.print(renderable)
    return buffer.getvalue().rstrip("\n")


def is_interactive() -> bool:
    """True quando há um terminal real para receber teclas."""
    return sys.stdin.isatty() and sys.stdout.isatty()


async def run_modal(
    controller: ModalController, console: Console, keep_on_screen: bool = False
) -> None:
    """Conduz o modal até que o controller peça para fechar.

    Com a tela cheia ativa (ADR-043), o modal é desenhado por ela, acima do input.
    """
    host = active_host()
    if host is not None:
        await host.run_modal(controller, keep_on_screen)
        return
    if not is_interactive():
        console.print(controller.render())
        return

    bindings = KeyBindings()

    def dispatch(name: str, event: KeyPressEvent) -> None:
        if controller.on_key(name):
            event.app.exit()

    for key, name in (
        ("up", "up"),
        ("down", "down"),
        ("tab", "tab"),
        ("s-tab", "s-tab"),
        ("enter", "enter"),
        ("backspace", "backspace"),
        ("c-c", "escape"),
    ):
        bindings.add(key)(lambda event, name=name: dispatch(name, event))
    bindings.add("escape", eager=True)(lambda event: dispatch("escape", event))
    bindings.add(Keys.Any)(lambda event: dispatch(event.data, event))

    control = FormattedTextControl(lambda: ANSI(render_ansi(controller.render())))
    app: Application[None] = Application(
        layout=Layout(Window(control, dont_extend_height=True, always_hide_cursor=True)),
        key_bindings=bindings,
        erase_when_done=not keep_on_screen,
    )
    silence_cpr_warning(app)
    await app.run_async()


async def _ask_text(question: str, default: str = "") -> str:
    """Pergunta de texto livre: no input da tela cheia ou num ``PromptSession`` próprio."""
    host = active_host()
    if host is not None:
        return await host.ask_text(question, default)
    session: PromptSession[str] = PromptSession()
    silence_cpr_warning(session.app)
    return await session.prompt_async("❯ ", default=default)


class ModelPicker:
    """Blueprint B: lista com filtro por digitação."""

    def __init__(self, models: list[Any], current: str) -> None:
        self.models = models
        self.current = current
        self.query = ""
        self.selected = 0
        self.chosen: str | None = None

    @property
    def rows(self) -> list[Any]:
        query = self.query.lower()
        return [m for m in self.models if query in m.id.lower()]

    def render(self) -> RenderableType:
        return render_model_picker(self.rows, self.selected, self.current, self.query)

    def on_key(self, key: str) -> bool:
        rows = self.rows
        if key == "escape":
            return True
        if key == "enter":
            if rows:
                self.chosen = rows[self.selected].id
            return True
        if key == "up" and rows:
            self.selected = (self.selected - 1) % len(rows)
        elif key == "down" and rows:
            self.selected = (self.selected + 1) % len(rows)
        elif key == "backspace":
            self.query = self.query[:-1]
            self.selected = 0
        elif len(key) == 1 and key.isprintable():
            self.query += key
            self.selected = 0
        return False


@dataclass
class ConfigSetting:
    """Opção do /config; sem options, é somente leitura."""

    label: str
    get: Any
    options: list[str] | None = None
    set: Any = None


class ConfigPanel:
    """Blueprint A: categorias à esquerda, opções à direita."""

    def __init__(
        self,
        categories: dict[str, list[ConfigSetting]],
        notes: dict[str, list[str]] | None = None,
    ) -> None:
        self.categories = categories
        self.names = list(categories)
        self.notes = notes or {}
        self.category = 0
        self.setting = 0
        self.focus_right = False

    @property
    def settings(self) -> list[ConfigSetting]:
        return self.categories[self.names[self.category]]

    def render(self) -> RenderableType:
        rows = [(item.label, str(item.get())) for item in self.settings]
        notes = self.notes.get(self.names[self.category], [])
        return render_config(self.names, self.category, rows, self.setting, self.focus_right, notes)

    def on_key(self, key: str) -> bool:
        if key in ("escape", "q"):
            return True
        if key in ("tab", "s-tab"):
            self.focus_right = not self.focus_right and bool(self.settings)
            self.setting = 0
        elif key in ("up", "down"):
            step = 1 if key == "down" else -1
            if self.focus_right:
                self.setting = (self.setting + step) % len(self.settings)
            else:
                self.category = (self.category + step) % len(self.names)
                self.setting = 0
        elif key in ("enter", " ") and self.focus_right:
            item = self.settings[self.setting]
            if item.options:
                current = str(item.get())
                index = item.options.index(current) if current in item.options else -1
                item.set(item.options[(index + 1) % len(item.options)])
        return False


class PepChoice:
    """Blueprint D: decisão de uma tecla."""

    def __init__(
        self,
        action: Action,
        level: ActionLevel,
        reason: str | None = None,
        footer: RenderableType | None = None,
    ) -> None:
        self.action = action
        self.level = level
        self.reason = reason
        self.footer = footer
        self.choice = "n"

    def render(self) -> RenderableType:
        dialog = render_pep_dialog(self.action.tool, self.action.params, self.level, self.reason)
        if self.footer is None:
            return dialog
        return Group(dialog, Text(""), self.footer)

    def on_key(self, key: str) -> bool:
        lowered = key.lower()
        if lowered == "e" and self.action.tool != "run_command":
            return False
        if lowered == "a" and self.reason:
            return False  # escalada (sudo / fora do workspace) nunca vira "sempre"
        if lowered in ("y", "n", "e", "a"):
            self.choice = lowered
            return True
        if key == "escape":
            self.choice = "n"
            return True
        return False


async def ask_pep_decision(
    console: Console,
    action: Action,
    level: ActionLevel,
    reason: str | None = None,
    footer: RenderableType | None = None,
) -> Any:
    """Exibe o diálogo; sem terminal interativo a ação é negada.

    Enquanto o modal está aberto a linha de status continua visível (*footer*). Ao decidir, o
    histórico guarda o diálogo sem as teclas e a decisão do Senhor (V-13).
    """
    interactive = is_interactive() or active_host() is not None
    console.print()  # respiro entre a fala do modelo e o diálogo
    picker = PepChoice(action, level, reason, footer if interactive else None)
    await run_modal(picker, console, keep_on_screen=not interactive)
    if interactive:
        console.print(
            render_pep_dialog(action.tool, action.params, level, reason, show_keys=False)
        )
    if picker.choice != "e":
        _print_decision(console, picker.choice, level=int(level))
        return picker.choice
    edited = await _ask_text("comando editado (Enter aprova, vazio nega)", str(action.params.get("command", "")))
    if not edited.strip():
        _print_decision(console, "n", level=int(level))
        return "n"
    _print_decision(console, "e", edited.strip(), level=int(level))
    return {**action.params, "command": edited.strip()}


def _print_decision(console: Console, choice: str, edited: str = "", level: int | None = None) -> None:
    """Decisão na coluna das ferramentas, com o nível da ação (N-12, N-13)."""
    line = Text()
    if choice in ("y", "a", "e"):
        line.append("✔ aprovado", style="status_ok")
        if level is not None:
            line.append(f" · ação de nível {level}", style="text_dim")
        if choice == "a":
            line.append(" · sempre permitir", style="text_dim")
        elif choice == "e":
            line.append(f" · editado: {edited}", style="text_dim")
    else:
        line.append("✖ negado", style="diff_del")
        if level is not None:
            line.append(f" · ação de nível {level}", style="text_dim")
    console.print(line)


class AskChoice:
    """ask_user: escolha entre opções (uma ou várias) ou resposta livre."""

    def __init__(self, question: str, options: list[dict[str, str]], multi: bool = False) -> None:
        self.question = question
        self.options = options
        self.multi = multi
        self.selected = 0
        self.checked: set[int] = set()
        self.answers: list[str] = []
        self.wants_text = not options  # sem opções: vai direto para a resposta livre

    @property
    def _other_index(self) -> int:
        return len(self.options)

    def render(self) -> RenderableType:
        return render_question(self.question, self.options, self.selected, self.checked, self.multi)

    def on_key(self, key: str) -> bool:
        total = len(self.options) + 1
        if self.wants_text:
            return True
        if key == "escape":
            return True
        if key == "up":
            self.selected = (self.selected - 1) % total
        elif key == "down":
            self.selected = (self.selected + 1) % total
        elif key.isdigit() and 1 <= int(key) <= total:
            self.selected = int(key) - 1
            return self._confirm() if not self.multi else self._toggle()
        elif key == " " and self.multi:
            return self._toggle()
        elif key == "enter":
            return self._confirm()
        return False

    def _toggle(self) -> bool:
        if self.selected == self._other_index:
            self.wants_text = True
            return True
        self.checked.symmetric_difference_update({self.selected})
        return False

    def _confirm(self) -> bool:
        if self.selected == self._other_index:
            self.wants_text = True
            return True
        picks = sorted(self.checked) if self.multi and self.checked else [self.selected]
        self.answers = [self.options[i]["label"] for i in picks]
        return True


async def ask_user_choice(
    console: Console, question: str, options: list[dict[str, str]], multi: bool = False
) -> list[str] | None:
    """Pergunta ao Senhor; sem terminal interativo devolve None (a tool falha com clareza)."""
    if not is_interactive() and active_host() is None:
        return None
    picker = AskChoice(question, options, multi)
    if not picker.wants_text:
        await run_modal(picker, console, keep_on_screen=True)
    if picker.wants_text:
        console.print(Text(question, style="text_primary"))
        typed = (await _ask_text("sua resposta")).strip()
        return [typed] if typed else None
    return picker.answers or None


class PlanApproval:
    """exit_plan_mode: aprovação do plano em uma tecla."""

    def __init__(self, plan: str, mode_label: str) -> None:
        self.plan = plan
        self.mode_label = mode_label
        self.approved = False

    def render(self) -> RenderableType:
        return render_plan_approval(self.plan, self.mode_label)

    def on_key(self, key: str) -> bool:
        lowered = key.lower()
        if lowered == "y":
            self.approved = True
            return True
        return lowered == "n" or key == "escape"


async def approve_plan(console: Console, plan: str, mode_label: str) -> bool:
    """Mostra o plano; sem terminal interativo o plano NÃO é aprovado."""
    if not is_interactive() and active_host() is None:
        return False
    modal = PlanApproval(plan, mode_label)
    await run_modal(modal, console, keep_on_screen=True)
    return modal.approved


async def ask_secret(console: Console, request: Any) -> str | None:
    """Pede uma senha ao Senhor sem eco (ADR-048). None = cancelado ou ninguém para responder.

    Tela cheia: input mascarado do host (nunca vai para o histórico). Modo clássico: prompt sem
    eco do prompt_toolkit. Sem terminal, mas com display: diálogo de senha do SO (zenity). A
    verificação é sempre do sudo ou do PAM, nunca deste diálogo.
    """
    title = str(getattr(request, "title", "Senha"))
    command = str(getattr(request, "command", ""))
    detail = command if len(command) <= 100 else command[:97] + "..."
    host = active_host()
    if host is not None:
        return await host.ask_secret(title, detail)
    if is_interactive():
        console.print(Text.assemble(("[PEP] ", "pep_warn"), (title, "text_primary"), (f"  ·  {detail}", "text_dim")))
        session: PromptSession[str] = PromptSession()
        silence_cpr_warning(session.app)
        try:
            answer = await session.prompt_async("senha › ", is_password=True)
        except (EOFError, KeyboardInterrupt):
            return None
        return answer or None
    return await _graphical_secret(title, detail)


async def _graphical_secret(title: str, detail: str) -> str | None:
    import os
    import shutil

    zenity = shutil.which("zenity")
    if not zenity or not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None
    proc = await asyncio.create_subprocess_exec(
        zenity, "--password", "--title", f"O.R.I.O.N · {title}",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
    except TimeoutError:
        proc.kill()
        return None
    if proc.returncode != 0:
        return None
    secret = out.decode("utf-8", errors="replace").rstrip("\n")
    return secret or None
