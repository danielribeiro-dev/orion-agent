"""Isolamento por git worktree: escreve só no worktree, PEP confina e falha fechada fora de git."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orion.agents.runner import TaskRequest
from orion.agents.worktree import GitWorktreeWorkspace, WorkspaceUnavailable
from orion.governance.pep import AutonomyMode
from tests.agent_helpers import make_rig
from tests.llm_script import ScriptedLLM, say, use

ISOLATED = "---\nname: iso\ndescription: Isolado\nisolation: worktree\n---\nTrabalhe isolado.\n"


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout


def _repo(path: Path, *, commit: bool = True) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    if commit:
        (path / "app.py").write_text("print('original')\n")
        _git(path, "add", ".")
        _git(path, "commit", "-q", "-m", "init")
    return path


def _port(tmp_path: Path, workspace: Path) -> GitWorktreeWorkspace:
    return GitWorktreeWorkspace(workspace, tmp_path / "home" / "worktrees")


# ── porta ───────────────────────────────────────────────────────────────────


async def test_prepare_creates_a_checkout_outside_the_repo(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "ws")
    port = _port(tmp_path, repo)
    scope = await port.prepare("agent_abc123")
    root = scope.roots[0]
    assert (root / "app.py").read_text() == "print('original')\n"
    assert repo not in root.parents and root.parent.parent == (tmp_path / "home" / "worktrees").resolve()
    assert port.active == ["agent_abc123"]
    assert "agent_abc123" in _git(repo, "worktree", "list")


async def test_release_removes_an_untouched_worktree(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "ws")
    port = _port(tmp_path, repo)
    root = (await port.prepare("agent_abc123")).roots[0]
    outcome = await port.release("agent_abc123", keep_if_changed=True)
    assert not outcome.kept and not root.exists()
    assert "agent_abc123" not in _git(repo, "worktree", "list")
    assert (await port.release("agent_abc123", keep_if_changed=True)).kept is False  # idempotente


async def test_release_keeps_a_changed_worktree_and_lists_the_files(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "ws")
    port = _port(tmp_path, repo)
    root = (await port.prepare("agent_abc123")).roots[0]
    (root / "app.py").write_text("print('mudou')\n")
    (root / "novo.txt").write_text("x")
    outcome = await port.release("agent_abc123", keep_if_changed=True)
    assert outcome.kept and root.exists() and set(outcome.changed_files) == {"app.py", "novo.txt"}
    discarded = _port(tmp_path, repo)
    root2 = (await discarded.prepare("agent_def456")).roots[0]
    (root2 / "novo.txt").write_text("x")
    assert not (await discarded.release("agent_def456", keep_if_changed=False)).kept
    assert not root2.exists()


async def test_fails_closed_outside_git_or_without_commits(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(WorkspaceUnavailable, match="repositório git"):
        await _port(tmp_path, plain).prepare("agent_abc123")
    empty = _repo(tmp_path / "empty", commit=False)
    with pytest.raises(WorkspaceUnavailable, match="commit"):
        await _port(tmp_path, empty).prepare("agent_abc123")


async def test_rejects_ids_that_could_escape_the_base_dir(tmp_path: Path) -> None:
    port = _port(tmp_path, _repo(tmp_path / "ws"))
    for bad in ("../evil", "agent_../x", "AGENT_1", "x"):
        with pytest.raises(WorkspaceUnavailable):
            await port.prepare(bad)


# ── ponta a ponta com o runner ──────────────────────────────────────────────


def _iso_rig(tmp_path: Path, scripts: list[ScriptedLLM], mode: AutonomyMode = AutonomyMode.FULLY_AUTO):  # type: ignore[no-untyped-def]
    repo = _repo(tmp_path / "ws")
    port = _port(tmp_path, repo)
    rig = make_rig(tmp_path, scripts, mode=mode, extra_agents={"iso": ISOLATED}, workspace_port=port)
    return rig, repo, port


async def test_child_writes_only_inside_its_worktree(tmp_path: Path) -> None:
    script = ScriptedLLM(use("write_file", {"path": "gerado.txt", "content": "do filho"}), say("feito"))
    rig, repo, port = _iso_rig(tmp_path, [script])
    result = (await rig.runner.spawn_many([TaskRequest("iso", "gere")], rig.parent))[0]
    assert result.status == "ok"
    assert not (repo / "gerado.txt").exists()  # o workspace real ficou intocado
    assert "isolated workspace kept at" in result.summary and "gerado.txt" in result.summary
    kept = Path(result.summary.split("kept at ")[1].split(";")[0])
    assert (kept / "gerado.txt").read_text() == "do filho" and port.active == []
    assert _git(repo, "status", "--porcelain") == ""  # nem o git do repo real mudou


async def test_unchanged_worktree_is_cleaned_up_automatically(tmp_path: Path) -> None:
    script = ScriptedLLM(use("read_file", {"path": "app.py"}), say("li"))
    rig, repo, _ = _iso_rig(tmp_path, [script])
    result = (await rig.runner.spawn_many([TaskRequest("iso", "leia")], rig.parent))[0]
    assert result.status == "ok" and "no changes and was removed" in result.summary
    assert _git(repo, "worktree", "list").strip().count("\n") == 0  # só o checkout principal


async def test_paths_are_anchored_at_the_worktree_root(tmp_path: Path) -> None:
    script = ScriptedLLM(use("read_file", {"path": "app.py"}), use("glob", {"pattern": "*.py"}), say("ok"))
    rig, _, _ = _iso_rig(tmp_path, [script])
    await rig.runner.spawn_many([TaskRequest("iso", "x")], rig.parent)
    tool_msgs = [m for m in script.requests[-1] if m.role.value == "user"]
    joined = " ".join(b.content if isinstance(b.content, str) else "" for m in tool_msgs for b in m.blocks)
    assert "original" in joined and "app.py" in joined  # relativo resolveu DENTRO do worktree


async def test_run_command_defaults_to_the_worktree_cwd(tmp_path: Path) -> None:
    script = ScriptedLLM(use("run_command", {"command": "pwd"}), say("ok"))
    rig, _, _ = _iso_rig(tmp_path, [script])
    await rig.runner.spawn_many([TaskRequest("iso", "x")], rig.parent)
    outputs = " ".join(
        b.content if isinstance(b.content, str) else ""
        for m in script.requests[-1]
        for b in m.blocks
        if b.type == "tool_result"
    )
    assert "worktrees" in outputs and str(tmp_path / "ws") not in outputs.replace("worktrees", "")


async def test_pep_denies_cwd_and_reads_outside_the_worktree(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("segredo")
    script = ScriptedLLM(
        use("run_command", {"command": "ls", "cwd": str(tmp_path / "ws")}),  # o workspace REAL
        use("read_file", {"path": str(secret)}),
        use("grep", {"pattern": "original", "path": str(tmp_path / "ws")}),
        say("tentei"),
    )
    rig, _, _ = _iso_rig(tmp_path, [script])
    await rig.runner.spawn_many([TaskRequest("iso", "x")], rig.parent)
    feedback = " ".join(
        b.content if isinstance(b.content, str) else ""
        for m in script.requests[-1]
        for b in m.blocks
        if b.type == "tool_result"
    )
    assert feedback.count("PEP denied") == 3 and "segredo" not in feedback and "original" not in feedback


async def test_isolation_failure_outside_git_never_calls_the_model(tmp_path: Path) -> None:
    plain = tmp_path / "ws"
    plain.mkdir()
    port = _port(tmp_path, plain)
    rig = make_rig(tmp_path, [ScriptedLLM(say("não roda"))], extra_agents={"iso": ISOLATED}, workspace_port=port)
    result = (await rig.runner.spawn_many([TaskRequest("iso", "x")], rig.parent))[0]
    assert result.status == "error" and "refusing to run unisolated" in result.summary
    assert rig.gateway.made == []  # falhou fechado: nada rodou no workspace compartilhado


async def test_worktree_is_released_even_when_the_child_is_cancelled(tmp_path: Path) -> None:
    import asyncio

    started = asyncio.Event()

    async def hang() -> None:
        started.set()
        await asyncio.sleep(60)

    from tests.agent_helpers import FakeGateway

    repo = _repo(tmp_path / "ws")
    port = _port(tmp_path, repo)
    rig = make_rig(
        tmp_path, gateway=FakeGateway(scripts=[ScriptedLLM(say("x"))], on_call=hang),
        extra_agents={"iso": ISOLATED}, workspace_port=port, mode=AutonomyMode.FULLY_AUTO,
    )
    run = asyncio.create_task(rig.runner.spawn_many([TaskRequest("iso", "x")], rig.parent))
    await asyncio.wait_for(started.wait(), 3)
    assert len(port.active) == 1
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    assert port.active == [] and _git(repo, "worktree", "list").strip().count("\n") == 0
