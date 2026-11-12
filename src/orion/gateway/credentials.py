"""
O.R.I.O.N — Credenciais de provedores (v0.5.0 Sprint 1)

Ordem de precedência de cada chave: variável de ambiente, ``~/.orion/.env`` (0600, criado
vazio na primeira execução) e o arquivo legado ``~/.orion/<nome>_api_key``. Nunca de arquivos
versionados. O PEP nega ao agente ler ou escrever esses arquivos.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

KEY_FILE_NAME = "anthropic_api_key"
OPENROUTER_KEY_FILE_NAME = "openrouter_api_key"
ENV_FILE_NAME = ".env"
ENV_TEMPLATE = """# O.R.I.O.N — variáveis locais (~/.orion/.env, permissão 0600).
# Uma variável por linha, sem aspas. A variável de ambiente do shell, se existir, vence.
# O agente não lê nem altera este arquivo (PEP).

# Chave do OpenRouter (https://openrouter.ai/keys)
OPENROUTER_API_KEY=
"""
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


def read_env_file(home: Path) -> dict[str, str]:
    """Lê ``~/.orion/.env`` (``CHAVE=valor``, comentários e ``export`` aceitos). Ausente: ``{}``."""
    try:
        text = (home / ENV_FILE_NAME).read_text(encoding="utf-8")
    except OSError:
        return {}
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key.strip():
            values[key.strip()] = value
    return values


def ensure_env_file(home: Path) -> Path | None:
    """Cria ``~/.orion/.env`` vazio (modelo comentado, 0600) se ainda não existir."""
    path = home / ENV_FILE_NAME
    if path.exists():
        return path
    try:
        home.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(ENV_TEMPLATE)
    except FileExistsError:
        return path
    except OSError:
        return None
    return path


def env_file_too_open(home: Path) -> bool:
    """True se o ``.env`` é legível por grupo ou outros usuários."""
    try:
        return bool((home / ENV_FILE_NAME).stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))
    except OSError:
        return False


def _from_env_or_dotenv(name: str, home: Path) -> tuple[str | None, str]:
    env = os.environ.get(name, "").strip()
    if env:
        return env, "env"
    value = read_env_file(home).get(name, "").strip()
    if value:
        return value, ".env"
    return None, "ausente"


def load_anthropic_key(home: Path) -> str | None:
    """Retorna a chave (env > ``.env`` > arquivo) ou ``None``."""
    value, _ = _from_env_or_dotenv("ANTHROPIC_API_KEY", home)
    if value:
        return value
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
    _, source = _from_env_or_dotenv("ANTHROPIC_API_KEY", home)
    too_open = False
    if source == ".env":
        too_open = env_file_too_open(home)
    elif source == "ausente":
        source = "file"
        try:
            mode = (home / KEY_FILE_NAME).stat().st_mode
            too_open = bool(mode & (stat.S_IRWXG | stat.S_IRWXO))
        except OSError:
            pass
    return KeyStatus(
        found=True,
        source=source,
        well_formed=key.startswith(_KEY_PREFIX),
        file_too_open=too_open,
    )


def load_openrouter_key(home: Path) -> str | None:
    """Chave do OpenRouter: ``OPENROUTER_API_KEY`` do ambiente, do ``~/.orion/.env`` ou do arquivo
    legado ``~/.orion/openrouter_api_key``, nessa ordem."""
    value, _ = _from_env_or_dotenv("OPENROUTER_API_KEY", home)
    if value:
        return value
    try:
        value = (home / OPENROUTER_KEY_FILE_NAME).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def openrouter_key_status(home: Path) -> tuple[bool, str]:
    """(configurada, detalhe) da chave do OpenRouter, sem expô-la."""
    value, source = _from_env_or_dotenv("OPENROUTER_API_KEY", home)
    if value is None:
        if load_openrouter_key(home):
            return True, f"configurada via ~/.orion/{OPENROUTER_KEY_FILE_NAME}"
        return False, "ausente (preencha OPENROUTER_API_KEY em ~/.orion/.env)"
    detail = f"configurada via {source}"
    if source == ".env" and env_file_too_open(home):
        return False, detail + "; ~/.orion/.env legível por outros: rode chmod 600"
    return True, detail
