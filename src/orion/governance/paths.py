"""Zonas de caminho da governança (ADR-046): segredo, governança, sensível, sistema, escopo.

Funções puras sobre caminhos (só resolvem symlinks). Vivem fora do ``pep.py`` para que o
classificador de faixas (``bands.py``) e o PEP compartilhem a mesma fonte de verdade.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

# Estado de governança do próprio ORION: nenhuma tool de escrita do agente o altera
# (o agente não pode ampliar a própria allowlist, orçamento, segredos ou trilha de auditoria).
PROTECTED_NAMES = frozenset(
    {
        "web_allowlist.json", "settings.json", "config.json", "blacklist.json", "users.json",
        "token_budget.json", "anthropic_api_key", "openrouter_api_key", "permissions.json",
        ".env", "web_blocklist.json", "command_trust.db",
    }
)
# Segredos: o agente também não os LÊ (o conteúdo iria para o provedor).
SECRET_NAMES = frozenset({".env", "anthropic_api_key", "openrouter_api_key"})
_PROTECTED_PREFIXES = ("audit.", "trust")
_PROTECTED_DIRS = frozenset({"secrets"})

#: Caminhos do Senhor que mudam login, chaves ou o que roda sozinho (ADR-046).
SENSITIVE_HOME = (
    ".ssh", ".gnupg", ".config/systemd", ".config/autostart", ".local/share/keyrings",
    ".bashrc", ".zshrc", ".profile", ".bash_profile", ".zprofile", ".zshenv", ".bash_login",
    ".bash_logout", ".xprofile", ".xinitrc", ".pam_environment", ".netrc", ".pgpass",
    ".config/git/credentials", ".git-credentials", ".docker/config.json", ".kube/config",
    ".aws/credentials",
)
#: Dentro dos sensíveis, os que guardam chaves: escrever ou apagar é Nuclear, não Presença.
KEY_HOME = (".ssh", ".gnupg", ".local/share/keyrings")

#: Árvores do sistema: escrever ou apagar ali é Nuclear (fora do espaço do usuário).
SYSTEM_ROOTS = (
    "/etc", "/boot", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/var",
    "/opt", "/sys", "/proc", "/dev", "/root", "/srv", "/snap",
)


class Zone(StrEnum):
    """Onde um caminho cai, do mais protegido ao mais livre."""

    SECRET = "secret"  # segredos do ORION: nem leitura
    GOVERNANCE = "governance"  # estado de governança do ORION: nunca escrito pelo agente
    KEYS = "keys"  # ~/.ssh, ~/.gnupg, chaveiro: Nuclear
    SYSTEM = "system"  # /etc, /usr, raiz...: Nuclear
    SENSITIVE = "sensitive"  # rc do shell, autostart, credenciais: Presença
    SCOPE = "scope"  # espaço do usuário, não sensível: Livre
    OUTSIDE = "outside"  # fora do espaço do usuário mas não do sistema (ex.: /tmp): Classificada


def _relative(path: str | Path, root: Path) -> tuple[str, ...] | None:
    try:
        target = Path(path).expanduser().resolve()
        return target.relative_to(root.resolve()).parts
    except (ValueError, OSError, RuntimeError):
        return None


def is_secret_path(path: str, home: Path | None = None) -> bool:
    """True se ler *path* exporia um segredo de ``~/.orion`` (arquivo, ``secrets/`` ou a raiz)."""
    parts = _relative(path, home or Path.home() / ".orion")
    if parts is None:
        return False
    return not parts or parts[0] == "secrets" or parts[-1] in SECRET_NAMES


def is_protected_state_path(path: str, home: Path | None = None) -> bool:
    """True se *path* aponta para um arquivo de governança dentro de ``~/.orion``."""
    parts = _relative(path, home or Path.home() / ".orion")
    if not parts:
        return False
    return (
        parts[0] in _PROTECTED_DIRS
        or parts[-1] in PROTECTED_NAMES
        or any(parts[-1].startswith(p) for p in _PROTECTED_PREFIXES)
    )


def _under_home_entry(path: str | Path, entries: tuple[str, ...], home: Path | None) -> bool:
    parts = _relative(path, home or Path.home())
    if parts is None:
        return False
    text = "/".join(parts)
    return any(text == entry or text.startswith(entry + "/") for entry in entries)


def is_sensitive_path(path: str, home: Path | None = None) -> bool:
    """True se escrever em *path* altera login, chaves, credenciais ou autostart do Senhor."""
    return _under_home_entry(path, SENSITIVE_HOME, home)


def is_key_path(path: str | Path, home: Path | None = None) -> bool:
    """True se *path* está em ``~/.ssh``, ``~/.gnupg`` ou no chaveiro do usuário."""
    return _under_home_entry(path, KEY_HOME, home)


def is_system_path(path: str | Path) -> bool:
    """True se *path* (resolvido) é a raiz ou está numa árvore do sistema."""
    try:
        target = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return True
    text = target.as_posix()
    if text == "/":
        return True
    return any(text == root or text.startswith(root + "/") for root in SYSTEM_ROOTS)


def zone_of(
    path: str | Path,
    *,
    in_scope: bool,
    home: Path | None = None,
    orion_home: Path | None = None,
) -> Zone:
    """Zona de *path*; *in_scope* diz se o escopo do usuário o cobre."""
    raw = str(path)
    if is_secret_path(raw, orion_home):
        return Zone.SECRET
    if is_protected_state_path(raw, orion_home):
        return Zone.GOVERNANCE
    if is_key_path(raw, home):
        return Zone.KEYS
    if in_scope and is_sensitive_path(raw, home):
        return Zone.SENSITIVE
    if in_scope:
        return Zone.SCOPE
    if is_system_path(raw):
        return Zone.SYSTEM
    return Zone.OUTSIDE
