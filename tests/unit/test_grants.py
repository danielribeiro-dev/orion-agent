"""v0.5.3 Sprint 2 — aprovação por intenção (ADR-047 item 5)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from orion.core.events import Action
from orion.governance.audit import AuditLogger
from orion.governance.bands import Band
from orion.governance.grants import DEFAULT_TTL_S, GrantStore
from orion.governance.pep import ActionDenied, AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import WorkspaceScope


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TestStore:
    def test_command_matching(self) -> None:
        store = GrantStore()
        grant = store.issue(commands=["git push origin main", "docker compose up *"])
        assert grant is not None
        assert grant.covers("run_command", {"command": "git  push  origin main"})
        assert not grant.covers("run_command", {"command": "git push --force origin main"})
        assert not grant.covers("run_command", {"command": "git push origin main; rm -rf x"})
        assert grant.covers("run_command", {"command": "docker compose up -d web"})
        assert not grant.covers("run_command", {"command": "docker compose down"})

    def test_path_matching(self, tmp_path: Path) -> None:
        grant = GrantStore().issue(paths=[str(tmp_path / "deploy")])
        assert grant is not None
        assert grant.covers("write_file", {"path": str(tmp_path / "deploy" / "a.yml")})
        assert not grant.covers("write_file", {"path": str(tmp_path / "deploy-x" / "a.yml")})
        assert not grant.covers("write_file", {"path": str(tmp_path / "deploy" / ".." / "fora.yml")})
        assert not grant.covers("run_command", {"command": f"rm {tmp_path / 'deploy'}"})

    def test_ttl_and_nuclear(self) -> None:
        clock = Clock()
        store = GrantStore(clock=clock)
        store.issue(commands=["git push origin main"])
        params = {"command": "git push origin main"}
        assert store.match("run_command", params, Band.PRESENCA) is not None
        assert store.match("run_command", params, Band.NUCLEAR) is None
        clock.now += DEFAULT_TTL_S + 1
        assert store.match("run_command", params, Band.PRESENCA) is None
        assert DEFAULT_TTL_S == 15 * 60

    def test_empty_grant_is_not_created(self) -> None:
        assert GrantStore().issue(commands=["  "], paths=[]) is None


def pep(tmp_path: Path, asked: list[str], **kw: Any) -> PolicyEnforcementPoint:
    p = PolicyEnforcementPoint(
        scope=WorkspaceScope([tmp_path]),
        mode=AutonomyMode.WORKSPACE_AUTO,
        audit_logger=AuditLogger(tmp_path / "audit.log"),
        confirm=lambda prompt: asked.append(prompt) or False,
        **kw,
    )
    p.configure_bands(current_branch=lambda _p: "main")
    return p


class TestPep:
    async def test_grant_skips_presence_question_and_is_audited(self, tmp_path: Path) -> None:
        asked: list[str] = []
        gate = pep(tmp_path, asked)
        action = Action(tool="run_command", params={"command": "git push origin main"})
        assert await gate.evaluate(action) is False and len(asked) == 1  # sem grant: pergunta
        grant = gate.issue_grant(commands=["git push origin main"])
        assert grant is not None
        assert await gate.evaluate(Action(tool="run_command", params={"command": "git push origin main"}))
        assert len(asked) == 1
        audit = (tmp_path / "audit.log").read_text()
        assert f'"decision_source": "grant:{grant.id}"' in audit

    async def test_grant_never_covers_nuclear(self, tmp_path: Path) -> None:
        gate = pep(tmp_path, [])
        gate.issue_grant(commands=["git push --force origin main"])
        with pytest.raises(ActionDenied, match="Nuclear"):
            await gate.evaluate(Action(tool="run_command", params={"command": "git push --force origin main"}))

    async def test_grant_never_covers_blocklist(self, tmp_path: Path) -> None:
        gate = pep(tmp_path, [])
        gate.issue_grant(commands=["rm -rf /"])
        with pytest.raises(ActionDenied, match="blocklist"):
            await gate.evaluate(Action(tool="run_command", params={"command": "rm -rf /"}))


class TestPlanApproval:
    async def test_plan_with_presence_steps_issues_grant(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from orion.tui.session import AgentMode, AgentSession
        from orion.tui.status_bar import SessionStatusBar
        from orion.tui.theme import get_orion_theme

        seen: dict[str, Any] = {}

        async def approve(console: Any, plan: str, mode_label: str, steps: list[str] | None = None) -> bool:
            seen["steps"] = steps
            return True

        monkeypatch.setattr("orion.tui.modal.approve_plan", approve)
        (tmp_path / "ws").mkdir()
        session = AgentSession(
            status_bar=SessionStatusBar(),
            console=Console(file=io.StringIO(), theme=get_orion_theme()),
            workspace=tmp_path / "ws",
            home=tmp_path / "home",
            ask_pep=lambda *_: _never(),
        )
        session.set_mode(AgentMode.PLAN)
        result = await session.runtime.execute(
            "exit_plan_mode",
            {"plan": "# Plano\n1. publicar", "presence_commands": ["docker system prune -af"]},
        )
        assert result.success and seen["steps"] == ["docker system prune -af"]
        assert session.mode is AgentMode.AUTO
        assert [g.commands for g in session.pep.grants.active()] == [("docker system prune -af",)]
        assert await session.pep.evaluate(Action(tool="run_command", params={"command": "docker system prune -af"}))

    def test_modal_lists_the_steps(self) -> None:
        from orion.tui.panels import render_plan_approval
        from orion.tui.theme import get_orion_theme

        console = Console(file=io.StringIO(), width=100, theme=get_orion_theme())
        console.print(render_plan_approval("# Plano", "auto", ["git push origin main"]))
        text = console.file.getvalue()  # type: ignore[attr-defined]
        assert "Passos de presença" in text and "› git push origin main" in text and "Aprovar o plano" in text


async def _never() -> Any:
    raise AssertionError("não deveria perguntar")
