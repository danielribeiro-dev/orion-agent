"""v0.5.3 Sprint 2 — overlay de Presença e aprovação do plano com passos de presença (ADR-046/047).

O HOME do lab é temporário: ``~/.bashrc`` aqui é um arquivo descartável.
"""

from __future__ import annotations

import re

PRESENCE = {
    "presenca": [
        {"text": "Vou ajustar o shell.", "tools": [["write_file", {"path": "~/.bashrc", "content": "export ORION_LAB=1\n"}]]},
        {"text": "Pronto, ajuste recusado."},
    ]
}

PLAN = {
    "planeje": [
        {"text": "Entro no modo plano.", "tools": [["enter_plan_mode", {}]]},
        {
            "text": "Plano pronto.",
            "tools": [
                [
                    "exit_plan_mode",
                    {"plan": "# Plano\n1. Ajustar o shell do Senhor", "presence_paths": ["~/.bashrc"]},
                ]
            ],
        },
        {"text": "Aplicando.", "tools": [["write_file", {"path": "~/.bashrc", "content": "export ORION_LAB=2\n"}]]},
        {"text": "Shell ajustado conforme o plano."},
    ]
}

REVERSIBLE = {
    "limpe": [
        {"text": "Apagando o exemplo.", "tools": [["run_command", {"command": "rm sample.py"}]]},
        {"text": "Apaguei sample.py."},
    ]
}


def test_presence_overlay_shows_the_band(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(PRESENCE)
    lab.submit("presenca")
    assert lab.wait_for(r"y aprovar", 25), lab.screen_text()
    screen = lab.screen_text()
    assert re.search(r"presença", screen), screen
    lab.send("n")
    assert lab.wait_for("✖ negado", 15, history=True), lab.history_text()[-2000:]
    assert not (lab.home / ".bashrc").exists()


def test_plan_approval_covers_presence_steps(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(PLAN)
    lab.submit("planeje")
    assert lab.wait_for("Passos de presença", 25), lab.screen_text()
    assert "~/.bashrc" in lab.screen_text()
    lab.send("y")
    assert lab.wait_for("conforme o plano", 25, history=True), lab.history_text()[-2500:]
    history = lab.history_text()
    assert "aprovados com o plano" in history, history[-2500:]
    assert "y aprovar" not in history[history.index("aprovados com o plano") :], history[-2500:]
    assert (lab.home / ".bashrc").read_text() == "export ORION_LAB=2\n"


def test_reversible_delete_shows_trash_line(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(REVERSIBLE)
    lab.submit("limpe")
    assert lab.wait_for("Apaguei sample.py", 25, history=True), lab.history_text()[-2000:]
    history = lab.history_text()
    assert re.search(r"1 arquivo no lixo do ORION · /undo \w+", history), history[-2000:]
    assert "y aprovar" not in history
