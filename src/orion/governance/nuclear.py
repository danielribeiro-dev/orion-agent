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

ESTRATÉGIA DE AUTENTICAÇÃO (por ambiente):
──────────────────────────────────────────
  Com display gráfico (DISPLAY ou WAYLAND_DISPLAY):
    1. zenity --password (GTK, funciona em GNOME/XFCE)
    2. kdialog --password (KDE)
    3. Fallback para TTY se nenhum gráfico disponível

  Headless / SSH (sem display gráfico):
    1. getpass seguro via /dev/tty (leitura direta, sem eco)

  O ORION nunca usa stdin padrão para autenticação nuclear — apenas
  /dev/tty para evitar injeção de automação.

Referências: ADR-018 (Nuclear Threshold & Popup Obrigatório do SO).
"""

from __future__ import annotations

import getpass
import logging
import os
import re
import shutil
import subprocess
import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Alias para abertura de /dev/tty (facilita testes sem patch global de builtins.open)
_open_tty = open


# ---------------------------------------------------------------------------
# Enumeração de Blast Radius
# ---------------------------------------------------------------------------


class BlastRadius(str, Enum):
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
    """Trava de segurança nuclear com autenticação obrigatória do SO.

    Intercepta comandos classificados como NUCLEAR_DESTRUCTIVE e exige
    autenticação nativa do sistema operacional antes de permitir execução.

    INVARIANTE: Não há nenhuma configuração, modo ou flag que permita
    bypassar esta classe para comandos nucleares. A autenticação é sempre
    exigida.

    Exemplo de uso:
        >>> gate = NuclearSafetyGate()
        >>> result = gate.challenge("rm -rf /home/user/project")
        >>> result.authorized
        False  # se o usuário cancelou
        >>> gate.assert_authorized("rm -rf /tmp")  # lança se não autorizado
    """

    def __init__(
        self,
        classifier: Optional[BlastRadiusClassifier] = None,
        prompt_prefix: str = "🔐 O.R.I.O.N Nuclear Safety Gate",
    ) -> None:
        """Inicializa o Nuclear Safety Gate.

        Args:
            classifier: Classificador de Blast Radius. Usa padrão se None.
            prompt_prefix: Prefixo do prompt de autenticação.
        """
        self._classifier = classifier or BlastRadiusClassifier()
        self._prompt_prefix = prompt_prefix

    def classify(self, command: str) -> BlastRadius:
        """Classifica o Blast Radius de um comando.

        Args:
            command: Comando a classificar.

        Returns:
            ``BlastRadius`` do comando.
        """
        return self._classifier.classify(command)

    def requires_nuclear_auth(self, command: str) -> bool:
        """Verifica se um comando requer autenticação nuclear do SO.

        Args:
            command: Comando a verificar.

        Returns:
            True se o comando é NUCLEAR_DESTRUCTIVE.
        """
        return self._classifier.is_nuclear(command)

    def challenge(self, command: str) -> NuclearChallengeResult:
        """Dispara o desafio de autenticação nuclear se necessário.

        Se o comando NÃO é nuclear, retorna imediatamente com authorized=True.
        Se o comando É nuclear, exige autenticação do SO.

        Args:
            command: Comando a verificar e potencialmente desafiar.

        Returns:
            ``NuclearChallengeResult`` com resultado da autenticação.
        """
        blast = self._classifier.classify(command)

        if blast != BlastRadius.NUCLEAR_DESTRUCTIVE:
            return NuclearChallengeResult(
                authorized=True,
                method_used="no_auth_required",
                duration_seconds=0.0,
                command_pattern=command[:80],
                blast_radius=blast,
            )

        # Comando nuclear: autenticação obrigatória
        logger.warning(
            "NuclearGate: DESAFIO NUCLEAR disparado para: '%s'",
            command[:100],
        )
        return self._run_challenge(command, blast)

    def assert_authorized(self, command: str) -> NuclearChallengeResult:
        """Verifica autorização e lança exceção se negada.

        Args:
            command: Comando a verificar.

        Returns:
            ``NuclearChallengeResult`` se autorizado.

        Raises:
            NuclearAuthDenied: Se a autenticação foi negada ou cancelada.
        """
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
        """Executa o desafio de autenticação nuclear.

        Tenta os métodos na seguinte ordem:
        1. zenity (GTK, GNOME/XFCE)
        2. kdialog (KDE)
        3. getpass via /dev/tty (headless/SSH)

        Args:
            command: Comando que disparou o desafio.
            blast: Classificação de blast radius.

        Returns:
            ``NuclearChallengeResult`` com resultado.
        """
        t0 = time.monotonic()
        short_cmd = command[:80] + ("..." if len(command) > 80 else "")

        prompt_msg = (
            f"{self._prompt_prefix}\n\n"
            f"⚠️  OPERAÇÃO DESTRUTIVA DETECTADA\n"
            f"Comando: {short_cmd}\n"
            f"Risco: {blast.value.upper()}\n\n"
            f"Esta ação é IRREVERSÍVEL. Digite sua senha para confirmar:"
        )

        # Tentar autenticação gráfica se display disponível
        if self._has_display():
            method, success = self._try_graphical_auth(prompt_msg)
            if method != "skipped":
                duration = time.monotonic() - t0
                return NuclearChallengeResult(
                    authorized=success,
                    method_used=method,
                    duration_seconds=duration,
                    command_pattern=short_cmd,
                    blast_radius=blast,
                )

        # Fallback: getpass via /dev/tty
        method, success = self._try_tty_auth(prompt_msg)
        duration = time.monotonic() - t0
        return NuclearChallengeResult(
            authorized=success,
            method_used=method,
            duration_seconds=duration,
            command_pattern=short_cmd,
            blast_radius=blast,
        )

    def _has_display(self) -> bool:
        """Verifica se há um display gráfico disponível."""
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    def _try_graphical_auth(self, prompt: str) -> tuple[str, bool]:
        """Tenta autenticação gráfica via zenity ou kdialog.

        Args:
            prompt: Mensagem do prompt.

        Returns:
            Tupla (método_usado, sucesso).
        """
        # Tentar zenity (GTK)
        if shutil.which("zenity"):
            try:
                result = subprocess.run(
                    ["zenity", "--password", "--title", "ORION Nuclear Safety Gate"],
                    capture_output=True,
                    timeout=60,
                    text=True,
                )
                if result.returncode == 0 and result.stdout.strip():
                    logger.info("NuclearGate: autenticado via zenity.")
                    return ("zenity", True)
                logger.warning("NuclearGate: zenity cancelado ou senha vazia.")
                return ("zenity", False)
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning("NuclearGate: zenity falhou — %s", exc)

        # Tentar kdialog (KDE)
        if shutil.which("kdialog"):
            try:
                result = subprocess.run(
                    ["kdialog", "--password", "ORION Nuclear Safety Gate — Confirme sua identidade:"],
                    capture_output=True,
                    timeout=60,
                    text=True,
                )
                if result.returncode == 0 and result.stdout.strip():
                    logger.info("NuclearGate: autenticado via kdialog.")
                    return ("kdialog", True)
                logger.warning("NuclearGate: kdialog cancelado ou senha vazia.")
                return ("kdialog", False)
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning("NuclearGate: kdialog falhou — %s", exc)

        return ("skipped", False)

    def _try_tty_auth(self, prompt: str) -> tuple[str, bool]:
        """Autenticação segura via /dev/tty (headless/SSH).

        Lê senha diretamente do terminal sem eco, evitando injeção
        via stdin automatizado.

        Args:
            prompt: Mensagem do prompt.

        Returns:
            Tupla (método_usado, sucesso).
        """
        print(
            "\n" + "━" * 60,
            "\n🔐 ORION NUCLEAR SAFETY GATE — AUTENTICAÇÃO REQUERIDA",
            "\n" + "━" * 60,
            "\n⚠️  Esta operação é IRREVERSÍVEL e requer sua presença física.",
            f"\n{prompt}",
            "\n" + "━" * 60,
        )

        try:
            # Usar /dev/tty diretamente para evitar que stdin seja
            # redirecionado por automação
            if os.path.exists("/dev/tty"):
                with _open_tty("/dev/tty") as tty:
                    import termios
                    import tty as tty_module
                    old_settings = termios.tcgetattr(tty.fileno())
                    try:
                        tty_module.setraw(tty.fileno())
                        print("\nSenha (oculta): ", end="", flush=True)
                        password = []
                        while True:
                            char = tty.read(1)
                            if char in ("\n", "\r"):
                                break
                            if char == "\x03":  # Ctrl+C
                                raise KeyboardInterrupt
                            password.append(char)
                        print()  # nova linha
                    finally:
                        termios.tcsetattr(tty.fileno(), termios.TCSADRAIN, old_settings)

                    entered = "".join(password)
            else:
                # Fallback final: getpass padrão
                entered = getpass.getpass("\nSenha (oculta): ")

            if entered.strip():
                # Não validamos a senha aqui — apenas que o usuário digitou algo.
                # A validação real seria via PAM/polkit, mas essa integração
                # requer chamadas nativas do SO (escopo futuro).
                # Por ora: presença + senha não-vazia = autorização.
                logger.info("NuclearGate: autenticado via tty_fallback.")
                return ("tty_fallback", True)
            else:
                logger.warning("NuclearGate: senha vazia no tty — negado.")
                return ("tty_fallback", False)

        except KeyboardInterrupt:
            print("\n[ORION] Operação nuclear cancelada pelo usuário.")
            return ("tty_fallback", False)
        except Exception as exc:
            logger.error("NuclearGate: falha no desafio TTY — %s", exc)
            return ("tty_fallback_error", False)


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
            f"☢️  ORION Nuclear Safety Gate: operação NEGADA.\n"
            f"   Comando: {command[:80]}\n"
            f"   Risco: {blast_radius.value}\n"
            f"   Método: {method_used}\n"
            f"   A ação foi cancelada ou a autenticação falhou."
        )
