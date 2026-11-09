"""Isolamento por ``git worktree`` temporário (``isolation: worktree``, ADR-028).

Cada filho isolado recebe um *checkout* separado do ``HEAD`` do repositório do Senhor, fora do
repositório (``~/.orion/worktrees/``). Ele escreve só ali: o ``WorkspaceScope`` do filho é a raiz
do worktree, o PEP valida ``cwd``/``path`` contra ela e o runtime ancora caminhos relativos nela.

**Falha fechada:** fora de um repositório git (ou sem commit) o isolamento é impossível e a
execução é recusada; nunca se cai em silêncio para o workspace compartilhado. Sem alterações o
worktree é removido; com alterações ele é mantido e o Senhor é avisado do caminho.
Limite conhecido: o worktree parte do ``HEAD``, então não enxerga mudanças não commitadas do pai.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import shutil
import subprocess
from pathlib import Path

from orion.agents.models import WorkspaceOutcome
from orion.governance.permissions import WorkspaceScope

logger = logging.getLogger(__name__)

_AGENT_ID = re.compile(r"^agent_[0-9a-f]{6,32}$")
_GIT_TIMEOUT_S = 60


class WorkspaceUnavailable(Exception):
    """Não foi possível criar o workspace isolado (a execução deve ser recusada)."""


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - argumentos fixos, sem shell
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=_GIT_TIMEOUT_S,
    )


class GitWorktreeWorkspace:
    """``WorkspacePort`` sobre ``git worktree``."""

    def __init__(self, workspace: Path, base_dir: Path) -> None:
        self._workspace = workspace.resolve()
        self._base = base_dir
        self._active: dict[str, tuple[Path, Path]] = {}  # agent_id -> (repo, worktree)

    @property
    def active(self) -> list[str]:
        return sorted(self._active)

    async def prepare(self, agent_id: str) -> WorkspaceScope:
        if not _AGENT_ID.match(agent_id):
            raise WorkspaceUnavailable(f"identificador de agente inválido: {agent_id!r}")
        return await asyncio.to_thread(self._prepare, agent_id)

    def _prepare(self, agent_id: str) -> WorkspaceScope:
        try:
            top = _git(self._workspace, "rev-parse", "--show-toplevel")
        except (OSError, subprocess.SubprocessError) as exc:
            raise WorkspaceUnavailable(f"git indisponível: {exc}") from exc
        if top.returncode != 0 or not top.stdout.strip():
            raise WorkspaceUnavailable("o workspace não é um repositório git")
        repo = Path(top.stdout.strip()).resolve()
        if _git(repo, "rev-parse", "--verify", "HEAD").returncode != 0:
            raise WorkspaceUnavailable("o repositório não tem nenhum commit (HEAD inexistente)")
        slug = hashlib.sha256(str(repo).encode()).hexdigest()[:12]
        path = self._base / slug / agent_id
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        added = _git(repo, "worktree", "add", "--detach", str(path), "HEAD")
        if added.returncode != 0:
            raise WorkspaceUnavailable(f"git worktree add falhou: {added.stderr.strip()[:300]}")
        self._active[agent_id] = (repo, path)
        return WorkspaceScope([path])

    async def release(self, agent_id: str, *, keep_if_changed: bool) -> WorkspaceOutcome:
        entry = self._active.pop(agent_id, None)
        if entry is None:
            return WorkspaceOutcome()
        return await asyncio.to_thread(self._release, entry, keep_if_changed)

    def _release(self, entry: tuple[Path, Path], keep_if_changed: bool) -> WorkspaceOutcome:
        repo, path = entry
        status = _git(path, "status", "--porcelain")
        changed = [line[3:].strip() for line in status.stdout.splitlines() if line.strip()]
        if changed and keep_if_changed:
            return WorkspaceOutcome(kept=True, path=str(path), changed_files=changed)
        removed = _git(repo, "worktree", "remove", "--force", str(path))
        if removed.returncode != 0:
            logger.warning("worktree remove falhou (%s); removendo à mão", removed.stderr.strip()[:200])
            shutil.rmtree(path, ignore_errors=True)
        _git(repo, "worktree", "prune")
        return WorkspaceOutcome(kept=False, path=str(path))
