"""
O.R.I.O.N — Nuclear Safety Gate (v0.3.0 Sprint 4)

Detector de Blast Radius e autenticação obrigatória do SO para
operações de alto impacto destrutivo.

Implementa a trava final de segurança do ORION: qualquer comando
classificado como NUCLEAR_DESTRUCTIVE dispara incondicionalmente
um popup de autenticação nativa do sistema operacional, exigindo
a presença física consciente do usuário.

INVARIANTES INVIOLÁVEIS:
─────────────────────────
  1. NUCLEAR_DESTRUCTIVE SEMPRE exige autenticação do SO — em qualquer
     modo de autonomia (incluindo FULLY_AUTO), em qualquer contexto.
  2. Nenhuma flag de configuração, nenhuma sequência de comandos prévia,
     nenhum estado do sistema pode bypassar a autenticação nuclear.
  3. Se a autenticação falhar ou for cancelada, a ação é NEGADA.
  4. O Trust Ledger NUNCA registra comandos NUCLEAR_DESTRUCTIVE.

ESTRATÉGIA DE AUTENTICAÇÃO (v0.5.3, ADR-048):
──────────────────────────────────────────────
  1. polkit (``pkexec``) com display e agente gráfico: o próprio SO verifica.
  2. PAM do usuário com a senha pedida pela interface do ORION (overlay mascarado).
  3. Sem nenhum dos dois: NEGADO. Nunca "qualquer texto vale", nunca /dev/tty cru.

Referências: ADR-018 (Nuclear Threshold), ADR-048 (presença verificada).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enumeração de Blast Radius
# ---------------------------------------------------------------------------


class BlastRadius(StrEnum):
    """Classificação de impacto destrutivo de um comando.

    BENIGN            — Leitura, build, testes, listagem. Sem efeitos colaterais.
    WORKSPACE_MUTATION — Criação/edição dentro do workspace permitido.
    SYSTEM_ELEVATED   — Instalação de pacotes com sudo não-destrutivos.
                        Seguro após 1ª aprovação no Trust Ledger.
    NUCLEAR_DESTRUCTIVE — Destruição irreversível: rm -rf, wipe, mkfs, dd,
                          modificações em /, /etc, ~/.ssh, boot, etc.
                          SEMPRE exige autenticação do SO.
    """

    BENIGN = "benign"
    WORKSPACE_MUTATION = "workspace"
    SYSTEM_ELEVATED = "system"
    NUCLEAR_DESTRUCTIVE = "nuclear"


# ---------------------------------------------------------------------------
# Resultado de Desafio Nuclear
# ---------------------------------------------------------------------------


class NuclearChallengeResult(BaseModel):
    """Resultado de um desafio de autenticação nuclear.

    Attributes:
        authorized: True se o usuário autenticou com sucesso.
        method_used: Método de autenticação usado.
        duration_seconds: Tempo total do desafio em segundos.
        command_pattern: Padrão do comando que disparou o desafio.
        blast_radius: Classificação de impacto do comando.
    """

    model_config = {"frozen": True}

    authorized: bool
    method_used: str
    duration_seconds: float
    command_pattern: str
    blast_radius: BlastRadius


# ---------------------------------------------------------------------------
# Padrões de Detecção Nuclear
# ---------------------------------------------------------------------------

# Padrões de comando que classificam como NUCLEAR_DESTRUCTIVE.
# Ordem importa: os mais específicos e perigosos vêm primeiro.
_NUCLEAR_PATTERNS: list[re.Pattern[str]] = [
    # rm com flags destrutivas
    re.compile(r"\brm\s+.*-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\b", re.IGNORECASE),
    re.compile(r"\brm\s+.*-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*\b", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\brm\s+-fr\b", re.IGNORECASE),
    # Destruição de dispositivos de bloco
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+.*of=/dev/", re.IGNORECASE),
    re.compile(r"\bshred\b", re.IGNORECASE),
    re.compile(r"\bwipe\b", re.IGNORECASE),
    re.compile(r"\bblkdiscard\b", re.IGNORECASE),
    # Modificações em diretórios críticos do sistema
    re.compile(r"\b(rm|mv|chmod|chown|truncate)\s+.*(/etc/|/boot/|/sys/|/proc/)", re.IGNORECASE),
    re.compile(r"\b(rm|mv|chmod|chown|truncate)\s+.*(~|/home/[^/]+)/\.ssh/", re.IGNORECASE),
    re.compile(r"\b(rm|mv|chmod|chown|truncate)\s+.*/\s*$", re.IGNORECASE),
    # Forçar deleção em root ou diretórios críticos
    re.compile(r"\brm\s+.*(/\s*$|/\*)", re.IGNORECASE),
    re.compile(r"\brm\s+-[rf]+\s+/\b", re.IGNORECASE),
    # Comandos de limpeza total
    re.compile(r"\bgit\s+clean\s+.*-f\b.*-d\b", re.IGNORECASE),
    re.compile(r"\bgit\s+clean\s+.*-fd\b", re.IGNORECASE),
    # Truncar arquivos do sistema
    re.compile(r">\s+(/etc/|/boot/)", re.IGNORECASE),
    # sudo com comandos destrutivos
    re.compile(r"\bsudo\s+(rm|mkfs|dd|shred|wipe)\b", re.IGNORECASE),
    # O agente trocando o próprio código instalado (ADR-044)
    re.compile(r"\borion(-agent)?\s+update\b", re.IGNORECASE),
    re.compile(r"\bpython[\d.]*\s+-m\s+orion\.install\b", re.IGNORECASE),
    # poweroff/reboot destrutivo (não-gracioso)
    re.compile(r"\b(poweroff|halt|shutdown\s+-h\s+now|reboot\s+--force)\b", re.IGNORECASE),
]

# Padrões de SYSTEM_ELEVATED (sudo não-destrutivos)
_ELEVATED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bsudo\s+(apt|apt-get|yum|dnf|pacman|brew)\s+(install|update|upgrade)\b", re.IGNORECASE),
    re.compile(r"\bsudo\s+(systemctl|service)\s+(start|stop|restart|enable|disable)\b", re.IGNORECASE),
    re.compile(r"\bsudo\s+(chmod|chown)\s+", re.IGNORECASE),
    re.compile(r"\bsudo\b", re.IGNORECASE),  # Qualquer sudo não capturado acima
]

# Padrões de WORKSPACE_MUTATION (escrita em workspace)
_MUTATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bmkdir\b", re.IGNORECASE),
    re.compile(r"\btouch\b", re.IGNORECASE),
    re.compile(r"\bmv\b", re.IGNORECASE),
    re.compile(r"\bcp\b", re.IGNORECASE),
    re.compile(r"\brm\b", re.IGNORECASE),  # rm simples, sem flags -rf
]


# ---------------------------------------------------------------------------
# Classificador de Blast Radius
# ---------------------------------------------------------------------------


class BlastRadiusClassifier:
    """Classifica o Blast Radius de um comando shell.

    Exemplo de uso:
        >>> clf = BlastRadiusClassifier()
        >>> clf.classify("rm -rf /tmp/cache")
        BlastRadius.NUCLEAR_DESTRUCTIVE
        >>> clf.classify("git status")
        BlastRadius.BENIGN
        >>> clf.classify("sudo apt install htop")
        BlastRadius.SYSTEM_ELEVATED
    """

    @classmethod
    def classify(cls, command: str) -> BlastRadius:
        """Classifica o impacto destrutivo de um comando.

        Args:
            command: Comando shell a classificar.

        Returns:
            ``BlastRadius`` correspondente ao nível de risco.
        """
        cmd = command.strip()

        # Verificar padrões nucleares (mais perigosos primeiro)
        for pattern in _NUCLEAR_PATTERNS:
            if pattern.search(cmd):
                logger.warning(
                    "NuclearGate: padrão NUCLEAR detectado — '%s'",
                    cmd[:100],
                )
                return BlastRadius.NUCLEAR_DESTRUCTIVE

        # Verificar padrões elevados (sudo não-destrutivos)
        for pattern in _ELEVATED_PATTERNS:
            if pattern.search(cmd):
                return BlastRadius.SYSTEM_ELEVATED

        # Verificar padrões de mutação de workspace
        for pattern in _MUTATION_PATTERNS:
            if pattern.search(cmd):
                return BlastRadius.WORKSPACE_MUTATION

        return BlastRadius.BENIGN

    @classmethod
    def is_nuclear(cls, command: str) -> bool:
        """Atalho: retorna True se o comando é NUCLEAR_DESTRUCTIVE."""
        return cls.classify(command) == BlastRadius.NUCLEAR_DESTRUCTIVE


# ---------------------------------------------------------------------------
# Nuclear Safety Gate
# ---------------------------------------------------------------------------


class NuclearSafetyGate:
    """Trava de segurança nuclear com presença VERIFICADA do Senhor (ADR-018, emenda ADR-048).

    Ordem: polkit (``pkexec``, diálogo nativo; a senha nunca passa pelo ORION) quando há display e
    agente polkit; senão PAM do próprio usuário (``python-pam`` → ``unix_chkpwd``) com a senha
    pedida pelo *prompter* da interface (overlay mascarado na tela cheia). Leitor de digital
    entra pelo próprio PAM quando ``pam_fprintd`` está no serviço. Senha errada nega.

    INVARIANTE: não há configuração, modo ou flag que permita bypassar esta classe para comandos
    nucleares. "Qualquer texto vale" e a leitura crua de ``/dev/tty`` foram removidos (G-01, G-03).
    """

    def __init__(
        self,
        classifier: BlastRadiusClassifier | None = None,
        prompt_prefix: str = "[PEP] O.R.I.O.N Nuclear Safety Gate",
        *,
        prompter: Any = None,
        authenticator: Callable[[str, str], bool] | None = None,
        pam_service: str | None = None,
        notifier: Callable[[str], None] | None = None,
    ) -> None:
        """Inicializa o Nuclear Safety Gate.

        Args:
            classifier: Classificador de Blast Radius. Usa padrão se None.
            prompt_prefix: Prefixo das mensagens ao Senhor.
            prompter: ``SecretPrompter`` (async) da interface; sem ele não há caminho PAM.
            authenticator: ``(usuário, senha) -> bool``; padrão: PAM do sistema.
            pam_service: serviço PAM (padrão: ``orion`` se existir, senão ``login``).
            notifier: mostra ao Senhor que um diálogo do sistema foi aberto.
        """
        self._classifier = classifier or BlastRadiusClassifier()
        self._prompt_prefix = prompt_prefix
        self._prompter = prompter
        self._authenticator = authenticator
        self._pam_service = pam_service
        self._notifier = notifier

    def set_prompter(self, prompter: Any) -> None:
        self._prompter = prompter

    def set_notifier(self, notifier: Callable[[str], None] | None) -> None:
        self._notifier = notifier

    def classify(self, command: str) -> BlastRadius:
        """Classifica o Blast Radius de um comando."""
        return self._classifier.classify(command)

    def requires_nuclear_auth(self, command: str) -> bool:
        """True se o comando é NUCLEAR_DESTRUCTIVE."""
        return self._classifier.is_nuclear(command)

    def _passthrough(self, command: str, blast: BlastRadius) -> NuclearChallengeResult:
        return NuclearChallengeResult(
            authorized=True,
            method_used="no_auth_required",
            duration_seconds=0.0,
            command_pattern=command[:80],
            blast_radius=blast,
        )

    def challenge(self, command: str) -> NuclearChallengeResult:
        """Versão síncrona (fora de um loop asyncio). O PEP usa :meth:`challenge_async`."""
        blast = self._classifier.classify(command)
        if blast != BlastRadius.NUCLEAR_DESTRUCTIVE:
            return self._passthrough(command, blast)
        logger.warning("NuclearGate: DESAFIO NUCLEAR disparado para: '%s'", command[:100])
        return self._run_challenge(command, blast)

    async def challenge_async(self, command: str) -> NuclearChallengeResult:
        """Dispara o desafio se *command* é nuclear; senão passa direto."""
        blast = self._classifier.classify(command)
        if blast != BlastRadius.NUCLEAR_DESTRUCTIVE:
            return self._passthrough(command, blast)
        logger.warning("NuclearGate: DESAFIO NUCLEAR disparado para: '%s'", command[:100])
        return await self._run_challenge_async(command, blast)

    def assert_authorized(self, command: str) -> NuclearChallengeResult:
        """Verifica autorização e lança :class:`NuclearAuthDenied` se negada."""
        result = self.challenge(command)
        if not result.authorized:
            raise NuclearAuthDenied(
                command=command,
                blast_radius=result.blast_radius,
                method_used=result.method_used,
            )
        return result

    # ── Autenticação interna ──────────────────────────────────────────────────

    def _run_challenge(self, command: str, blast: BlastRadius) -> NuclearChallengeResult:
        """Desafio síncrono: só para chamadores fora de um loop (scripts, testes)."""
        import asyncio

        return asyncio.run(self._run_challenge_async(command, blast))

    async def _run_challenge_async(self, command: str, blast: BlastRadius) -> NuclearChallengeResult:
        t0 = time.monotonic()
        short_cmd = command[:80] + ("..." if len(command) > 80 else "")
        method, success = await self._try_polkit(short_cmd)
        if method == "skipped":
            method, success = await self._try_pam(command)
        return NuclearChallengeResult(
            authorized=success,
            method_used=method,
            duration_seconds=time.monotonic() - t0,
            command_pattern=short_cmd,
            blast_radius=blast,
        )

    def _has_display(self) -> bool:
        """Verifica se há um display gráfico disponível."""
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    async def _try_polkit(self, short_cmd: str) -> tuple[str, bool]:
        """``pkexec --disable-internal-agent /bin/true``: o diálogo do GNOME verifica a senha.

        Sem display, sem ``pkexec`` ou sem agente polkit: ``("skipped", False)`` e o PAM assume.
        Nunca usa o agente de texto do pkexec (disputaria o terminal com a tela cheia).
        """
        import asyncio

        pkexec = shutil.which("pkexec")
        if not self._has_display() or not pkexec:
            return ("skipped", False)
        if self._notifier is not None:
            self._notifier(f"{self._prompt_prefix}: confirme no diálogo do sistema para executar: {short_cmd}")
        try:
            proc = await asyncio.create_subprocess_exec(
                pkexec, "--disable-internal-agent", "/bin/true",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            _out, err = await asyncio.wait_for(proc.communicate(), timeout=120)
        except (TimeoutError, OSError) as exc:
            logger.warning("NuclearGate: polkit indisponível — %s", exc)
            return ("skipped", False)
        if proc.returncode == 0:
            logger.info("NuclearGate: presença verificada via polkit.")
            return ("polkit", True)
        text = (err or b"").decode("utf-8", errors="replace").lower()
        if proc.returncode == 127 and ("agent" in text or "agente" in text):
            return ("skipped", False)  # sem agente gráfico: cai para o PAM
        logger.warning("NuclearGate: polkit negou ou foi cancelado (rc=%s).", proc.returncode)
        return ("polkit", False)

    def _service(self) -> str:
        if self._pam_service:
            return self._pam_service
        return "orion" if os.path.exists("/etc/pam.d/orion") else "login"

    def _pam_authenticate(self, user: str, secret: str) -> bool:
        if self._authenticator is not None:
            return bool(self._authenticator(user, secret))
        try:
            import pam
        except ImportError:
            logger.error("NuclearGate: python-pam ausente; presença não pode ser verificada.")
            return False
        return bool(pam.pam().authenticate(user, secret, service=self._service(), resetcreds=False))

    async def _try_pam(self, command: str) -> tuple[str, bool]:
        """Senha do Senhor pelo prompter da interface, verificada pelo PAM (sem root)."""
        import asyncio
        import getpass

        from orion.governance.askpass import SecretRequest

        if self._prompter is None:
            logger.warning("NuclearGate: sem polkit e sem interface para pedir a senha — negado.")
            return ("unavailable", False)
        request = SecretRequest(
            "nuclear",
            command,
            f"{self._prompt_prefix}: ação IRREVERSÍVEL. Senha do Senhor para executar",
        )
        secret = await self._prompter(request)
        if not secret:
            logger.warning("NuclearGate: desafio cancelado pelo Senhor.")
            return ("pam", False)
        try:
            ok = await asyncio.to_thread(self._pam_authenticate, getpass.getuser(), secret)
        finally:
            secret = None
        if ok:
            logger.info("NuclearGate: presença verificada via PAM.")
        else:
            logger.warning("NuclearGate: senha recusada pelo PAM.")
        return ("pam", ok)


# ---------------------------------------------------------------------------
# Exceção de Negação Nuclear
# ---------------------------------------------------------------------------


class NuclearAuthDenied(Exception):
    """Levantada quando a autenticação nuclear foi negada ou cancelada.

    Attributes:
        command: Comando que foi negado.
        blast_radius: Classificação de impacto do comando.
        method_used: Método de autenticação tentado.
    """

    def __init__(
        self,
        command: str,
        blast_radius: BlastRadius,
        method_used: str,
    ) -> None:
        self.command = command
        self.blast_radius = blast_radius
        self.method_used = method_used
        super().__init__(
            f"[PEP] ORION Nuclear Safety Gate: operação NEGADA.\n"
            f"   Comando: {command[:80]}\n"
            f"   Risco: {blast_radius.value}\n"
            f"   Método: {method_used}\n"
            f"   A ação foi cancelada ou a autenticação falhou."
        )
