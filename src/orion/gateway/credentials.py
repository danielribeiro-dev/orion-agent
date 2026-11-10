"""
O.R.I.O.N — Credenciais de provedores (v0.5.0 Sprint 1)

A chave da Anthropic vem de ``ANTHROPIC_API_KEY`` ou do arquivo
``~/.orion/anthropic_api_key`` (nunca de arquivos versionados). O ambiente vence.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

KEY_FILE_NAME = "anthropic_api_key"
OPENROUTER_KEY_FILE_NAME = "openrouter_api_key"
_KEY_PREFIX = "sk-ant-"


@dataclass(frozen=True)
class KeyStatus:
    """Resultado da inspeção da chave (sem rede e sem custo)."""

    found: bool
    source: str  # "env" | "file" | "ausente"
    well_formed: bool
    file_too_open: bool = False  # arquivo legível por grupo/outros

    @property
    def detail(self) -> str:
        if not self.found:
            return f"ausente (defina ANTHROPIC_API_KEY ou ~/.orion/{KEY_FILE_NAME})"
        parts = [f"configurada via {self.source}"]
        if not self.well_formed:
            parts.append(f"formato inesperado (esperado prefixo {_KEY_PREFIX})")
        if self.file_too_open:
            parts.append("arquivo legível por outros usuários: rode chmod 600")
        return "; ".join(parts)

    @property
    def ok(self) -> bool:
        return self.found and self.well_formed and not self.file_too_open


def load_anthropic_key(home: Path) -> str | None:
    """Retorna a chave (env > arquivo) ou ``None``."""
    env = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env:
        return env
    path = home / KEY_FILE_NAME
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def inspect_anthropic_key(home: Path) -> KeyStatus:
    """Valida presença, formato e permissões da chave, sem expô-la."""
    key = load_anthropic_key(home)
    if key is None:
        return KeyStatus(found=False, source="ausente", well_formed=False)
    from_env = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    too_open = False
    if not from_env:
        try:
            mode = (home / KEY_FILE_NAME).stat().st_mode
            too_open = bool(mode & (stat.S_IRWXG | stat.S_IRWXO))
        except OSError:
            pass
    return KeyStatus(
        found=True,
        source="env" if from_env else "file",
        well_formed=key.startswith(_KEY_PREFIX),
        file_too_open=too_open,
    )


def load_openrouter_key(home: Path) -> str | None:
    """Chave do OpenRouter: ``OPENROUTER_API_KEY`` (env vence) ou ``~/.orion/openrouter_api_key``."""
    env = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env:
        return env
    try:
        value = (home / OPENROUTER_KEY_FILE_NAME).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None
