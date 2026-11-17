"""Motor de reversibilidade (ADR-047, v0.5.3 Sprint 2).

Antes de uma deleção ou sobrescrita, o PEP pede um :class:`SnapshotPlan` (alvos resolvidos e
tamanho) e, aprovada a ação, o snapshot: cópia em ``~/.orion/trash/<ts>-<id>/`` com
``manifest.json`` (hardlink na deleção quando seguro, reflink quando o sistema de arquivos deixa,
cópia no resto) e, em repositório git, ``git stash create`` guardado em ``refs/orion/undo/<id>``.

Tetos: 2 GiB por ação e 10 GiB no total; acima do teto a ação sobe para Nuclear (quem decide é o
PEP). Retenção de 7 dias, limpa por evento (novo snapshot, ``/undo``), nunca por relógio ocioso
(ADR-022). Pastas regeneráveis (``node_modules``, ``.venv``, caches) não são copiadas: são
recuperáveis de outra forma e ficam registradas no manifesto.
"""

from __future__ import annotations

import contextlib
import fcntl
import glob as globlib
import json
import logging
import os
import shutil
import stat
import subprocess
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from orion.governance.bands import DestructiveOp

logger = logging.getLogger(__name__)

GIB = 1024**3
DEFAULT_ACTION_CAP = 2 * GIB
DEFAULT_TOTAL_CAP = 10 * GIB
DEFAULT_RETENTION_S = 7 * 24 * 3600
_FICLONE = 0x40049409  # ioctl de reflink no Linux (btrfs, xfs)

#: Pastas que se regeneram (instalar dependências, rodar o build): não vão para o lixo.
REGENERABLE_NAMES = frozenset(
    {
        "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache",
        ".ruff_cache", ".tox", ".nox", "dist", "build", "target", ".next", ".turbo", ".cache",
        ".gradle", ".parcel-cache", "coverage", "htmlcov", ".coverage",
    }
)


class SnapshotError(Exception):
    """O snapshot não pôde ser feito; sem ele a ação não é reversível."""


@dataclass
class SnapshotPlan:
    """Alvos resolvidos de uma ação destrutiva e quanto custa guardá-los."""

    files: list[Path] = field(default_factory=list)  # arquivos/links/pastas a copiar
    regenerable: list[Path] = field(default_factory=list)
    git: list[tuple[Path, str]] = field(default_factory=list)  # (repo, op) para stash create
    bytes: int = 0
    regenerable_bytes: int = 0
    unresolved: bool = False
    missing: list[str] = field(default_factory=list)
    #: Alvos de deleção (não de sobrescrita): podem ir por hardlink quando seguro.
    deleted: set[Path] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not self.files and not self.git

    @property
    def count(self) -> int:
        return sum(_count_files(p) for p in self.files)


@dataclass(frozen=True)
class SnapshotEntry:
    original: str
    stored: str
    kind: str  # file | dir | symlink
    size: int


@dataclass
class Snapshot:
    """Um snapshot no lixo do ORION."""

    id: str
    created_at: float
    command: str
    root: Path
    entries: list[SnapshotEntry] = field(default_factory=list)
    git_refs: list[dict[str, str]] = field(default_factory=list)
    regenerable: list[str] = field(default_factory=list)
    bytes: int = 0
    restored: bool = False
    session_id: str | None = None

    @property
    def file_count(self) -> int:
        return sum(1 for e in self.entries if e.kind != "dir")

    def summary(self) -> str:
        parts: list[str] = []
        if self.file_count:
            parts.append(f"{self.file_count} arquivo{'s' if self.file_count != 1 else ''}")
        if self.git_refs:
            parts.append("mudanças do git")
        return " + ".join(parts) or "nada"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "command": self.command,
            "entries": [e.__dict__ for e in self.entries],
            "git_refs": self.git_refs,
            "regenerable": self.regenerable,
            "bytes": self.bytes,
            "restored": self.restored,
            "session_id": self.session_id,
        }

    @classmethod
    def from_json(cls, root: Path, data: dict[str, Any]) -> Snapshot:
        return cls(
            id=str(data["id"]),
            created_at=float(data["created_at"]),
            command=str(data.get("command", "")),
            root=root,
            entries=[SnapshotEntry(**e) for e in data.get("entries", [])],
            git_refs=list(data.get("git_refs", [])),
            regenerable=list(data.get("regenerable", [])),
            bytes=int(data.get("bytes", 0)),
            restored=bool(data.get("restored", False)),
            session_id=data.get("session_id"),
        )


@dataclass
class RestoreResult:
    snapshot: Snapshot
    restored: list[str] = field(default_factory=list)
    conflicts: list[tuple[str, str]] = field(default_factory=list)  # (original, renomeado)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{len(self.restored)} item(ns) restaurado(s) de {self.snapshot.id}"]
        if self.conflicts:
            parts.append(f"{len(self.conflicts)} versão(ões) atual(is) preservada(s) como .orion-undo")
        parts.extend(self.notes)
        return "; ".join(parts)


def _count_files(path: Path) -> int:
    if path.is_symlink() or not path.is_dir():
        return 1
    total = 0
    for _root, _dirs, files in os.walk(path):
        total += len(files)
    return total


def _size(path: Path) -> int:
    try:
        if path.is_symlink():
            return 0
        if not path.is_dir():
            return path.stat().st_size
    except OSError:
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            with contextlib.suppress(OSError):
                full = Path(root) / name
                if not full.is_symlink():
                    total += full.stat().st_size
    return total


def _run_git(repo: Path, *args: str, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - argv fixo, sem shell
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _repo_root(path: Path) -> Path | None:
    try:
        out = _run_git(path, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return Path(out.stdout.strip())


class ReversibilityEngine:
    """Planeja, grava e restaura snapshots no lixo do ORION."""

    def __init__(
        self,
        home: Path,
        *,
        action_cap: int = DEFAULT_ACTION_CAP,
        total_cap: int = DEFAULT_TOTAL_CAP,
        retention_s: float = DEFAULT_RETENTION_S,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.trash = home / "trash"
        self.action_cap = action_cap
        self.total_cap = total_cap
        self.retention_s = retention_s
        self._clock = clock

    # ── Plano ───────────────────────────────────────────────────────────

    def plan(self, ops: Iterable[DestructiveOp]) -> SnapshotPlan:
        """Resolve os alvos (glob como o shell faria) e mede o que precisa ser guardado."""
        plan = SnapshotPlan()
        seen: set[Path] = set()
        for op in ops:
            cwd = Path(op.cwd) if op.cwd else Path.cwd()
            if op.kind == "git_tree":
                repo = _repo_root(cwd)
                if repo is None:
                    plan.unresolved = True
                    continue
                plan.git.append((repo, " ".join(op.git_args)))
                continue
            if op.kind == "git_clean":
                targets = self._git_clean_targets(cwd, op.git_args)
                if targets is None:
                    plan.unresolved = True
                    continue
            else:
                if not op.targets:
                    plan.unresolved = True
                    continue
                targets = []
                for raw in op.targets:
                    expanded = self._expand(raw, cwd)
                    if expanded is None:
                        plan.unresolved = True
                        continue
                    if not expanded:
                        plan.missing.append(raw)
                    targets.extend(expanded)
            for target in targets:
                absolute = Path(os.path.abspath(target))
                if absolute in seen or not (absolute.exists() or absolute.is_symlink()):
                    continue
                seen.add(absolute)
                if absolute.name in REGENERABLE_NAMES and absolute.is_dir() and not absolute.is_symlink():
                    plan.regenerable.append(absolute)
                    plan.regenerable_bytes += _size(absolute)
                    continue
                plan.files.append(absolute)
                plan.bytes += _size(absolute)
                if op.kind == "delete":
                    plan.deleted.add(absolute)
        return plan

    @staticmethod
    def _expand(raw: str, cwd: Path) -> list[Path] | None:
        if any(ch in raw for ch in "$`{}"):
            return None
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = cwd / path
        if any(ch in str(path) for ch in "*?["):
            return [Path(p) for p in sorted(globlib.glob(str(path)))]
        return [path] if path.exists() or path.is_symlink() else []

    @staticmethod
    def _git_clean_targets(cwd: Path, args: tuple[str, ...]) -> list[Path] | None:
        dry = [a for a in args if a not in ("-f", "--force", "-i", "--interactive")]
        dry = [("-" + a[1:].replace("f", "")) if a.startswith("-") and not a.startswith("--") else a for a in dry]
        dry = [a for a in dry if a != "-"]
        try:
            out = _run_git(cwd, "clean", "-n", *dry)
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        targets: list[Path] = []
        for line in out.stdout.splitlines():
            if line.startswith("Would remove "):
                targets.append(cwd / line[len("Would remove ") :].rstrip("/"))
        return targets

    def fits(self, plan: SnapshotPlan) -> bool:
        return plan.bytes <= self.action_cap

    # ── Snapshot ────────────────────────────────────────────────────────

    def snapshot(self, plan: SnapshotPlan, *, command: str, session_id: str | None = None) -> Snapshot | None:
        """Grava o snapshot do plano; None quando não há nada a guardar."""
        if plan.empty:
            return None
        if plan.bytes > self.action_cap:
            raise SnapshotError(f"snapshot de {plan.bytes} bytes acima do teto de {self.action_cap}")
        self.collect(needed=plan.bytes)
        snap_id = uuid.uuid4().hex[:8]
        stamp = datetime.fromtimestamp(self._clock(), UTC).strftime("%Y%m%dT%H%M%S")
        root = self.trash / f"{stamp}-{snap_id}"
        files_dir = root / "files"
        files_dir.mkdir(parents=True, exist_ok=False)
        os.chmod(self.trash, 0o700)
        snap = Snapshot(id=snap_id, created_at=self._clock(), command=command[:500], root=root, session_id=session_id)
        snap.regenerable = [str(p) for p in plan.regenerable]
        try:
            for index, target in enumerate(plan.files):
                stored = files_dir / f"{index:05d}"
                snap.entries.extend(self._store(target, stored, root, hardlink_ok=target in plan.deleted))
            for repo, op in plan.git:
                ref = self._git_snapshot(repo, snap_id, len(snap.git_refs))
                if ref is not None:
                    ref["op"] = op
                    snap.git_refs.append(ref)
        except OSError as exc:
            shutil.rmtree(root, ignore_errors=True)
            raise SnapshotError(f"falha ao copiar para o lixo do ORION: {exc}") from exc
        if not snap.entries and not snap.git_refs:
            shutil.rmtree(root, ignore_errors=True)
            return None
        snap.bytes = plan.bytes
        self._write_manifest(snap)
        return snap

    def _store(self, target: Path, stored: Path, root: Path, *, hardlink_ok: bool) -> list[SnapshotEntry]:
        entries: list[SnapshotEntry] = []
        rel = str(stored.relative_to(root))
        if target.is_symlink():
            os.symlink(os.readlink(target), stored)
            return [SnapshotEntry(str(target), rel, "symlink", 0)]
        if target.is_dir():
            stored.mkdir()
            entries.append(SnapshotEntry(str(target), rel, "dir", 0))
            for child in sorted(target.iterdir()):
                entries.extend(self._store(child, stored / child.name, root, hardlink_ok=hardlink_ok))
            return entries
        mode = target.lstat().st_mode
        if not stat.S_ISREG(mode):
            return []  # socket, fifo, dispositivo: nada a guardar
        size = target.stat().st_size
        if not (hardlink_ok and _try_hardlink(target, stored)):
            _copy_file(target, stored)
        return [SnapshotEntry(str(target), rel, "file", size)]

    def _git_snapshot(self, repo: Path, snap_id: str, index: int) -> dict[str, str] | None:
        head = _run_git(repo, "rev-parse", "HEAD")
        head_sha = head.stdout.strip() if head.returncode == 0 else ""
        created = _run_git(repo, "stash", "create", f"orion undo {snap_id}")
        if created.returncode != 0:
            raise OSError(created.stderr.strip() or "git stash create falhou")
        stash_sha = created.stdout.strip()
        ref = f"refs/orion/undo/{snap_id}" + (f"-{index}" if index else "")
        if stash_sha:
            update = _run_git(repo, "update-ref", ref, stash_sha)
            if update.returncode != 0:
                raise OSError(update.stderr.strip() or "git update-ref falhou")
        if not stash_sha and not head_sha:
            return None
        return {"repo": str(repo), "ref": ref if stash_sha else "", "stash": stash_sha, "head": head_sha}

    def _write_manifest(self, snap: Snapshot) -> None:
        path = snap.root / "manifest.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snap.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    # ── Consulta ────────────────────────────────────────────────────────

    def list(self) -> list[Snapshot]:
        """Snapshots do mais novo para o mais antigo."""
        if not self.trash.is_dir():
            return []
        found: list[Snapshot] = []
        for root in self.trash.iterdir():
            manifest = root / "manifest.json"
            try:
                found.append(Snapshot.from_json(root, json.loads(manifest.read_text(encoding="utf-8"))))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(found, key=lambda s: s.created_at, reverse=True)

    def get(self, snap_id: str) -> Snapshot | None:
        return next((s for s in self.list() if s.id == snap_id or s.id.startswith(snap_id)), None)

    def latest(self, *, session_id: str | None = None) -> Snapshot | None:
        for snap in self.list():
            if snap.restored:
                continue
            if session_id is not None and snap.session_id != session_id:
                continue
            return snap
        return None

    def total_bytes(self) -> int:
        return sum(s.bytes for s in self.list())

    # ── Restauração ─────────────────────────────────────────────────────

    def restore(self, snap_id: str | None = None, *, session_id: str | None = None) -> RestoreResult | None:
        """Devolve os arquivos ao lugar; a versão atual de um caminho ocupado é preservada."""
        snap = self.get(snap_id) if snap_id else self.latest(session_id=session_id)
        if snap is None:
            return None
        result = RestoreResult(snapshot=snap)
        if snap.restored:
            result.notes.append("já restaurado antes")
            return result
        # Pastas primeiro (pais antes dos filhos), depois arquivos e links.
        for entry in sorted(snap.entries, key=lambda e: (e.kind != "dir", e.original)):
            original = Path(entry.original)
            stored = snap.root / entry.stored
            if entry.kind == "dir":
                original.mkdir(parents=True, exist_ok=True)
                continue
            original.parent.mkdir(parents=True, exist_ok=True)
            if original.exists() or original.is_symlink():
                if entry.kind == "file" and original.is_file() and _same_content(original, stored):
                    result.restored.append(entry.original)
                    continue
                aside = original.with_name(f"{original.name}.orion-undo-{snap.id}")
                os.replace(original, aside)
                result.conflicts.append((entry.original, str(aside)))
            if entry.kind == "symlink":
                os.symlink(os.readlink(stored), original)
            else:
                _copy_file(stored, original)
                with contextlib.suppress(OSError):
                    shutil.copystat(stored, original)
            result.restored.append(entry.original)
        for ref in snap.git_refs:
            self._restore_git(ref, result)
        snap.restored = True
        self._write_manifest(snap)
        return result

    @staticmethod
    def _restore_git(ref: dict[str, str], result: RestoreResult) -> None:
        repo = Path(ref["repo"])
        head = _run_git(repo, "rev-parse", "HEAD")
        current = head.stdout.strip() if head.returncode == 0 else ""
        if ref.get("head") and current and current != ref["head"]:
            result.notes.append(
                f"HEAD mudou ({current[:8]}); era {ref['head'][:8]} em {repo.name}: "
                f"`git reset --keep {ref['head'][:12]}` volta o ponteiro"
            )
        if ref.get("stash"):
            applied = _run_git(repo, "stash", "apply", "--index", ref["stash"])
            if applied.returncode != 0:
                applied = _run_git(repo, "stash", "apply", ref["stash"])
            if applied.returncode != 0:
                result.notes.append(f"git stash apply falhou em {repo.name}: {applied.stderr.strip()[:200]}")
            else:
                result.restored.append(f"{repo}: mudanças do git ({ref['stash'][:8]})")

    # ── Limpeza por evento ──────────────────────────────────────────────

    def collect(self, *, needed: int = 0) -> int:
        """Apaga snapshots vencidos e, se preciso, os mais antigos até caber *needed*."""
        removed = 0
        now = self._clock()
        snaps = self.list()
        keep: list[Snapshot] = []
        for snap in snaps:
            if now - snap.created_at > self.retention_s:
                self._drop(snap)
                removed += 1
            else:
                keep.append(snap)
        total = sum(s.bytes for s in keep)
        for snap in sorted(keep, key=lambda s: s.created_at):
            if total + needed <= self.total_cap:
                break
            self._drop(snap)
            total -= snap.bytes
            removed += 1
        return removed

    @staticmethod
    def _drop(snap: Snapshot) -> None:
        for ref in snap.git_refs:
            if ref.get("ref"):
                with contextlib.suppress(OSError, subprocess.SubprocessError):
                    _run_git(Path(ref["repo"]), "update-ref", "-d", ref["ref"])
        shutil.rmtree(snap.root, ignore_errors=True)


def _same_content(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def _try_hardlink(src: Path, dst: Path) -> bool:
    """Hardlink só na deleção e só se o arquivo tem um único nome.

    Depois do ``rm``, o link do lixo vira o único nome do inode, então nada mais o altera. Com
    outros nomes (``st_nlink > 1``) uma escrita no lugar por eles mudaria o snapshot: copia.
    """
    try:
        if src.stat().st_nlink != 1:
            return False
        os.link(src, dst)
    except OSError:
        return False
    return True


def _copy_file(src: Path, dst: Path) -> None:
    """Reflink quando o sistema de arquivos deixa; senão cópia."""
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        try:
            fcntl.ioctl(fout.fileno(), _FICLONE, fin.fileno())
        except OSError:
            shutil.copyfileobj(fin, fout, length=1024 * 1024)
    with contextlib.suppress(OSError):
        shutil.copymode(src, dst)
