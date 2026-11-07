"""
O.R.I.O.N — Command Trust Ledger (v0.3.0 Sprint 4)

Cache persistente de assinaturas de comandos conhecidos e seguros.

Implementa a Autonomia Adaptativa: comandos que já foram aprovados
pelo usuário e executados com sucesso são registrados com uma assinatura
canônica. Em modo auto, o PEP consulta este ledger antes de pedir
confirmação ao usuário — se o comando é conhecido e seguro, executa
silenciosamente.

REGRAS DE SEGURANÇA (invioláveis):
───────────────────────────────────
  1. Comandos NUCLEAR_DESTRUCTIVE NUNCA são registrados no trust ledger.
     O NuclearSafetyGate sempre intercepta esses comandos, independente
     do histórico.
  2. Comandos só são registrados após execução BEM-SUCEDIDA (exit_code=0).
     Falhas não aprendem.
  3. O conteúdo do banco pode ser auditado e limpo pelo usuário a qualquer
     momento — é armazenado em ``~/.orion/command_trust.db``.
  4. Assinaturas são baseadas em padrão canônico (sem argumentos variáveis),
     não no comando literal. Ex: ``git commit -m *`` → ``git commit``.

Referências: ADR-017 (Command Trust Ledger & Autonomia Adaptativa).
"""

from __future__ import annotations

import hashlib
import logging
import re
import shlex
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".orion" / "command_trust.db"


# ---------------------------------------------------------------------------
# Modelos de Dados
# ---------------------------------------------------------------------------


class CommandSignature(BaseModel):
    """Assinatura de um comando confiável registrado no ledger.

    Attributes:
        command_hash: SHA-256 do padrão canônico (8 hex chars).
        canonical_pattern: Padrão canônico do comando (sem args variáveis).
        first_executed_at: ISO-8601 UTC da primeira execução aprovada.
        last_executed_at: ISO-8601 UTC da última execução aprovada.
        execution_count: Número total de execuções bem-sucedidas registradas.
        last_exit_code: Código de saída da última execução (sempre 0 aqui).
        sudo_required: True se o comando requer sudo.
        trust_level: Nível de confiança: 'auto' (sem prompt) ou 'once' (sempre perguntar).
    """

    model_config = {"frozen": True}

    command_hash: str = Field(description="SHA-256 truncado do padrão canônico (8 chars)")
    canonical_pattern: str = Field(description="Padrão canônico do comando")
    first_executed_at: str = Field(description="ISO-8601 UTC da primeira execução")
    last_executed_at: str = Field(description="ISO-8601 UTC da última execução")
    execution_count: int = Field(ge=1, description="Total de execuções registradas")
    last_exit_code: int = Field(description="Código de saída da última execução")
    sudo_required: bool = Field(default=False, description="Requer sudo")
    trust_level: str = Field(default="auto", description="'auto' ou 'once'")


class TrustLookupResult(BaseModel):
    """Resultado de consulta ao CommandTrustLedger.

    Attributes:
        is_trusted: True se o comando é confiável e pode executar sem prompt.
        signature: A assinatura registrada (None se não encontrada).
        reason: Justificativa da decisão.
    """

    model_config = {"frozen": True}

    is_trusted: bool
    signature: CommandSignature | None
    reason: str


# ---------------------------------------------------------------------------
# Canonizador de Comandos
# ---------------------------------------------------------------------------


class CommandCanonicalizer:
    """Converte comandos literais em padrões canônicos para lookup no ledger.

    Remove argumentos variáveis (strings, paths, números) mantendo apenas
    a estrutura do comando. Isso permite que ``git commit -m "feat: xyz"``
    e ``git commit -m "fix: bug"`` tenham a mesma assinatura.

    Exemplos:
        ``git status``                     → ``git status``
        ``git commit -m "feat: add X"``   → ``git commit -m``
        ``npm test``                       → ``npm test``
        ``pytest tests/unit/test_foo.py`` → ``pytest``
        ``sudo apt install htop``          → ``sudo apt install``
        ``cat /tmp/file.txt``              → ``cat``
    """

    # Padrões que indicam argumentos variáveis (não fazem parte do padrão)
    _VARIABLE_PATTERNS = [
        re.compile(r'"[^"]*"'),           # Strings com aspas duplas
        re.compile(r"'[^']*'"),           # Strings com aspas simples
        re.compile(r"/[^\s]+"),           # Paths absolutos
        re.compile(r"\./[^\s]+"),         # Paths relativos com ./
        re.compile(r"\b\d+\b"),           # Números isolados
        re.compile(r"[^\s]+\.[a-z]{1,6}\b"),  # Arquivos com extensão
    ]

    @classmethod
    def canonicalize(cls, command: str) -> str:
        """Converte um comando literal em seu padrão canônico.

        Args:
            command: Comando literal a ser canonizado.

        Returns:
            Padrão canônico normalizado.
        """
        cmd = command.strip()
        if not cmd:
            return ""

        try:
            tokens = shlex.split(cmd)
        except ValueError:
            tokens = cmd.split()

        if not tokens:
            return ""

        canonical_tokens: list[str] = []
        i = 0
        n = len(tokens)

        # Tratar prefixo sudo
        if tokens[0].lower() == "sudo" and n > 1:
            canonical_tokens.append("sudo")
            i = 1

        if i >= n:
            return " ".join(canonical_tokens).lower()

        base_cmd = tokens[i].lower()
        canonical_tokens.append(base_cmd)
        i += 1

        # Ferramentas com subcomandos de pacotes (apt, brew, etc.)
        if base_cmd in {"apt", "apt-get", "yum", "dnf", "pacman", "brew"}:
            if i < n:
                canonical_tokens.append(tokens[i].lower())
            return " ".join(canonical_tokens).lower()

        # Ferramentas de sistema (systemctl, service)
        if base_cmd in {"systemctl", "service"}:
            if i < n:
                canonical_tokens.append(tokens[i].lower())
            return " ".join(canonical_tokens).lower()

        # Git: subcomandos e flag -m
        if base_cmd == "git":
            if i < n:
                sub = tokens[i].lower()
                canonical_tokens.append(sub)
                i += 1
                if i < n and tokens[i] in {"-m", "--message"}:
                    canonical_tokens.append("-m")
            return " ".join(canonical_tokens).lower()

        # Gerenciadores de pacote JS (npm, yarn, pnpm)
        if base_cmd in {"npm", "yarn", "pnpm"}:
            if i < n:
                sub = tokens[i].lower()
                canonical_tokens.append(sub)
                i += 1
                if sub == "run" and i < n:
                    canonical_tokens.append(tokens[i].lower())
            return " ".join(canonical_tokens).lower()

        # Outros comandos/utilitários (pytest, cat, ls, etc.)
        while i < n:
            token = tokens[i]
            if (
                any(p.search(token) for p in cls._VARIABLE_PATTERNS)
                or "/" in token
                or "\\" in token
                or "." in token
                or token.isdigit()
            ):
                break
            if token.startswith("-"):
                canonical_tokens.append(token.lower())
                i += 1
            else:
                break

        return " ".join(canonical_tokens).lower().strip()

    @classmethod
    def compute_hash(cls, canonical: str) -> str:
        """Calcula o hash SHA-256 truncado do padrão canônico.

        Args:
            canonical: Padrão canônico do comando.

        Returns:
            8 primeiros caracteres hexadecimais do SHA-256.
        """
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Command Trust Ledger
# ---------------------------------------------------------------------------


class CommandTrustLedger:
    """Cache persistente SQLite de assinaturas de comandos confiáveis.

    Armazena comandos que já foram aprovados pelo usuário e executados
    com sucesso. Em modo auto, o PEP consulta este ledger para evitar
    prompts repetitivos em comandos rotineiros e seguros.

    IMPORTANTE: Este ledger NÃO registra:
      - Comandos classificados como NUCLEAR_DESTRUCTIVE (sempre exigem popup)
      - Comandos com exit_code != 0 (falhas não aprendem)
      - Comandos que destroem dados irreversivelmente

    Thread-safe via lock de threading para uso em contextos assíncronos.

    Exemplo de uso:
        >>> ledger = CommandTrustLedger()
        >>> result = ledger.lookup("git status")
        >>> result.is_trusted
        True  # se já foi executado com sucesso antes
        >>> ledger.record_success("git commit -m 'feat: add X'", exit_code=0)
        >>> ledger.lookup("git commit -m 'fix: bug'").is_trusted
        True  # mesma assinatura canônica
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Inicializa o ledger e cria o banco SQLite se necessário.

        Args:
            db_path: Caminho do banco SQLite. Padrão: ``~/.orion/command_trust.db``.
        """
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize_db()

    # ── API Pública ───────────────────────────────────────────────────────────

    def lookup(self, command: str) -> TrustLookupResult:
        """Verifica se um comando é confiável (já aprovado e executado com sucesso).

        Args:
            command: Comando literal a verificar.

        Returns:
            ``TrustLookupResult`` indicando se o comando é confiável.
        """
        canonical = CommandCanonicalizer.canonicalize(command)
        cmd_hash = CommandCanonicalizer.compute_hash(canonical)

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM command_trust WHERE command_hash = ?",
                (cmd_hash,),
            ).fetchone()

        if row is None:
            return TrustLookupResult(
                is_trusted=False,
                signature=None,
                reason=f"Comando desconhecido: padrão '{canonical}' não está no trust ledger.",
            )

        sig = CommandSignature(
            command_hash=row["command_hash"],
            canonical_pattern=row["canonical_pattern"],
            first_executed_at=row["first_executed_at"],
            last_executed_at=row["last_executed_at"],
            execution_count=row["execution_count"],
            last_exit_code=row["last_exit_code"],
            sudo_required=bool(row["sudo_required"]),
            trust_level=row["trust_level"],
        )

        if sig.trust_level == "once":
            return TrustLookupResult(
                is_trusted=False,
                signature=sig,
                reason=f"Comando '{canonical}' configurado como 'once': sempre requer confirmação.",
            )

        return TrustLookupResult(
            is_trusted=True,
            signature=sig,
            reason=(
                f"Comando confiável: '{canonical}' executado com sucesso "
                f"{sig.execution_count}x. Última execução: {sig.last_executed_at}."
            ),
        )

    def record_success(
        self,
        command: str,
        exit_code: int = 0,
        *,
        trust_level: str = "auto",
    ) -> CommandSignature:
        """Registra uma execução bem-sucedida de um comando.

        Cria ou atualiza a assinatura do comando no ledger.

        IMPORTANTE: Chame este método APENAS após confirmar que:
          1. O comando NÃO é NUCLEAR_DESTRUCTIVE.
          2. O exit_code indica sucesso.

        Args:
            command: Comando literal executado.
            exit_code: Código de saída (deve ser 0 para sucesso).
            trust_level: Nível de confiança: 'auto' (executar sem prompt)
                         ou 'once' (sempre perguntar).

        Returns:
            ``CommandSignature`` criada ou atualizada.
        """
        canonical = CommandCanonicalizer.canonicalize(command)
        cmd_hash = CommandCanonicalizer.compute_hash(canonical)
        now_iso = datetime.now(UTC).isoformat()
        sudo_required = command.strip().startswith("sudo ")

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT execution_count, first_executed_at FROM command_trust "
                "WHERE command_hash = ?",
                (cmd_hash,),
            ).fetchone()

            if existing:
                new_count = existing["execution_count"] + 1
                first_at = existing["first_executed_at"]
                conn.execute(
                    """
                    UPDATE command_trust
                    SET last_executed_at = ?,
                        execution_count  = ?,
                        last_exit_code   = ?,
                        trust_level      = ?
                    WHERE command_hash = ?
                    """,
                    (now_iso, new_count, exit_code, trust_level, cmd_hash),
                )
            else:
                new_count = 1
                first_at = now_iso
                conn.execute(
                    """
                    INSERT INTO command_trust
                        (command_hash, canonical_pattern, first_executed_at,
                         last_executed_at, execution_count, last_exit_code,
                         sudo_required, trust_level)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cmd_hash,
                        canonical,
                        first_at,
                        now_iso,
                        new_count,
                        exit_code,
                        int(sudo_required),
                        trust_level,
                    ),
                )

        logger.debug(
            "TrustLedger: comando registrado — padrão='%s', hash=%s, execuções=%d",
            canonical,
            cmd_hash,
            new_count,
        )

        return CommandSignature(
            command_hash=cmd_hash,
            canonical_pattern=canonical,
            first_executed_at=first_at,
            last_executed_at=now_iso,
            execution_count=new_count,
            last_exit_code=exit_code,
            sudo_required=sudo_required,
            trust_level=trust_level,
        )

    def revoke(self, command: str) -> bool:
        """Remove um comando do ledger de confiança.

        Args:
            command: Comando literal a revogar.

        Returns:
            True se o comando foi encontrado e removido; False se não existia.
        """
        canonical = CommandCanonicalizer.canonicalize(command)
        cmd_hash = CommandCanonicalizer.compute_hash(canonical)

        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM command_trust WHERE command_hash = ?",
                (cmd_hash,),
            )
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info(
                "TrustLedger: confiança revogada — padrão='%s', hash=%s",
                canonical,
                cmd_hash,
            )
        return deleted

    def list_trusted(self) -> list[CommandSignature]:
        """Lista todos os comandos registrados no ledger.

        Returns:
            Lista de ``CommandSignature`` ordenada por data da última execução.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM command_trust ORDER BY last_executed_at DESC"
            ).fetchall()

        return [
            CommandSignature(
                command_hash=row["command_hash"],
                canonical_pattern=row["canonical_pattern"],
                first_executed_at=row["first_executed_at"],
                last_executed_at=row["last_executed_at"],
                execution_count=row["execution_count"],
                last_exit_code=row["last_exit_code"],
                sudo_required=bool(row["sudo_required"]),
                trust_level=row["trust_level"],
            )
            for row in rows
        ]

    def clear(self) -> int:
        """Remove todos os registros do ledger (útil para testes e reset).

        Returns:
            Número de registros removidos.
        """
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM command_trust")
            count = cursor.rowcount
        logger.warning("TrustLedger: %d registros removidos do ledger.", count)
        return count

    # ── Internals ─────────────────────────────────────────────────────────────

    def _initialize_db(self) -> None:
        """Cria o schema SQLite se ainda não existir."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS command_trust (
                    command_hash       TEXT PRIMARY KEY,
                    canonical_pattern  TEXT NOT NULL,
                    first_executed_at  TEXT NOT NULL,
                    last_executed_at   TEXT NOT NULL,
                    execution_count    INTEGER NOT NULL DEFAULT 1,
                    last_exit_code     INTEGER NOT NULL DEFAULT 0,
                    sudo_required      INTEGER NOT NULL DEFAULT 0,
                    trust_level        TEXT NOT NULL DEFAULT 'auto'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trust_last_exec "
                "ON command_trust (last_executed_at)"
            )

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Abre uma conexão SQLite thread-safe com row_factory configurada."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
