"""
O.R.I.O.N TUI — Custom Prompt Keybindings.

Configures ergonomic terminal navigation:
- Ctrl+C: Graceful prompt interrupt / turn cancellation without killing the agent.
- Alt+Enter / Escape+Enter: Multi-line entry (insert newline without submitting).
- Ctrl+L: Clear terminal screen while preserving prompt state.
- Enter: Validate and submit current command/prompt.
"""

from __future__ import annotations

from collections.abc import Callable

from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent


def create_key_bindings(
    on_interrupt: Callable[[KeyPressEvent], None] | None = None,
    on_clear: Callable[[KeyPressEvent], None] | None = None,
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
            # Emite KeyboardInterrupt capturável pelo loop interativo
            event.app.exit(exception=KeyboardInterrupt("Prompt turn cancelled by user (Ctrl+C)"))

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

    return kb
