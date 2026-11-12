"""Stream em movimento: cadência (CA-02), bloco de código alto (V-10), cancelamento (V-17)
e aviso de travamento (1B.7)."""

from __future__ import annotations

import os
import re

from tests.lab.probes import load_baseline, measure, record
from tests.lab.texts import CODE_TALL, LONG, STALL


def test_long_answer_cadence(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab({"longo": [{"text": LONG}]})
    cpu0 = lab.cpu_seconds()
    lab.samples.clear()
    sent = lab.now()
    lab.submit("texto longo")
    assert lab.wait_for("Análise do módulo", 20)
    first = lab.now()
    assert lab.wait_for("Fim da resposta longa", 40, history=True)
    assert lab.wait_ready(20)
    probe = measure(lab.samples, sent, first, lab.now(), lab.cpu_seconds() - cpu0)
    if os.environ.get("ORION_LAB_RECORD") == "1":
        record("long_answer", probe)
    base = load_baseline().get("long_answer")
    print(f"\nPROBE {probe}")
    assert probe.updates_per_s >= 10, probe  # CA-02
    assert probe.max_gap_after_first_s <= 0.3, probe
    if base:
        assert probe.cpu_core_pct <= base["cpu_core_pct"] * 1.2, (probe, base)
        assert probe.total_s <= base["total_s"] * 1.1, (probe, base)


def test_tall_code_block_leaves_no_ghost_frame(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab({"arquivo": [{"text": CODE_TALL}]}, rows=24)
    lab.submit("mostre o arquivo")
    assert lab.wait_for("Fim do arquivo", 40, history=True)
    assert lab.wait_ready(20)
    history = lab.history_text()
    tops = [line for line in history.splitlines() if line.lstrip().startswith("╭")]
    # Um único bloco de código: uma única borda superior; nada de quadro vazio "preso".
    assert len(tops) == 1, history[-3000:]
    assert history.count("linha_40 = 40") == 1, history[-3000:]


def test_live_view_keeps_newest_lines_visible(open_lab) -> None:  # type: ignore[no-untyped-def]
    """Com o bloco aberto e mais alto que a tela, a última linha recebida aparece ao vivo."""
    lab = open_lab({"arquivo": [{"text": CODE_TALL}]}, rows=24, delay=0.05)
    lab.submit("mostre o arquivo")
    assert lab.wait_for(r"linha_30 = 30", 40), lab.screen_text()


def test_cancel_keeps_text_already_shown(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab({"longo": [{"text": LONG}]})
    lab.submit("texto longo")
    assert lab.wait_for("Blocos de código só", 30)
    lab.key("ctrl-c")
    assert lab.wait_for("interrompido", 15, history=True)
    history = lab.history_text()
    assert "Blocos de código só" in history, history[-3000:]
    assert lab.alive()


def test_stall_notice_after_five_seconds(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab({"travar": [{"text": STALL, "stall_after": 0.5, "stall_seconds": 8}]})
    lab.submit("travar agora")
    assert lab.wait_for("pausa no meio", 15)
    assert lab.wait_for(r"sem resposta há \d+s", 9), lab.screen_text()
    assert lab.wait_ready(20)
    assert not re.search(r"sem resposta há", lab.screen_text())
