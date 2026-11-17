"""
O.R.I.O.N — ``orion setup sudo`` (v0.5.3 Sprint 1, ADR-048)

Opt-in do Senhor, fora do alcance do agente:
  * ``orion setup sudo``              guarda a senha do sudo no chaveiro do SO, depois de o
                                      próprio sudo confirmá-la (senha errada não é guardada);
  * ``orion setup sudo --forget``     apaga do chaveiro e desliga o preenchimento;
  * ``orion setup sudo --sudoers``    gera ``~/.orion/sudoers.orion`` para o Senhor revisar;
  * ``... --sudoers --apply``         valida com ``visudo -c`` e instala em
                                      ``/etc/sudoers.d/orion`` via ``pkexec`` (0440, root).
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from orion.governance.askpass import (
    SUDO_KEYRING_MARKER,
    SUDOERS_TEMPLATE,
    KeyringSudoStore,
    SecretStore,
    verify_sudo_password,
)

SUDOERS_DRAFT = "sudoers.orion"
SUDOERS_TARGET = "/etc/sudoers.d/orion"


@dataclass(frozen=True)
class SetupOutcome:
    code: int
    lines: tuple[str, ...]


Runner = Callable[[list[str]], int]


def _default_runner(argv: list[str]) -> int:
    return subprocess.run(argv, check=False).returncode  # noqa: S603 - argv fixo, ação do Senhor


def remember(
    home: Path,
    *,
    store: SecretStore | None = None,
    read_secret: Callable[[str], str] = getpass.getpass,
    verify: Callable[[str], bool] = verify_sudo_password,
) -> SetupOutcome:
    """Pergunta a senha, deixa o sudo conferir e só então guarda no chaveiro."""
    target = store or KeyringSudoStore()
    if isinstance(target, KeyringSudoStore) and not target.available():
        return SetupOutcome(1, ("✖ chaveiro do sistema (Secret Service) indisponível nesta sessão",))
    secret = read_secret("Senha do sudo (verificada pelo próprio sudo): ")
    if not secret:
        return SetupOutcome(1, ("✖ nada digitado; nada foi guardado",))
    try:
        if not verify(secret):
            return SetupOutcome(1, ("✖ o sudo recusou a senha; nada foi guardado",))
        target.set(secret)
    except Exception as exc:  # noqa: BLE001 - chaveiro trancado, D-Bus fora
        return SetupOutcome(1, (f"✖ não foi possível guardar no chaveiro: {type(exc).__name__}",))
    finally:
        secret = ""
    home.mkdir(parents=True, exist_ok=True)
    marker = home / SUDO_KEYRING_MARKER
    marker.write_text("keyring\n", encoding="utf-8")
    marker.chmod(0o600)
    return SetupOutcome(
        0,
        (
            "✔ senha guardada no chaveiro do sistema (nunca em arquivo do ORION)",
            "● sudo de instalar, atualizar, consultar e reiniciar serviços roda sem perguntar",
            "● ações irreversíveis continuam pedindo a presença do Senhor",
            "● orion setup sudo --forget desfaz",
        ),
    )


def forget(home: Path, *, store: SecretStore | None = None) -> SetupOutcome:
    target = store or KeyringSudoStore()
    try:
        removed = target.delete()
    except Exception as exc:  # noqa: BLE001
        return SetupOutcome(1, (f"✖ não foi possível acessar o chaveiro: {type(exc).__name__}",))
    marker = home / SUDO_KEYRING_MARKER
    had_marker = marker.exists()
    marker.unlink(missing_ok=True)
    if removed or had_marker:
        return SetupOutcome(0, ("✔ senha do sudo apagada do chaveiro; o ORION volta a perguntar",))
    return SetupOutcome(0, ("● não havia senha do sudo guardada",))


def sudoers_draft(home: Path) -> SetupOutcome:
    draft = home / SUDOERS_DRAFT
    if not draft.exists():
        home.mkdir(parents=True, exist_ok=True)
        draft.write_text(SUDOERS_TEMPLATE.format(user=getpass.getuser()), encoding="utf-8")
        draft.chmod(0o600)
    return SetupOutcome(
        0,
        (
            f"● rascunho em {draft}",
            "● revise a lista (um comando exato por linha, nunca ALL) e aplique com:",
            "  orion setup sudo --sudoers --apply",
        ),
    )


def _grants_all(text: str) -> bool:
    """True se alguma regra libera qualquer comando (``ALL``) ou um shell."""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        commands = line.split("=", 1)[1]
        if ")" in commands:
            commands = commands.split(")", 1)[1]
        for part in commands.split(","):
            cmd = part.split(":")[-1].strip()
            program = cmd.split()[0] if cmd else ""
            if cmd == "ALL" or Path(program).name in {"sh", "bash", "zsh", "su", "sudo", "env"}:
                return True
    return False


def sudoers_apply(home: Path, *, runner: Runner = _default_runner) -> SetupOutcome:
    draft = home / SUDOERS_DRAFT
    if not draft.exists():
        return SetupOutcome(1, ("✖ sem rascunho; rode antes orion setup sudo --sudoers",))
    text = draft.read_text(encoding="utf-8")
    if _grants_all(text):
        return SetupOutcome(1, ("✖ o rascunho libera ALL; o ORION não instala isso",))
    visudo = shutil.which("visudo") or "/usr/sbin/visudo"
    if runner([visudo, "-c", "-f", str(draft)]) != 0:
        return SetupOutcome(1, ("✖ visudo recusou o rascunho; corrija e tente de novo",))
    pkexec = shutil.which("pkexec")
    if not pkexec:
        return SetupOutcome(1, ("✖ pkexec não encontrado; instale manualmente com sudo",))
    argv = [pkexec, "install", "-m", "0440", "-o", "root", "-g", "root", str(draft), SUDOERS_TARGET]
    if runner(argv) != 0:
        return SetupOutcome(1, ("✖ instalação cancelada ou negada pelo sistema",))
    return SetupOutcome(0, (f"✔ {SUDOERS_TARGET} instalado (0440, root)",))


def run(home: Path, *, forget_it: bool = False, sudoers: bool = False, apply: bool = False) -> SetupOutcome:
    if forget_it:
        return forget(home)
    if sudoers:
        return sudoers_apply(home) if apply else sudoers_draft(home)
    if not os.isatty(0):
        return SetupOutcome(2, ("! precisa de um terminal interativo para digitar a senha",))
    return remember(home)
