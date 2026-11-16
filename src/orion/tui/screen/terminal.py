"""Sinais do terminal na tela cheia (ADR-045, N-22 a N-24).

* **Synchronized output** (``CSI ?2026h`` … ``CSI ?2026l``): o terminal mostra cada quadro inteiro,
  nunca pela metade. Terminais sem suporte ignoram a sequência; ``ORION_SYNC_OUTPUT=0`` desliga.
* **Título da aba** (OSC 0) com o estado e **progresso nativo** (OSC 9;4, Ghostty, Konsole,
  Windows Terminal, WezTerm); ``ORION_PROGRESS=0`` desliga o progresso.
* **Eventos de foco** (``CSI ?1004h``): o spinner desacelera sem foco e um turno longo termina
  com o sino quando o Senhor está em outra janela.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Mapping
from typing import Any

from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
from prompt_toolkit.keys import Keys

BEGIN_SYNC = "\x1b[?2026h"
END_SYNC = "\x1b[?2026l"
FOCUS_ON = "\x1b[?1004h"
FOCUS_OFF = "\x1b[?1004l"
PROGRESS_BUSY = "\x1b]9;4;3\x07"
PROGRESS_CLEAR = "\x1b]9;4;0\x07"
FOCUS_IN_KEY = Keys.F23
FOCUS_OUT_KEY = Keys.F24


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def sync_supported(env: Mapping[str, str] | None = None) -> bool:
    env = _env(env)
    return env.get("ORION_SYNC_OUTPUT", "1") != "0" and env.get("TERM", "") != "linux"


def progress_supported(env: Mapping[str, str] | None = None) -> bool:
    env = _env(env)
    return env.get("ORION_PROGRESS", "1") != "0" and env.get("TERM", "") != "linux"


def enable_sync_output(output: Any) -> bool:
    """Embrulha o ``flush`` da saída: cada quadro vai entre BSU e ESU."""
    if not hasattr(output, "_buffer") or getattr(output, "_orion_sync", False):
        return False
    original = output.flush

    def flush() -> None:
        buffer = output._buffer
        if buffer:
            buffer.insert(0, BEGIN_SYNC)
            buffer.append(END_SYNC)
        original()

    output.flush = flush
    output._orion_sync = True
    return True


def register_focus_keys() -> None:
    """Ensina o parser do prompt_toolkit a reconhecer ``CSI I``/``CSI O`` (foco ganho/perdido)."""
    ANSI_SEQUENCES.setdefault("\x1b[I", FOCUS_IN_KEY)
    ANSI_SEQUENCES.setdefault("\x1b[O", FOCUS_OUT_KEY)


def write(output: Any, data: str) -> None:
    with contextlib.suppress(Exception):
        output.write_raw(data)
        output.flush()


def set_title(output: Any, text: str) -> None:
    with contextlib.suppress(Exception):
        output.set_title(text)
        output.flush()
