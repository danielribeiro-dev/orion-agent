"""
O.R.I.O.N — Presença verificada para o sudo (v0.5.3 Sprint 1, ADR-048)

O ``run_command`` roda sem terminal, então o ``sudo`` não tinha por onde pedir senha (G-02).
Agora ele roda como ``sudo -A`` com ``SUDO_ASKPASS`` apontando para ``orion.askpass``, que pede a
senha a este broker por um socket Unix efêmero (diretório 0700, socket 0600, token de uso único).
Quem verifica a senha é o próprio sudo.

Invariantes:
  1. A senha nunca passa pelo engine, pelo transcript, pela auditoria nem pelos logs.
  2. O broker só responde a um processo do mesmo usuário cujo pai é o ``sudo`` (SO_PEERCRED):
     um script dentro do comando não consegue pedir a senha guardada.
  3. A senha do chaveiro (opt-in, ``orion setup sudo``) só é preenchida sozinha na primeira
     tentativa e só para comandos ``sudo`` que :func:`is_sudo_safe` aprova; nunca para Nuclear.
  4. Sem quem pergunte (daemon, subagent), o pedido é recusado: o sudo falha como no terminal.
"""

from __future__ import annotations

import asyncio
import contextlib
import getpass
import hmac
import json
import logging
import os
import re
import secrets
import shlex
import socket
import struct
import sys
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
SOCKET_PATH_LIMIT = 104
KEYRING_LABEL = "O.R.I.O.N · senha do sudo"
KEYRING_SCHEMA = "orion.sudo"
#: Marca em ``~/.orion`` de que o Senhor optou pelo chaveiro (só a marca; a senha fica no SO).
SUDO_KEYRING_MARKER = "sudo_keyring"

# ---------------------------------------------------------------------------
# Pedido de segredo (sudo ou presença nuclear) e quem pergunta ao Senhor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecretRequest:
    """O que a interface mostra ao pedir uma senha. Nunca carrega a senha."""

    purpose: Literal["sudo", "nuclear"]
    command: str
    prompt: str
    attempt: int = 1

    @property
    def title(self) -> str:
        if self.purpose == "nuclear":
            return "Ação irreversível: confirme com a senha do Senhor"
        retry = f" (tentativa {self.attempt} de {MAX_ATTEMPTS})" if self.attempt > 1 else ""
        return f"Senha do sudo{retry}"


#: Pergunta a senha ao Senhor (overlay mascarado, prompt sem eco ou popup). None = cancelado.
SecretPrompter = Callable[[SecretRequest], Awaitable[str | None]]


class SecretStore(Protocol):
    """Onde a senha do sudo pode ficar guardada (opt-in). Nunca em arquivo do ORION."""

    def get(self) -> str | None: ...

    def set(self, secret: str) -> None: ...

    def delete(self) -> bool: ...


class KeyringSudoStore:
    """Chaveiro do SO (Secret Service: GNOME Keyring, KWallet) via ``secretstorage``.

    Coleção trancada não é destrancada aqui (isso abriria um diálogo inesperado): ``get``
    devolve None e o broker pergunta ao Senhor.
    """

    def __init__(self, user: str | None = None) -> None:
        self._user = user or getpass.getuser()

    @property
    def attributes(self) -> dict[str, str]:
        return {"xdg:schema": KEYRING_SCHEMA, "orion": "sudo", "user": self._user}

    def _collection(self, unlock: bool = False) -> Any:
        import secretstorage

        conn = secretstorage.dbus_init()
        collection = secretstorage.get_default_collection(conn)
        if collection.is_locked():
            if not unlock:
                return None
            collection.unlock()
            if collection.is_locked():
                return None
        return collection

    def available(self) -> bool:
        try:
            import secretstorage

            conn = secretstorage.dbus_init()
            return bool(secretstorage.check_service_availability(conn))
        except Exception:  # noqa: BLE001 - sem D-Bus/Secret Service
            return False

    def get(self) -> str | None:
        try:
            collection = self._collection()
            if collection is None:
                return None
            for item in collection.search_items(self.attributes):
                return str(item.get_secret().decode("utf-8"))
        except Exception:  # noqa: BLE001 - chaveiro indisponível: pergunta ao Senhor
            logger.info("askpass: chaveiro indisponível")
        return None

    def set(self, secret: str) -> None:
        collection = self._collection(unlock=True)
        if collection is None:
            raise RuntimeError("o chaveiro do sistema está trancado")
        collection.create_item(KEYRING_LABEL, self.attributes, secret.encode("utf-8"), replace=True)

    def delete(self) -> bool:
        collection = self._collection(unlock=True)
        if collection is None:
            return False
        removed = False
        for item in collection.search_items(self.attributes):
            item.delete()
            removed = True
        return removed

    def has_secret(self) -> bool:
        """True se há senha guardada (sem lê-la)."""
        try:
            collection = self._collection()
            return collection is not None and any(True for _ in collection.search_items(self.attributes))
        except Exception:  # noqa: BLE001
            return False


# ---------------------------------------------------------------------------
# Regras determinísticas (Sprint 1; o classificador da Sprint 2 as complementa)
# ---------------------------------------------------------------------------

_SUDO_TOKEN = re.compile(
    r"(?P<pre>^|[\s;&|(`])sudo(?=\s)(?!\s+(?:-[A-Za-z]*[ASn][A-Za-z]*\b|--(?:askpass|stdin|non-interactive)\b))"
)
_HAS_SUDO = re.compile(r"(?:^|[\s;&|(`])sudo(?:\s|$)")
_COMPOUND = re.compile(r"[;&|<>`\n]|\$\(")
#: Opções do sudo que trocam de usuário, abrem shell ou editam arquivos: nunca autopreenchidas.
_UNSAFE_SUDO_OPTS = frozenset(
    {"-u", "-g", "-s", "-i", "-e", "-E", "--user", "--group", "--shell", "--login", "--edit",
     "--preserve-env", "-D", "--chdir", "-R", "--chroot", "-h", "--host"}
)
#: Programas (e subcomandos) que o chaveiro pode autorizar sem perguntar: instalar, atualizar,
#: consultar e reiniciar serviços. Nada que apague dados, mude usuários ou leia segredos.
_SAFE_PROGRAMS: dict[str, frozenset[str] | None] = {
    "apt": frozenset({"update", "upgrade", "install", "list", "search", "show", "policy"}),
    "apt-get": frozenset({"update", "upgrade", "install", "check"}),
    "dnf": frozenset({"install", "update", "upgrade", "check-update", "list", "search", "info", "makecache"}),
    "yum": frozenset({"install", "update", "check-update", "list", "search", "info", "makecache"}),
    "snap": frozenset({"install", "refresh", "list", "info"}),
    "flatpak": frozenset({"install", "update", "list", "info"}),
    "systemctl": frozenset({"status", "start", "restart", "reload", "daemon-reload", "is-active",
                            "is-enabled", "list-units", "list-timers"}),
    "docker": frozenset({"ps", "images", "logs", "inspect", "start", "restart", "stats", "info", "version"}),
    "journalctl": None,
    "dmesg": None,
    "lsblk": None,
    "blkid": None,
    "lshw": None,
    "dmidecode": None,
    "lsof": None,
    "ss": None,
    "netstat": None,
    "nvidia-smi": None,
    "iotop": None,
    "ufw": frozenset({"status"}),
    "updatedb": None,
    "ldconfig": None,
    "fwupdmgr": frozenset({"get-devices", "get-updates", "refresh"}),
}


def uses_sudo(command: str) -> bool:
    return bool(_HAS_SUDO.search(command))


def rewrite_sudo(command: str) -> str:
    """``sudo x`` → ``sudo -A x`` (pede a senha pelo askpass); quem já passa -A/-S/-n fica."""
    return _SUDO_TOKEN.sub(lambda m: f"{m.group('pre')}sudo -A", command)


def is_sudo_safe(command: str) -> bool:
    """True se o chaveiro pode autorizar *command* sem perguntar ao Senhor (ADR-048 item 2).

    Só um ``sudo`` simples (sem encadear, redirecionar ou substituir), sem trocar de usuário ou
    abrir shell, com programa e subcomando da lista acima, e nunca Nuclear.
    """
    from orion.governance.nuclear import BlastRadius, BlastRadiusClassifier

    text = command.strip()
    if not text or _COMPOUND.search(text):
        return False
    if BlastRadiusClassifier.classify(text) == BlastRadius.NUCLEAR_DESTRUCTIVE:
        return False
    try:
        tokens = shlex.split(text)
    except ValueError:
        return False
    if not tokens or tokens[0] != "sudo":
        return False
    i = 1
    while i < len(tokens) and tokens[i].startswith("-"):
        opt = tokens[i].split("=", 1)[0]
        if opt in _UNSAFE_SUDO_OPTS or opt == "--":
            return False
        if opt not in {"-A", "--askpass", "-n", "--non-interactive", "-k", "-S", "--stdin"}:
            return False
        i += 1
    if i >= len(tokens):
        return False
    program = Path(tokens[i]).name
    if program not in _SAFE_PROGRAMS:
        return False
    allowed = _SAFE_PROGRAMS[program]
    if allowed is None:
        return True
    sub = next((t for t in tokens[i + 1:] if not t.startswith("-")), "")
    return sub in allowed


# ---------------------------------------------------------------------------
# Quem está pedindo a senha (SO_PEERCRED)
# ---------------------------------------------------------------------------


def peer_credentials(sock: Any) -> tuple[int, int, int]:
    """(pid, uid, gid) do processo do outro lado do socket Unix."""
    raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    pid, uid, gid = struct.unpack("3i", raw)
    return pid, uid, gid


def is_sudo_peer(pid: int) -> bool:
    """True se *pid* é o helper do ORION chamado pelo ``sudo`` (sudo clássico ou sudo-rs)."""
    try:
        import psutil

        proc = psutil.Process(pid)
        parent = proc.parent()
        if parent is None:
            return False
        # sudo é setuid root: /proc/<pid>/exe não é legível; o nome (comm) é.
        if parent.name() not in {"sudo", "sudo-rs"} or parent.uids().real != os.getuid():
            return False
        return any("orion.askpass" in part for part in proc.cmdline())
    except Exception:  # noqa: BLE001 - processo sumiu ou sem permissão: recusa
        return False


# ---------------------------------------------------------------------------
# Broker
# ---------------------------------------------------------------------------


@dataclass
class AskpassReport:
    """O que aconteceu num comando com sudo (para metadados e auditoria; sem segredo)."""

    requests: int = 0
    sources: list[str] = field(default_factory=list)  # keyring | prompt | cancelled | refused
    keyring_rejected: bool = False

    def summary(self) -> str:
        return ",".join(self.sources) if self.sources else "none"


def runtime_dir() -> Path:
    """``$XDG_RUNTIME_DIR/orion`` (0700); sem ele, ``/tmp/orion-<uid>`` conferido."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    root = Path(base) / "orion" if base else Path(tempfile.gettempdir()) / f"orion-{os.getuid()}"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    if info.st_uid != os.getuid():
        raise PermissionError(f"{root} pertence a outro usuário; askpass recusado")
    if info.st_mode & 0o077:
        root.chmod(0o700)
    return root


def _helper_script(directory: Path) -> Path:
    """Script que o sudo executa: o Python desta instalação rodando ``orion.askpass``."""
    import orion

    package_root = Path(orion.__file__).resolve().parent.parent
    body = (
        "#!/bin/sh\n"
        f"PYTHONPATH={shlex.quote(str(package_root))}${{PYTHONPATH:+:$PYTHONPATH}}\n"
        "export PYTHONPATH\n"
        f"exec {shlex.quote(sys.executable)} -m orion.askpass \"$@\"\n"
    )
    path = directory / "askpass"
    try:
        current = path.read_text(encoding="utf-8")
    except OSError:
        current = ""
    if current != body:
        tmp = directory / f".askpass-{secrets.token_hex(4)}"
        tmp.write_text(body, encoding="utf-8")
        tmp.chmod(0o700)
        tmp.replace(path)
    return path


class AskpassBroker:
    """Atende os pedidos de senha do ``sudo -A`` de um comando, dentro de :meth:`session`."""

    def __init__(
        self,
        *,
        prompter: SecretPrompter | None = None,
        store: SecretStore | None = None,
        peer_check: Callable[[int], bool] | None = None,
        directory: Path | None = None,
    ) -> None:
        self._prompter = prompter
        self._store = store
        self._peer_check = peer_check or is_sudo_peer
        self._directory = directory

    def set_prompter(self, prompter: SecretPrompter | None) -> None:
        self._prompter = prompter

    def set_store(self, store: SecretStore | None) -> None:
        self._store = store

    @property
    def has_store(self) -> bool:
        return self._store is not None

    def _socket_path(self) -> Path:
        directory = self._directory or runtime_dir()
        path = directory / f"askpass-{os.getpid()}-{secrets.token_hex(4)}.sock"
        if len(str(path)) >= SOCKET_PATH_LIMIT:
            fallback = Path(tempfile.gettempdir()) / f"orion-{os.getuid()}"
            fallback.mkdir(mode=0o700, exist_ok=True)
            path = fallback / f"ap-{secrets.token_hex(4)}.sock"
        return path

    @contextlib.asynccontextmanager
    async def session(self, command: str) -> AsyncIterator[tuple[dict[str, str], AskpassReport]]:
        """Abre o socket para *command*; devolve as variáveis de ambiente e o relatório."""
        sock_path = self._socket_path()
        helper = _helper_script(sock_path.parent)
        token = secrets.token_urlsafe(24)
        report = AskpassReport()
        safe = is_sudo_safe(command)

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            secret: str | None = None
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=10)
                request = json.loads(line.decode("utf-8") or "{}")
                given = str(request.get("token", "")) if isinstance(request, dict) else ""
                if not hmac.compare_digest(given.encode(), token.encode()):
                    report.sources.append("refused")
                    return
                pid, uid, _gid = peer_credentials(writer.get_extra_info("socket"))
                if uid != os.getuid() or not self._peer_check(pid):
                    logger.warning("askpass: pedido de um processo que não é o sudo (pid %s)", pid)
                    report.sources.append("refused")
                    return
                report.requests += 1
                if report.requests > MAX_ATTEMPTS:
                    report.sources.append("refused")
                    return
                if report.requests > 1 and "keyring" in report.sources:
                    report.keyring_rejected = True
                if report.requests == 1 and safe and self._store is not None:
                    secret = await asyncio.to_thread(self._store.get)
                    if secret:
                        report.sources.append("keyring")
                if not secret and self._prompter is not None:
                    secret = await self._prompter(
                        SecretRequest("sudo", command, str(request.get("prompt", ""))[:200], report.requests)
                    )
                    report.sources.append("prompt" if secret else "cancelled")
                elif not secret:
                    report.sources.append("refused")
                if secret:
                    writer.write(json.dumps({"secret": secret}).encode() + b"\n")
                    await writer.drain()
            except Exception:  # noqa: BLE001 - qualquer falha recusa, nunca vaza a senha
                logger.warning("askpass: pedido recusado por erro interno", exc_info=False)
                report.sources.append("refused")
            finally:
                secret = None
                with contextlib.suppress(Exception):
                    writer.close()

        server = await asyncio.start_unix_server(handle, path=str(sock_path))
        try:
            os.chmod(sock_path, 0o600)
            env = {
                "SUDO_ASKPASS": str(helper),
                "ORION_ASKPASS_SOCK": str(sock_path),
                "ORION_ASKPASS_TOKEN": token,
            }
            yield env, report
        finally:
            server.close()
            with contextlib.suppress(Exception):
                await server.wait_closed()
            with contextlib.suppress(OSError):
                sock_path.unlink()


# ---------------------------------------------------------------------------
# ``orion setup sudo`` (verificação pelo próprio sudo, sem guardar nada se errar)
# ---------------------------------------------------------------------------


def verify_sudo_password(secret: str, runner: Callable[[list[str], str], int] | None = None) -> bool:
    """Confere a senha com ``sudo -k -S -v`` (o próprio sudo decide). Nada é gravado aqui."""
    import subprocess

    def default(argv: list[str], data: str) -> int:
        proc = subprocess.run(  # noqa: S603 - argv fixo
            argv,
            input=data,
            text=True,
            capture_output=True,
            timeout=30,
            start_new_session=True,
            check=False,
        )
        return proc.returncode

    run = runner or default
    return run(["sudo", "-k", "-S", "-p", "", "-v"], secret + "\n") == 0


SUDOERS_TEMPLATE = """# O.R.I.O.N — sudo sem senha para uma lista curta revisada pelo Senhor (ADR-048).
# Edite este rascunho e aplique com: orion setup sudo --sudoers --apply
# Cada linha libera UM comando exato (caminho absoluto). Nunca use ALL aqui.
{user} ALL=(root) NOPASSWD: /usr/bin/apt update
{user} ALL=(root) NOPASSWD: /usr/bin/apt upgrade -y
# {user} ALL=(root) NOPASSWD: /usr/bin/systemctl restart docker
"""
