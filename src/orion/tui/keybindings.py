"""
O.R.I.O.N TUI — Custom Prompt Keybindings.

Configures ergonomic terminal navigation:
- Ctrl+C: Graceful prompt interrupt / turn cancellation without killing the agent.
- Alt+Enter / Escape+Enter: Multi-line entry (insert newline without submitting).
- Ctrl+L: Clear terminal screen while preserving prompt state.
- Enter: Validate and submit current command/prompt.
- Shift+Tab / Alt+T / Alt+O: cycle agent mode, reasoning effort and fast mode.
- Alt+R / Alt+E: expand the last reasoning block / the last collapsed tool output.
"""

from __future__ import annotations

from collections.abc import Callable

from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.filters import has_completions
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent


def create_key_bindings(
    on_interrupt: Callable[[KeyPressEvent], None] | None = None,
    on_clear: Callable[[KeyPressEvent], None] | None = None,
    on_escape: Callable[[KeyPressEvent], None] | None = None,
    on_cycle_mode: Callable[[], None] | None = None,
    on_cycle_effort: Callable[[], None] | None = None,
    on_toggle_fast: Callable[[], None] | None = None,
    on_expand_reasoning: Callable[[], None] | None = None,
    on_expand_output: Callable[[], None] | None = None,
) -> KeyBindings:
    """Cria e registra os atalhos de teclado oficiais do O.R.I.O.N."""
    kb = KeyBindings()

    @kb.add("c-c")
    def _handle_ctrl_c(event: KeyPressEvent) -> None:
        """Trata Ctrl+C graciosamente.

        Se houver texto digitado no buffer, limpa o buffer.
        Se o buffer já estiver vazio ou se houver um hook registrado, dispara interrupção
        sem abortar abruptamente a sessão do terminal.
        """
        if on_interrupt is not None:
            on_interrupt(event)
            return

        buf = event.current_buffer
        if buf.text:
            buf.text = ""
        else:
            # Emite KeyboardInterrupt capturável pelo loop interativo para checar duplo Ctrl+C
            event.app.exit(exception=KeyboardInterrupt("Prompt turn cancelled by user (Ctrl+C)"))

    @kb.add("escape", filter=~has_completions)
    def _handle_escape(event: KeyPressEvent) -> None:
        """Trata Esc para cancelar / limpar o prompt ou fechar abas quando o menu não estiver ativo."""
        if on_escape is not None:
            on_escape(event)
            return

        buf = event.current_buffer
        if buf.text:
            buf.text = ""
        else:
            event.app.exit(result="")

    @kb.add("escape", "enter")
    def _handle_alt_enter(event: KeyPressEvent) -> None:
        """Permite quebra de linha (Alt+Enter / Meta+Enter) para colar código ou prompt multilinha."""
        event.current_buffer.insert_text("\n")

    @kb.add("c-l")
    def _handle_ctrl_l(event: KeyPressEvent) -> None:
        """Limpa a tela do terminal (Ctrl+L) preservando o buffer atual."""
        if on_clear is not None:
            on_clear(event)
        else:
            event.app.renderer.clear()

    def _bind_state(key: tuple[str, ...], action: Callable[[], None] | None, **kw: object) -> None:
        """Atalho que altera o estado da sessão e redesenha a linha de status."""
        if action is None:
            return

        def _handler(event: KeyPressEvent) -> None:
            action()
            event.app.invalidate()

        kb.add(*key, **kw)(_handler)  # type: ignore[arg-type]

    def _bind_print(key: tuple[str, ...], action: Callable[[], None] | None) -> None:
        """Atalho que imprime no scrollback sem corromper o prompt."""
        if action is None:
            return

        def _handler(event: KeyPressEvent) -> None:
            run_in_terminal(action)

        kb.add(*key)(_handler)

    _bind_state(("s-tab",), on_cycle_mode, filter=~has_completions)
    _bind_state(("escape", "t"), on_cycle_effort)
    _bind_state(("escape", "o"), on_toggle_fast)
    _bind_print(("escape", "r"), on_expand_reasoning)
    _bind_print(("escape", "e"), on_expand_output)

    return kb
