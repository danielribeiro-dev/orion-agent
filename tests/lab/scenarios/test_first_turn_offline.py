"""V-09 / CA-01: o primeiro envio não acessa a rede nem suja a TUI; o recall cai no BM25."""

from __future__ import annotations

import re

NETWORK_NOISE = re.compile(r"Downloading|Fetching \d+ files|HF_TOKEN|huggingface|\| ERROR |fastembed")


def test_first_turn_has_no_network_noise(open_lab, network_trap) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab()
    lab.submit("oi")
    assert lab.wait_for("pong", 25), lab.screen_text()
    assert lab.wait_ready(20)
    history = lab.history_text()
    assert not NETWORK_NOISE.search(history), history[-2500:]
    assert network_trap.connections == 0, f"{network_trap.connections} tentativas de rede"


def test_semantic_memory_notice_is_shown_once(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab()
    lab.submit("oi")
    assert lab.wait_ready(25)
    lab.submit("de novo")
    assert lab.wait_for(r"❯ de novo", 10, history=True)
    assert lab.wait_ready(25)
    assert lab.history_text().count("Memória semântica desligada") == 1, lab.history_text()[-2500:]
