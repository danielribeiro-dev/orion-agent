"""Prompt e teclas: Esc fecha o menu (V-15), Ctrl+C com menu (V-16), rodapé sem CPR
(V-05/V-06) e digitação durante o turno (V-11)."""

from __future__ import annotations

from tests.lab.texts import LONG


def _prompt_block_intact(lab) -> bool:  # type: ignore[no-untyped-def]
    """Régua, ❯, régua e status em sequência, e nada abaixo (sem resíduo do menu, V-16)."""
    rows = [line.rstrip() for line in lab.screen.display]
    i = max(n for n, line in enumerate(rows) if line.startswith("❯"))
    block = rows[i - 1 : i + 3]
    return (
        len(block) == 4
        and set(block[0]) == {"─"}
        and set(block[2]) == {"─"}
        and block[3].startswith("auto ·")
        and not any(rows[i + 3 :])
    )


def test_escape_closes_completion_menu(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab()
    lab.send("/c")
    assert lab.wait_for(r"/context", 10)
    lab.key("esc")
    lab.pump(1.2)
    assert "/context" not in lab.screen_text(), lab.screen_text()
    assert "❯ /c" in lab.screen_text()  # Esc fecha o menu e mantém o texto
    assert _prompt_block_intact(lab), lab.screen_text()  # sem resíduo do menu (V-16)
    assert lab.alive()


def test_ctrl_c_with_menu_closes_menu_and_hints_exit(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab()
    lab.send("/c")
    assert lab.wait_for(r"/context", 10)
    lab.key("ctrl-c")
    lab.pump(1.0)
    screen = lab.screen_text()
    assert "/context" not in screen, screen
    assert _prompt_block_intact(lab), screen
    assert lab.alive()
    lab.key("ctrl-c")  # buffer vazio: avisa que o próximo sai
    assert lab.wait_for("Ctrl\\+C de novo para sair", 5), lab.screen_text()
    assert lab.alive()


def test_footer_without_cpr(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(cpr=False)
    lab.pump(1.0)
    screen = lab.screen_text()
    assert "auto ·" in screen, screen
    assert "CPR" not in lab.history_text(), lab.history_text()[-1500:]


def test_typing_during_turn_is_echoed_and_queued(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab({"longo": [{"text": LONG}]})
    lab.submit("texto longo")
    assert lab.wait_for("Análise do módulo", 20)
    lab.send("abc")
    assert lab.wait_for(r"❯ abc", 2.0), lab.screen_text()
    lab.send("\r")
    assert lab.wait_for(r"1 na fila", 2.0), lab.screen_text()
    assert lab.wait_for(r"❯ abc", 40, history=True)
    assert lab.wait_for("pong", 30, history=True), lab.history_text()[-2000:]
