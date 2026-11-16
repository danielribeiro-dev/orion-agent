"""Tela cheia num pty real (ADR-043, v0.5.2 Sprint 2): input vivo, fila, reflow, ocioso e saída."""

from __future__ import annotations

import re

SLOW = {
    "devagar": [
        {
            "reasoning": "Vou pensar com calma antes de responder ao Senhor. " * 4,
            "text": "Resposta lenta, linha a linha.\n\n" + "Mais um parágrafo para o stream durar. " * 30,
        }
    ],
    "segundo": [{"text": "Segundo pedido atendido."}],
}


def test_input_stays_alive_and_enter_queues(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(SLOW, fullscreen=True, delay=0.06)
    lab.submit("devagar")
    assert lab.wait_for(r"Pensando|Raciocínio", 20), lab.screen_text()
    lab.send("segundo")
    lab.pump(0.5)
    screen = lab.screen_text()
    assert re.search(r"^❯ segundo", screen, re.M), screen  # o input aparece durante o turno
    lab.send("\r")
    assert lab.wait_for(r"na fila: segundo", 10), lab.screen_text()
    assert lab.wait_for(r"Segundo pedido atendido", 60), lab.screen_text()


def test_layout_pins_input_and_reflows_on_resize(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(SLOW, fullscreen=True, cols=110, rows=30)
    rows = lab.screen_text().splitlines()
    assert rows[-2].startswith("─") and rows[-3].startswith("❯") and rows[-4].startswith("─"), rows[-5:]
    lab.submit("segundo")
    assert lab.wait_for(r"Segundo pedido atendido", 30)
    lab.resize(70, 30)
    lab.pump(1.0)
    screen = lab.screen_text()
    assert all(len(line) <= 70 for line in screen.splitlines())
    assert screen.count("─" * 60) == 2, screen  # só as duas réguas do input, sem régua fantasma


def test_idle_does_not_write(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(SLOW, fullscreen=True)
    lab.submit("segundo")
    assert lab.wait_for(r"Segundo pedido atendido", 30)
    lab.pump(1.5)
    before = len(lab.raw)
    lab.pump(3.0)
    assert len(lab.raw) == before, bytes(lab.raw[before:])[:200]


def test_exit_restores_screen_and_leaves_summary(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(SLOW, fullscreen=True)
    lab.submit("segundo")
    assert lab.wait_for(r"Segundo pedido atendido", 30)
    lab.submit("/exit")
    assert lab.wait_for(r"Até logo, Senhor.*retome com orion --resume", 15, history=True), lab.history_text()[-800:]
