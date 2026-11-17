"""Host ativo da tela cheia: modais e perguntas de texto delegam a ele quando existe (ADR-043).

``orion.tui.modal`` consulta :func:`active_host`; sem host, segue o caminho clássico (uma
``Application`` do prompt_toolkit por modal).
"""

from __future__ import annotations

from typing import Any, Protocol


class ScreenHost(Protocol):
    async def run_modal(self, controller: Any, keep_on_screen: bool = False) -> None: ...

    async def ask_text(self, question: str, default: str = "") -> str: ...

    async def ask_secret(self, title: str, detail: str = "") -> str | None: ...


_active: ScreenHost | None = None


def active_host() -> ScreenHost | None:
    return _active


def set_active_host(host: ScreenHost | None) -> None:
    global _active
    _active = host
