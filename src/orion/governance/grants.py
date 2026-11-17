"""Aprovação por intenção (ADR-047 item 5, v0.5.3 Sprint 2).

Quando o plano aprovado pelo Senhor lista passos de Presença (comandos e caminhos), o PEP recebe
um :class:`IntentGrant` com esse escopo e validade de 15 minutos: os passos listados rodam sem
nova pergunta. Um grant nunca cobre Nuclear nem a blocklist, e só vale para o que foi listado:
comando igual (tokens iguais, ou prefixo explícito terminado em `` *``) ou caminho dentro de um
caminho listado.
"""

from __future__ import annotations

import shlex
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orion.governance.bands import WRITE_TOOLS, Band

DEFAULT_TTL_S = 15 * 60


def _tokens(command: str) -> tuple[str, ...] | None:
    try:
        return tuple(shlex.split(command))
    except ValueError:
        return None


@dataclass(frozen=True)
class IntentGrant:
    """Escopo aprovado de uma vez pelo Senhor."""

    id: str
    commands: tuple[str, ...]
    paths: tuple[str, ...]
    expires_at: float
    note: str = ""

    def covers(self, tool: str, params: dict[str, Any]) -> bool:
        if tool == "run_command":
            return self._covers_command(str(params.get("command", "") or ""))
        if tool in WRITE_TOOLS:
            raw = str(params.get("path", "") or params.get("notebook_path", "") or "")
            return bool(raw) and self._covers_path(raw)
        return False

    def _covers_command(self, command: str) -> bool:
        wanted = _tokens(command)
        if not wanted:
            return False
        for listed in self.commands:
            prefix = listed.endswith(" *")
            tokens = _tokens(listed[:-2] if prefix else listed)
            if not tokens:
                continue
            if wanted == tokens or (prefix and wanted[: len(tokens)] == tokens):
                return True
        return False

    def _covers_path(self, raw: str) -> bool:
        try:
            target = Path(raw).expanduser().resolve()
        except (OSError, RuntimeError):
            return False
        for listed in self.paths:
            try:
                root = Path(listed).expanduser().resolve()
            except (OSError, RuntimeError):
                continue
            if target == root or root in target.parents:
                return True
        return False


@dataclass
class GrantStore:
    """Grants vivos de uma sessão (memória do processo; nunca persistidos)."""

    clock: Callable[[], float] = time.time
    _grants: list[IntentGrant] = field(default_factory=list)

    def issue(
        self,
        *,
        commands: Iterable[str] = (),
        paths: Iterable[str] = (),
        ttl_s: float = DEFAULT_TTL_S,
        note: str = "",
    ) -> IntentGrant | None:
        """Cria um grant com o escopo listado; None quando não há nada listado."""
        cmds = tuple(c.strip() for c in commands if c and c.strip())
        pths = tuple(p.strip() for p in paths if p and p.strip())
        if not cmds and not pths:
            return None
        grant = IntentGrant(
            id=uuid.uuid4().hex[:8],
            commands=cmds,
            paths=pths,
            expires_at=self.clock() + ttl_s,
            note=note[:200],
        )
        self._grants.append(grant)
        return grant

    def active(self) -> list[IntentGrant]:
        now = self.clock()
        self._grants = [g for g in self._grants if g.expires_at > now]
        return list(self._grants)

    def match(self, tool: str, params: dict[str, Any], band: Band) -> IntentGrant | None:
        """Grant vivo que cobre a ação; nunca para Nuclear (a blocklist nem chega aqui)."""
        if band >= Band.NUCLEAR:
            return None
        for grant in self.active():
            if grant.covers(tool, params):
                return grant
        return None

    def revoke_all(self) -> int:
        count = len(self._grants)
        self._grants.clear()
        return count
