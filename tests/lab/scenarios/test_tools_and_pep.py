"""Ferramentas e modal PEP: tempo sem a espera (V-12), decisão registrada e status visível
(V-13), expansão com cabeçalho e alias (V-14)."""

from __future__ import annotations

import re

TOOLS = {
    "ferramentas": [
        {"text": "Vou rodar.", "tools": [["run_command", {"command": "seq 1 40"}]]},
        {"text": "Feito, contei até 40."},
    ]
}


def _approve_after(lab, seconds: float) -> None:  # type: ignore[no-untyped-def]
    assert lab.wait_for(r"\[y\]", 25), lab.screen_text()
    lab.pump(seconds)
    lab.send("y")


def test_tool_time_excludes_approval_wait(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(TOOLS)
    lab.submit("ferramentas")
    _approve_after(lab, 3.0)
    assert lab.wait_for("contei até 40", 20, history=True)
    line = next(ln for ln in lab.history_text().splitlines() if "Bash" in ln and "exit 0" in ln)
    seconds = float(re.search(r"(\d+)[.,](\d)s", line).group(0)[:-1].replace(",", "."))  # type: ignore[union-attr]
    assert seconds < 1.5, line


def test_pep_decision_is_recorded_and_status_stays(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(TOOLS)
    lab.submit("ferramentas")
    assert lab.wait_for(r"\[y\]", 25)
    lab.pump(0.5)
    assert re.search(r"accept-edits ·", lab.screen_text()), lab.screen_text()
    lab.send("y")
    assert lab.wait_for("contei até 40", 20, history=True)
    history = lab.history_text()
    assert "✔ aprovado" in history, history[-2500:]
    assert "[y] Aprovar" not in history, history[-2500:]


def test_pep_denial_is_recorded(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(TOOLS)
    lab.submit("ferramentas")
    assert lab.wait_for(r"\[y\]", 25)
    lab.send("n")
    assert lab.wait_for("✖ negado", 15, history=True), lab.history_text()[-2000:]


def test_expand_output_has_header_and_shift_alias(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(TOOLS)
    lab.submit("ferramentas")
    _approve_after(lab, 0.3)
    assert lab.wait_for("contei até 40", 20, history=True)
    assert lab.wait_ready(15)
    lab.key("alt-E")
    assert lab.wait_for("saída completa", 10, history=True), lab.history_text()[-2000:]
    lab.pump(0.5)
    assert not re.search(r"^❯ E\s*$", lab.screen_text(), re.M), lab.screen_text()
