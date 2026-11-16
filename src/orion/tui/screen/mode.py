"""Escolha do renderizador: tela cheia (padrão) ou clássico, e reserva automática (ADR-043).

Preferência e contador de partidas falhas ficam em ``~/.orion/tui_state.json``. Uma partida da
tela cheia conta como falha até ela desenhar e durar 10 s ou terminar de forma limpa; duas falhas
seguidas fazem o ORION abrir no modo clássico até o Senhor pedir ``/tui fullscreen``.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Mode = Literal["fullscreen", "classic"]
MAX_FAILED_STARTS = 2
STATE_FILE = "tui_state.json"


@dataclass(frozen=True)
class Choice:
    mode: Mode
    reason: str


def _state_path(home: Path) -> Path:
    return home / STATE_FILE


def read_state(home: Path) -> dict[str, Any]:
    try:
        data = json.loads(_state_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(home: Path, **changes: Any) -> dict[str, Any]:
    state = read_state(home)
    state.update(changes)
    try:
        home.mkdir(parents=True, exist_ok=True)
        tmp = _state_path(home).with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, _state_path(home))
    except OSError:
        pass
    return state


def choose(
    home: Path,
    env: Mapping[str, str] | None = None,
    *,
    is_tty: bool | None = None,
) -> Choice:
    """Decide o renderizador desta partida, na ordem da tabela do ADR-043."""
    env = os.environ if env is None else env
    if is_tty is None:
        is_tty = sys.stdin.isatty() and sys.stdout.isatty()
    forced = env.get("ORION_TUI", "").strip().lower()
    if forced == "classic":
        return Choice("classic", "ORION_TUI=classic")
    if not is_tty:
        return Choice("classic", "sem terminal interativo")
    if env.get("TERM", "") in ("dumb", ""):
        return Choice("classic", f"TERM={env.get('TERM', '') or 'vazio'}")
    if forced == "fullscreen":
        return Choice("fullscreen", "ORION_TUI=fullscreen")
    state = read_state(home)
    if int(state.get("failed_starts", 0)) >= MAX_FAILED_STARTS:
        return Choice("classic", "a tela cheia falhou ao iniciar duas vezes (/tui fullscreen tenta de novo)")
    if state.get("mode") == "classic":
        return Choice("classic", "preferência salva (/tui)")
    return Choice("fullscreen", "padrão")


def mark_starting(home: Path) -> None:
    state = read_state(home)
    write_state(home, failed_starts=int(state.get("failed_starts", 0)) + 1)


def mark_started(home: Path) -> None:
    write_state(home, failed_starts=0)


def save_preference(home: Path, mode: Mode) -> None:
    write_state(home, mode=mode, failed_starts=0)
