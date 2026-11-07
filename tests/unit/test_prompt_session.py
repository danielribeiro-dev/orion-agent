"""
Unit tests for InteractivePrompt, keybindings, and signal/cancellation handling.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion.core.event_bus import EventBus
from orion.core.events import TurnCancelledEvent
from orion.tui.keybindings import create_key_bindings
from orion.tui.prompt import InteractivePrompt, get_prompt_style
from orion.tui.status_bar import ReasoningEffort, SessionStatusBar


class TestInteractivePromptBasics:
    """Testes de inicialização, configuração e histórico do InteractivePrompt."""

    def test_prompt_instantiation_with_custom_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            hist_file = Path(tmp_dir) / "sub" / "history"
            prompt = InteractivePrompt(
                workspace_root=tmp_dir,
                history_path=hist_file,
            )
            assert prompt.workspace_root == Path(tmp_dir).resolve()
            assert prompt.history_path == hist_file.resolve()
            assert hist_file.parent.exists()
            assert prompt.session is not None
            assert prompt.completer is not None

    def test_prompt_history_fallback_on_unwritable_path(self) -> None:
        from prompt_toolkit.history import InMemoryHistory

        # Forçar erro ao criar diretório passando caminho inválido/bloqueado
        with patch.object(Path, "mkdir", side_effect=OSError("Permission denied")):
            prompt = InteractivePrompt(history_path="/root/forbidden/history")
            assert isinstance(prompt.history, InMemoryHistory)

    def test_prompt_prefix_formatting(self) -> None:
        prompt = InteractivePrompt()
        prefix = prompt.get_prompt_prefix()
        plain_text = "".join(part[1] for part in prefix)
        assert "❯" in plain_text
        assert "─" not in plain_text
        assert plain_text == "❯ "

    def test_dock_to_bottom(self) -> None:
        prompt = InteractivePrompt()
        # Não deve levantar exceções nem injetar newlines forçadas
        prompt.dock_to_bottom(rendered_lines=15)
        prompt.dock_to_bottom(rendered_lines=200)

    def test_prompt_style_mapping(self) -> None:
        from prompt_toolkit.styles import default_ui_style, merge_styles

        style = get_prompt_style()
        assert style is not None
        # Validar ausência de bg:surface_panel na toolbar (CA-04: sem fundo sólido)
        style_rules = dict(style.style_rules)
        assert "bottom-toolbar" in style_rules
        toolbar_style = style_rules.get("bottom-toolbar", "")
        assert "bg:" not in toolbar_style
        assert "noreverse" in toolbar_style

        # Garantir que a mesclagem com default_ui_style desativa reverse (evita barra colorida sólida invertida)
        merged = merge_styles([default_ui_style(), style])
        attrs = merged.get_attrs_for_style_str("class:bottom-toolbar")
        assert attrs.reverse is False

    def test_tunnel_layout_structure(self) -> None:
        """Verifica a presença do menu flutuante acima do prompt e ausência de túneis rígidos (CA-03)."""
        prompt = InteractivePrompt()
        children = prompt.session.layout.container.children
        # Estrutura deve conter comp_window + main_input (mínimo 2 filhos)
        assert len(children) >= 2
        # Zero espaço reservado forçado (menu abre dinamicamente no container flutuante superior)
        assert prompt.session.reserve_space_for_menu == 0
        # Túneis rígidos foram eliminados: top_tunnel e bottom_tunnel não devem existir
        assert not hasattr(prompt, "top_tunnel"), "top_tunnel removido na Sprint 3"
        assert not hasattr(prompt, "bottom_tunnel"), "bottom_tunnel removido na Sprint 3"


class TestBottomToolbarIntegration:
    """Testes da integração da barra de status inferior Rich com o prompt_toolkit."""

    def test_bottom_toolbar_online_with_costs(self) -> None:
        import os

        status_bar = SessionStatusBar(
            is_online=True,
            model_name="claude-3-7-sonnet-thinking",
            reasoning_effort=ReasoningEffort.HIGH,
            pep_level=2,
            session_tokens_in=1500,
            session_tokens_out=600,
            session_cost_usd=0.0125,
            usd_to_brl_rate=5.50,
        )
        prompt = InteractivePrompt(status_bar=status_bar)

        # Em terminal standard/amplo (>= 110 colunas): exibe layout limpo com separadores · sutis
        with patch("shutil.get_terminal_size", return_value=os.terminal_size((140, 24))):
            toolbar = prompt.get_bottom_toolbar()
            plain_text = "".join(part[1] for part in toolbar)

            assert "claude-3-7-sonnet" in plain_text
            assert "thinking: high" in plain_text
            assert "PEP: 2" in plain_text
            assert "1.5k in / 600 out" in plain_text
            assert "$0.0125" in plain_text
            assert "R$" in plain_text
            assert "Ready ●" in plain_text
            assert " · " in plain_text
            assert " │ " not in plain_text

            # Verificar se classe CSS online foi aplicada
            styles = [part[0] for part in toolbar]
            assert "class:bottom-toolbar.ok" in styles
            assert "class:bottom-toolbar.border" in styles
            assert "─" not in plain_text

        # Em terminal padrão 80 colunas (Item 4: Clean Status Line):
        # claude-3-7-sonnet · 2.1k tok · $0.0125 · Ready ●
        with patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 24))):
            toolbar_compact = prompt.get_bottom_toolbar()
            compact_text = "".join(part[1] for part in toolbar_compact)
            assert "claude-3-7-sonnet · 2.1k tok · $0.0125 · Ready ●" in compact_text
            assert " · " in compact_text
            assert " │ " not in compact_text
            assert "Ready ●" in compact_text
            assert "─" not in compact_text

    def test_bottom_toolbar_offline_status(self) -> None:
        status_bar = SessionStatusBar(
            is_online=False,
            model_name="qwen-2.5-coder-32b",
            reasoning_effort=ReasoningEffort.LOW,
            pep_level=1,
        )
        prompt = InteractivePrompt(status_bar=status_bar)
        toolbar = prompt.get_bottom_toolbar()
        plain_text = "".join(part[1] for part in toolbar)

        assert "Offline ●" in plain_text
        styles = [part[0] for part in toolbar]
        assert "class:bottom-toolbar.offline" in styles


class TestKeybindings:
    """Testes da criação e comportamento dos atalhos de teclado."""

    def test_create_key_bindings_registration(self) -> None:
        from prompt_toolkit.keys import Keys

        kb = create_key_bindings()
        bindings = kb.bindings
        keys = [b.keys for b in bindings]

        # Ctrl+C
        assert any((Keys.ControlC,) == k for k in keys)
        # Alt+Enter (escape, enter)
        assert any((Keys.Escape, Keys.ControlM) == k for k in keys)
        # Ctrl+L
        assert any((Keys.ControlL,) == k for k in keys)

    def test_ctrl_c_clears_buffer_when_text_present(self) -> None:
        from prompt_toolkit.keys import Keys

        kb = create_key_bindings()
        binding = next(b for b in kb.bindings if b.keys == (Keys.ControlC,))

        mock_event = MagicMock()
        mock_event.current_buffer.text = "unfinished command"

        binding.call(mock_event)
        assert mock_event.current_buffer.text == ""

    def test_ctrl_c_raises_interrupt_when_buffer_empty(self) -> None:
        from prompt_toolkit.keys import Keys

        kb = create_key_bindings()
        binding = next(b for b in kb.bindings if b.keys == (Keys.ControlC,))

        mock_event = MagicMock()
        mock_event.current_buffer.text = ""

        binding.call(mock_event)
        mock_event.app.exit.assert_called_once()
        args, kwargs = mock_event.app.exit.call_args
        assert isinstance(kwargs.get("exception"), KeyboardInterrupt)

    def test_alt_enter_inserts_newline(self) -> None:
        from prompt_toolkit.keys import Keys

        kb = create_key_bindings()
        binding = next(b for b in kb.bindings if b.keys == (Keys.Escape, Keys.ControlM))

        mock_event = MagicMock()
        binding.call(mock_event)
        mock_event.current_buffer.insert_text.assert_called_once_with("\n")

    def test_ctrl_l_clears_screen(self) -> None:
        from prompt_toolkit.keys import Keys

        kb = create_key_bindings()
        binding = next(b for b in kb.bindings if b.keys == (Keys.ControlL,))

        mock_event = MagicMock()
        binding.call(mock_event)
        mock_event.app.renderer.clear.assert_called_once()

    def test_escape_clears_buffer_when_text_present(self) -> None:
        from prompt_toolkit.keys import Keys

        kb = create_key_bindings()
        binding = next(b for b in kb.bindings if b.keys == (Keys.Escape,))

        mock_event = MagicMock()
        mock_event.current_buffer.text = "comando digitado"

        binding.call(mock_event)
        assert mock_event.current_buffer.text == ""

    def test_escape_exits_prompt_when_buffer_empty(self) -> None:
        from prompt_toolkit.keys import Keys

        kb = create_key_bindings()
        binding = next(b for b in kb.bindings if b.keys == (Keys.Escape,))

        mock_event = MagicMock()
        mock_event.current_buffer.text = ""

        binding.call(mock_event)
        mock_event.app.exit.assert_called_once_with(result="")

    def test_custom_keybinding_hooks(self) -> None:
        from prompt_toolkit.keys import Keys

        interrupt_called = False
        clear_called = False

        def custom_interrupt(evt: Any) -> None:
            nonlocal interrupt_called
            interrupt_called = True

        def custom_clear(evt: Any) -> None:
            nonlocal clear_called
            clear_called = True

        kb = create_key_bindings(on_interrupt=custom_interrupt, on_clear=custom_clear)

        ctrl_c_binding = next(b for b in kb.bindings if b.keys == (Keys.ControlC,))
        ctrl_l_binding = next(b for b in kb.bindings if b.keys == (Keys.ControlL,))

        dummy_event = MagicMock()
        ctrl_c_binding.call(dummy_event)
        assert interrupt_called is True

        ctrl_l_binding.call(dummy_event)
        assert clear_called is True


class TestSignalAndTurnCancellation:
    """Cenário de Teste Obrigatório 3: Cancelamento gracioso de turnos com Ctrl+C."""

    @pytest.mark.asyncio
    async def test_ctrl_c_during_task_emits_turn_cancelled_event(self) -> None:
        """Cenário de Teste 3: Envio de Ctrl+C durante execução de tarefa emite TurnCancelledEvent sem fechar o CLI."""
        bus = EventBus()
        cancelled_events: list[TurnCancelledEvent] = []

        @bus.subscribe(TurnCancelledEvent)
        async def on_cancelled(event: TurnCancelledEvent) -> None:
            cancelled_events.append(event)

        prompt = InteractivePrompt(event_bus=bus)

        async def simulated_running_task() -> str:
            # Simula interrupção pelo usuário via Ctrl+C durante uma inferência de LLM ou tool call
            raise KeyboardInterrupt("Simulated Ctrl+C")

        result = await prompt.run_turn(
            simulated_running_task(),
            session_id="session-test-42",
            turn_index=3,
        )

        # O CLI não deve quebrar: o resultado é None e o evento foi disparado
        assert result is None
        assert len(cancelled_events) == 1
        event = cancelled_events[0]
        assert event.session_id == "session-test-42"
        assert event.turn_index == 3
        assert "Ctrl+C" in event.reason

    @pytest.mark.asyncio
    async def test_cancelled_error_during_task_emits_turn_cancelled_event(self) -> None:
        """asyncio.CancelledError também deve emitir TurnCancelledEvent e ser absorvido graciosamente."""
        bus = EventBus()
        cancelled_events: list[TurnCancelledEvent] = []

        @bus.subscribe(TurnCancelledEvent)
        async def on_cancelled(event: TurnCancelledEvent) -> None:
            cancelled_events.append(event)

        prompt = InteractivePrompt(event_bus=bus)

        async def cancelled_task() -> str:
            raise asyncio.CancelledError()

        result = await prompt.run_turn(
            cancelled_task(),
            session_id="session-async-cancel",
            turn_index=1,
        )

        assert result is None
        assert len(cancelled_events) == 1
        assert cancelled_events[0].session_id == "session-async-cancel"

    @pytest.mark.asyncio
    async def test_run_turn_handles_event_bus_publish_error_gracefully(self) -> None:
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=RuntimeError("Bus connection dropped"))

        prompt = InteractivePrompt(event_bus=mock_bus)

        async def interrupted_task() -> None:
            raise KeyboardInterrupt()

        # Não deve estourar erro mesmo se o publish falhar
        res = await prompt.run_turn(interrupted_task(), session_id="err-bus", turn_index=1)
        assert res is None

    @pytest.mark.asyncio
    async def test_successful_turn_returns_value(self) -> None:
        """Execução normal de turno conclui e retorna valor sem eventos de cancelamento."""
        bus = EventBus()
        prompt = InteractivePrompt(event_bus=bus)

        async def successful_task() -> str:
            return "Task completed successfully"

        result = await prompt.run_turn(successful_task(), session_id="session-ok", turn_index=1)
        assert result == "Task completed successfully"


class TestPromptInvocation:
    """Testes dos métodos prompt() e prompt_async()."""

    def test_sync_prompt_capture_keyboard_interrupt(self) -> None:
        prompt = InteractivePrompt()
        prompt.session.prompt = MagicMock(side_effect=KeyboardInterrupt())

        # Não deve estourar exceção; deve retornar string vazia
        res = prompt.prompt(raise_on_interrupt=False)
        assert res == ""

        # Com raise_on_interrupt=True, deve re-levantar
        with pytest.raises(KeyboardInterrupt):
            prompt.prompt(raise_on_interrupt=True)

    @pytest.mark.asyncio
    async def test_async_prompt_capture_keyboard_interrupt(self) -> None:
        prompt = InteractivePrompt()
        prompt.session.prompt_async = AsyncMock(side_effect=KeyboardInterrupt())

        res = await prompt.prompt_async(raise_on_interrupt=False)
        assert res == ""

        with pytest.raises(KeyboardInterrupt):
            await prompt.prompt_async(raise_on_interrupt=True)

    def test_sync_prompt_success(self) -> None:
        prompt = InteractivePrompt()
        prompt.session.prompt = MagicMock(return_value="/plan Create tests")

        res = prompt.prompt()
        assert res == "/plan Create tests"

    @pytest.mark.asyncio
    async def test_async_prompt_success(self) -> None:
        prompt = InteractivePrompt()
        prompt.session.prompt_async = AsyncMock(return_value="@src/orion/cli.py analyze")

        res = await prompt.prompt_async()
        assert res == "@src/orion/cli.py analyze"
