"""v0.5.3 Sprint 2 — motor de reversibilidade, /undo e undo_last (ADR-047, CA-06)."""

from __future__ import annotations

import io
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from orion.core.events import Action
from orion.governance.audit import AuditLogger
from orion.governance.bands import Band, DestructiveOp
from orion.governance.pep import AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import WorkspaceScope
from orion.governance.reversibility import GIB, ReversibilityEngine, SnapshotError
from orion.runtime.local_provider import LocalRuntimeProvider


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def clock() -> Clock:
    return Clock()


@pytest.fixture()
def engine(tmp_path: Path, clock: Clock) -> ReversibilityEngine:
    return ReversibilityEngine(tmp_path / "orion", clock=clock)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    for i in range(30):
        (root / "src" / f"m{i:02d}.py").write_text(f"x = {i}\n")
    return root


def delete(*targets: str, cwd: Path) -> DestructiveOp:
    return DestructiveOp("delete", targets, str(cwd))


class TestEngine:
    def test_plan_resolves_globs_and_measures(self, engine: ReversibilityEngine, project: Path) -> None:
        plan = engine.plan([delete("src/m0*.py", cwd=project)])
        assert len(plan.files) == 10 and plan.bytes > 0 and not plan.unresolved

    def test_plan_marks_opaque_targets(self, engine: ReversibilityEngine, project: Path) -> None:
        assert engine.plan([delete("$DIR/x", cwd=project)]).unresolved
        assert engine.plan([DestructiveOp("delete", (), str(project))]).unresolved

    def test_regenerable_dirs_are_not_copied(self, engine: ReversibilityEngine, project: Path) -> None:
        (project / "node_modules" / "pkg").mkdir(parents=True)
        (project / "node_modules" / "pkg" / "i.js").write_text("x" * 100)
        plan = engine.plan([delete("node_modules", "src", cwd=project)])
        assert [p.name for p in plan.regenerable] == ["node_modules"] and plan.regenerable_bytes == 100
        snap = engine.snapshot(plan, command="rm -rf node_modules src")
        assert snap is not None and snap.regenerable and snap.file_count == 30

    def test_snapshot_and_restore_30_files(self, engine: ReversibilityEngine, project: Path) -> None:
        """CA-06 no motor: 30 arquivos não commitados voltam idênticos."""
        plan = engine.plan([delete("src", cwd=project)])
        snap = engine.snapshot(plan, command="rm -rf src", session_id="s1")
        assert snap is not None and snap.file_count == 30
        assert (snap.root / "manifest.json").exists()
        assert oct(engine.trash.stat().st_mode & 0o777) == "0o700"
        subprocess.run(["rm", "-rf", str(project / "src")], check=True)
        result = engine.restore(session_id="s1")
        assert result is not None and len(result.restored) == 30 and not result.conflicts
        assert (project / "src" / "m07.py").read_text() == "x = 7\n"
        assert engine.latest(session_id="s1") is None  # restaurado não volta a ser "o último"
        again = engine.restore(snap.id)
        assert again is not None and "já restaurado" in again.summary()

    def test_hardlink_only_when_safe(self, engine: ReversibilityEngine, project: Path) -> None:
        lone = project / "src" / "m00.py"
        shared = project / "src" / "m01.py"
        os.link(shared, project / "outro-nome.py")
        snap = engine.snapshot(engine.plan([delete(str(lone), str(shared), cwd=project)]), command="rm")
        assert snap is not None
        stored = {Path(e.original).name: snap.root / e.stored for e in snap.entries}
        assert stored["m00.py"].stat().st_ino == lone.stat().st_ino  # único nome: hardlink
        assert stored["m01.py"].stat().st_ino != shared.stat().st_ino  # tem outro nome: cópia
        overwrite = engine.snapshot(engine.plan([DestructiveOp("overwrite", (str(lone),), str(project))]), command=">")
        assert overwrite is not None
        assert (overwrite.root / overwrite.entries[0].stored).stat().st_ino != lone.stat().st_ino

    def test_restore_keeps_current_version_aside(self, engine: ReversibilityEngine, project: Path) -> None:
        target = project / "src" / "m03.py"
        snap = engine.snapshot(engine.plan([DestructiveOp("overwrite", (str(target),), str(project))]), command="> m03")
        assert snap is not None
        target.write_text("novo\n")
        result = engine.restore(snap.id)
        assert result is not None and target.read_text() == "x = 3\n"
        aside = Path(result.conflicts[0][1])
        assert aside.read_text() == "novo\n" and aside.name.startswith("m03.py.orion-undo-")

    def test_symlinks_are_stored_as_links(self, engine: ReversibilityEngine, project: Path) -> None:
        link = project / "atalho"
        link.symlink_to(project / "src" / "m00.py")
        snap = engine.snapshot(engine.plan([delete("atalho", cwd=project)]), command="rm atalho")
        link.unlink()
        assert snap is not None and engine.restore(snap.id) is not None
        assert link.is_symlink() and os.readlink(link) == str(project / "src" / "m00.py")

    def test_action_cap(self, tmp_path: Path, project: Path) -> None:
        small = ReversibilityEngine(tmp_path / "o", action_cap=10)
        plan = small.plan([delete("src", cwd=project)])
        assert not small.fits(plan)
        with pytest.raises(SnapshotError):
            small.snapshot(plan, command="rm -rf src")

    def test_retention_and_total_cap_by_event(self, tmp_path: Path, project: Path, clock: Clock) -> None:
        engine = ReversibilityEngine(tmp_path / "o", total_cap=600, clock=clock)
        first = engine.snapshot(engine.plan([delete("src/m00.py", cwd=project)]), command="rm 0")
        clock.now += 8 * 24 * 3600  # 8 dias depois
        second = engine.snapshot(engine.plan([delete("src/m01.py", cwd=project)]), command="rm 1")
        ids = [s.id for s in engine.list()]
        assert first is not None and second is not None
        assert first.id not in ids and second.id in ids  # vencido saiu no evento do novo snapshot
        for i in range(2, 30):
            engine.snapshot(engine.plan([delete(f"src/m{i:02d}.py", cwd=project)]), command=f"rm {i}")
        assert engine.total_bytes() <= 600
        assert DEFAULT_CAPS == (2 * GIB, 10 * GIB)

    def test_nothing_to_save(self, engine: ReversibilityEngine, project: Path) -> None:
        plan = engine.plan([delete("nao-existe.txt", cwd=project)])
        assert plan.empty and plan.missing == ["nao-existe.txt"]
        assert engine.snapshot(plan, command="rm nao-existe.txt") is None


DEFAULT_CAPS = (ReversibilityEngine(Path("/nonexistent")).action_cap, ReversibilityEngine(Path("/nonexistent")).total_cap)


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return out.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / "a.txt").write_text("v1\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "init")
    return root


class TestGit:
    def test_reset_hard_is_undone_through_stash_ref(self, engine: ReversibilityEngine, repo: Path) -> None:
        (repo / "a.txt").write_text("trabalho não commitado\n")
        plan = engine.plan([DestructiveOp("git_tree", (), str(repo), ("reset", "--hard"))])
        snap = engine.snapshot(plan, command="git reset --hard")
        assert snap is not None and snap.git_refs
        assert git(repo, "for-each-ref", "refs/orion/undo/").strip()
        git(repo, "reset", "--hard", "-q")
        assert (repo / "a.txt").read_text() == "v1\n"
        result = engine.restore(snap.id)
        assert result is not None and (repo / "a.txt").read_text() == "trabalho não commitado\n"

    def test_git_clean_snapshots_untracked_files(self, engine: ReversibilityEngine, repo: Path) -> None:
        (repo / "novo.txt").write_text("não rastreado\n")
        (repo / "dir").mkdir()
        (repo / "dir" / "x.txt").write_text("x\n")
        plan = engine.plan([DestructiveOp("git_clean", (), str(repo), ("-fd",))])
        assert {p.name for p in plan.files} == {"novo.txt", "dir"}
        snap = engine.snapshot(plan, command="git clean -fd")
        git(repo, "clean", "-fdq")
        assert snap is not None and engine.restore(snap.id) is not None
        assert (repo / "dir" / "x.txt").read_text() == "x\n"

    def test_dropping_a_snapshot_deletes_its_ref(self, tmp_path: Path, repo: Path, clock: Clock) -> None:
        engine = ReversibilityEngine(tmp_path / "o", clock=clock)
        (repo / "a.txt").write_text("mudou\n")
        engine.snapshot(engine.plan([DestructiveOp("git_tree", (), str(repo), ("checkout", "--", "."))]), command="x")
        clock.now += 30 * 24 * 3600
        engine.collect()
        assert git(repo, "for-each-ref", "refs/orion/undo/") == ""


def band_pep(tmp_path: Path, engine: ReversibilityEngine | None, **kw: Any) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(
        scope=WorkspaceScope([tmp_path]),
        mode=kw.pop("mode", AutonomyMode.WORKSPACE_AUTO),
        audit_logger=AuditLogger(tmp_path / "audit.log"),
        reversibility=engine,
        confirm=kw.pop("confirm", lambda _p: False),
        **kw,
    )


class TestPep:
    async def test_ca06_rm_30_files_runs_without_asking_and_undo_restores(
        self, tmp_path: Path, engine: ReversibilityEngine, project: Path
    ) -> None:
        asked: list[str] = []
        pep = band_pep(tmp_path, engine, confirm=lambda p: asked.append(p) or False)
        runtime = LocalRuntimeProvider(pep=pep, scope=pep.scope)
        result = await runtime.execute("run_command", {"command": f"rm {project}/src/*.py"})
        assert result.success, result.error
        assert asked == [] and not list((project / "src").iterdir())
        assert result.metadata["snapshot_files"] == 30
        assert engine.restore(result.metadata["snapshot_id"]) is not None
        assert len(list((project / "src").iterdir())) == 30

    async def test_without_engine_deletion_is_nuclear(self, tmp_path: Path, project: Path) -> None:
        pep = band_pep(tmp_path, None)
        verdict = pep.band_of(Action(tool="run_command", params={"command": f"rm {project}/src/m00.py"}))
        assert verdict.band == Band.NUCLEAR and verdict.rule == "no_snapshot"

    async def test_over_cap_is_nuclear_and_regenerable_over_cap_is_presence(self, tmp_path: Path, project: Path) -> None:
        pep = band_pep(tmp_path, ReversibilityEngine(tmp_path / "o", action_cap=50))
        big = pep.band_of(Action(tool="run_command", params={"command": f"rm -r {project}/src"}))
        assert big.band == Band.NUCLEAR and big.rule == "snapshot_over_cap"
        (project / ".venv" / "lib").mkdir(parents=True)
        (project / ".venv" / "lib" / "x.so").write_bytes(b"x" * 100)
        venv = pep.band_of(Action(tool="run_command", params={"command": f"rm -rf {project}/.venv"}))
        assert venv.band == Band.PRESENCA

    async def test_unresolved_targets_go_up_one_band(self, tmp_path: Path, engine: ReversibilityEngine, project: Path) -> None:
        pep = band_pep(tmp_path, engine)
        verdict = pep.band_of(Action(tool="run_command", params={"command": "find . -name '*.pyc' -delete", "cwd": str(project)}))
        assert verdict.band == Band.PRESENCA and not verdict.stage1_allow

    async def test_snapshot_failure_denies(self, tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from orion.governance.pep import ActionDenied

        engine = ReversibilityEngine(tmp_path / "o")

        def boom(*_a: Any, **_k: Any) -> Any:
            raise SnapshotError("disco cheio")

        monkeypatch.setattr(engine, "snapshot", boom)
        pep = band_pep(tmp_path, engine)
        with pytest.raises(ActionDenied, match="disco cheio"):
            await pep.evaluate(Action(tool="run_command", params={"command": f"rm {project}/src/m00.py"}))
        assert (project / "src" / "m00.py").exists()

    async def test_edited_command_is_the_one_snapshotted(self, tmp_path: Path, engine: ReversibilityEngine, project: Path) -> None:
        def confirm(action: Action, level: Any) -> Any:
            return {"command": f"rm {project}/src/m05.py"}

        pep = PolicyEnforcementPoint(
            scope=WorkspaceScope([tmp_path]),
            mode=AutonomyMode.SUPERVISED,
            audit_logger=AuditLogger(tmp_path / "audit.log"),
            reversibility=engine,
            action_confirm=confirm,
        )
        action = Action(tool="run_command", params={"command": f"rm {project}/src/m04.py"})
        assert await pep.evaluate(action)
        snap = pep.take_snapshot(action.event_id)
        assert snap is not None and [Path(e.original).name for e in snap.entries] == ["m05.py"]


class TestSessionUndo:
    @pytest.fixture()
    def session(self, tmp_path: Path) -> Any:
        from orion.tui.session import AgentSession
        from orion.tui.status_bar import SessionStatusBar
        from orion.tui.theme import get_orion_theme

        (tmp_path / "ws").mkdir()
        return AgentSession(
            status_bar=SessionStatusBar(),
            console=Console(file=io.StringIO(), width=120, theme=get_orion_theme()),
            workspace=tmp_path / "ws",
            home=tmp_path / "home",
        )

    async def test_turn_line_and_slash_undo(self, session: Any, tmp_path: Path) -> None:
        from orion.tui.commands.base import CommandContext
        from orion.tui.commands.operation import UndoCommand

        ws = tmp_path / "ws"
        for i in range(3):
            (ws / f"f{i}.txt").write_text(str(i))
        lines: list[str] = []
        session.renderer.agent_line = lambda text, **_: lines.append(text)
        assert await session.run_tool("run_command", {"command": f"rm {ws}/f0.txt {ws}/f1.txt {ws}/f2.txt"})
        assert not (ws / "f1.txt").exists()
        assert any("3 arquivos no lixo do ORION · /undo" in line for line in lines)
        context = CommandContext(session=session, console=session.console, clear_screen=lambda: None)
        listed = await UndoCommand().execute("list", context)
        assert listed.success and len(listed.data) == 1
        result = await UndoCommand().execute("", context)
        assert result.success and "restaurado" in (result.output_message or "")
        assert (ws / "f1.txt").read_text() == "1"
        missing = await UndoCommand().execute("zzzz", context)
        assert not missing.success

    async def test_undo_last_tool(self, session: Any, tmp_path: Path) -> None:
        ws = tmp_path / "ws"
        (ws / "doc.md").write_text("original")
        assert await session.run_tool("run_command", {"command": f"echo trocado > {ws}/doc.md"})
        assert (ws / "doc.md").read_text().strip() == "trocado"
        result = await session.runtime.execute("undo_last", {})
        assert result.success and (ws / "doc.md").read_text() == "original"
        assert not (await session.runtime.execute("undo_last", {})).success
