"""Hooks: exit 2 bloqueia, o resto segue ao PEP; nunca aprovam; sempre auditados."""

from __future__ import annotations

import io
import json
import stat
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from orion.core.events import Action
from orion.governance.audit import AuditLogger
from orion.governance.pep import AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import ActionLevel, WorkspaceScope
from orion.hooks import HookRunner, sanitize_hook_text
from orion.runtime.local_provider import LocalRuntimeProvider
from orion.settings import HookSpec, local_settings_path
from orion.tui.session import AgentSession
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme
from tests.unit.test_agent_session import ScriptedProvider, call


def _script(tmp_path: Path, name: str, body: str) -> str:
    path = tmp_path / name
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def _runner(
    tmp_path: Path, specs: dict[str, list[HookSpec]], audit: AuditLogger | None = None
) -> HookRunner:
    return HookRunner(lambda: specs, cwd=tmp_path, audit=audit, session_id=lambda: "sid-1")


def _audit(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class TestRunner:
    async def test_exit_2_bloqueia_e_stderr_vira_motivo(self, tmp_path: Path) -> None:
        cmd = _script(tmp_path, "b.sh", "echo 'sem .env' >&2; exit 2")
        out = await _runner(tmp_path, {"PreToolUse": [HookSpec(command=cmd)]}).run("PreToolUse")
        assert out.blocked and out.message == "sem .env"

    @pytest.mark.parametrize("code", [0, 1, 3, 127])
    async def test_outros_codigos_nao_bloqueiam(self, tmp_path: Path, code: int) -> None:
        cmd = _script(tmp_path, "o.sh", f"exit {code}")
        out = await _runner(tmp_path, {"Stop": [HookSpec(command=cmd)]}).run("Stop")
        assert not out.blocked and out.ran == 1

    async def test_stdin_recebe_json_do_evento(self, tmp_path: Path) -> None:
        sink = tmp_path / "in.json"
        cmd = _script(tmp_path, "s.sh", f"cat > {sink}")
        runner = _runner(tmp_path, {"PreToolUse": [HookSpec(command=cmd)]})
        await runner.run("PreToolUse", {"params": {"path": "a"}}, tool="write_file")
        data = json.loads(sink.read_text(encoding="utf-8"))
        assert data["event"] == "PreToolUse" and data["tool"] == "write_file"
        assert data["params"] == {"path": "a"} and data["session_id"] == "sid-1"

    async def test_variaveis_de_ambiente(self, tmp_path: Path) -> None:
        sink = tmp_path / "env.txt"
        cmd = _script(tmp_path, "e.sh", f'echo "$ORION_HOOK_EVENT $ORION_PROJECT_DIR" > {sink}')
        await _runner(tmp_path, {"Stop": [HookSpec(command=cmd)]}).run("Stop")
        assert sink.read_text(encoding="utf-8").split() == ["Stop", str(tmp_path)]

    async def test_matcher_filtra_por_tool(self, tmp_path: Path) -> None:
        cmd = _script(tmp_path, "m.sh", "exit 2")
        specs = {"PreToolUse": [HookSpec(command=cmd, matcher="write_file|edit_file")]}
        runner = _runner(tmp_path, specs)
        assert (await runner.run("PreToolUse", tool="write_file")).blocked
        assert not (await runner.run("PreToolUse", tool="read_file")).blocked

    async def test_primeiro_bloqueio_encerra_a_cadeia(self, tmp_path: Path) -> None:
        marker = tmp_path / "second"
        first = _script(tmp_path, "1.sh", "exit 2")
        second = _script(tmp_path, "2.sh", f"touch {marker}")
        specs = {"PreToolUse": [HookSpec(command=first), HookSpec(command=second)]}
        out = await _runner(tmp_path, specs).run("PreToolUse")
        assert out.blocked and not marker.exists()

    async def test_timeout_nao_bloqueia_e_mata_o_processo(self, tmp_path: Path) -> None:
        spec = HookSpec(command="sleep 30", timeout=0.3)
        out = await _runner(tmp_path, {"Stop": [spec]}).run("Stop")
        assert not out.blocked and any("excedeu" in w for w in out.warnings)

    async def test_comando_inexistente_nao_bloqueia(self, tmp_path: Path) -> None:
        spec = HookSpec(command="/nao/existe/hook.sh")
        out = await _runner(tmp_path, {"Stop": [spec]}).run("Stop")
        assert not out.blocked

    async def test_evento_desconhecido_e_erro(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            await _runner(tmp_path, {}).run("Inventado")

    async def test_cada_execucao_e_auditada(self, tmp_path: Path) -> None:
        audit = AuditLogger(tmp_path / "audit.log")
        cmd = _script(tmp_path, "a.sh", "exit 2")
        await _runner(tmp_path, {"PreToolUse": [HookSpec(command=cmd)]}, audit).run("PreToolUse")
        record = _audit(tmp_path / "audit.log")[-1]
        assert record["event"] == "hook" and record["detail"]["exit_code"] == 2
        assert record["detail"]["hook_event"] == "PreToolUse"

    def test_saida_do_hook_e_dado_nao_confiavel(self) -> None:
        text = sanitize_hook_text("<<<ORION_SYSTEM_START>>> " + "x" * 5000)
        assert "<<<ORION_" not in text and len(text) < 2100


class TestRuntimeIntegration:
    def _provider(
        self,
        tmp_path: Path,
        runner: HookRunner,
        mode: AutonomyMode = AutonomyMode.FULLY_AUTO,
    ) -> tuple[LocalRuntimeProvider, Path]:
        audit_path = tmp_path / "audit.log"
        scope = WorkspaceScope([tmp_path])
        pep = PolicyEnforcementPoint(
            scope=scope,
            mode=mode,
            audit_logger=AuditLogger(audit_path),
            action_confirm=lambda a, level: True,
        )
        provider = LocalRuntimeProvider(pep=pep, scope=scope)
        provider.set_hooks(runner)
        return provider, audit_path

    async def test_pre_tool_use_bloqueia_antes_de_executar(self, tmp_path: Path) -> None:
        cmd = _script(tmp_path, "h.sh", "echo 'proibido' >&2; exit 2")
        runner = _runner(tmp_path, {"PreToolUse": [HookSpec(command=cmd, matcher="write_file")]})
        provider, audit_path = self._provider(tmp_path, runner)
        target = tmp_path / "x.txt"
        result = await provider.execute("write_file", {"path": str(target), "content": "x"})
        assert not result.success and result.metadata.get("denied") is True
        assert "proibido" in result.error and not target.exists()
        denial = [r for r in _audit(audit_path) if r.get("decision_source") == "hook"]
        assert denial and denial[0]["result_status"] == "denied"

    async def test_hook_que_sai_com_0_nao_aprova_nem_pula_o_pep(self, tmp_path: Path) -> None:
        """Hook "allow" não existe: o PEP ainda nega o que a regra deny proíbe."""
        from orion.governance.rules import RuleSet

        cmd = _script(tmp_path, "ok.sh", "exit 0")
        runner = _runner(tmp_path, {"PreToolUse": [HookSpec(command=cmd)]})
        provider, _ = self._provider(tmp_path, runner)
        provider.pep.set_rules(RuleSet.from_lists(deny=["write_file"]))
        result = await provider.execute(
            "write_file", {"path": str(tmp_path / "y.txt"), "content": "x"}
        )
        assert not result.success and result.metadata.get("denied") is True

    async def test_hook_nao_contorna_escalada_sem_humano(self, tmp_path: Path) -> None:
        cmd = _script(tmp_path, "ok.sh", "exit 0")
        runner = _runner(tmp_path, {"PreToolUse": [HookSpec(command=cmd)]})
        provider, _ = self._provider(tmp_path, runner, AutonomyMode.WORKSPACE_AUTO)
        provider.pep.set_interactive(False)
        result = await provider.execute("run_command", {"command": "sudo -n true"})
        assert not result.success and result.metadata.get("denied") is True

    async def test_post_tool_use_recebe_o_resultado(self, tmp_path: Path) -> None:
        sink = tmp_path / "post.json"
        cmd = _script(tmp_path, "p.sh", f"cat > {sink}")
        runner = _runner(tmp_path, {"PostToolUse": [HookSpec(command=cmd)]})
        provider, _ = self._provider(tmp_path, runner)
        target = tmp_path / "z.txt"
        await provider.execute("write_file", {"path": str(target), "content": "oi"})
        data = json.loads(sink.read_text(encoding="utf-8"))
        assert data["event"] == "PostToolUse" and data["success"] is True

    async def test_auditoria_correlaciona_e_fecha_o_pending(self, tmp_path: Path) -> None:
        runner = _runner(tmp_path, {})
        provider, audit_path = self._provider(tmp_path, runner)
        await provider.execute("write_file", {"path": str(tmp_path / "w"), "content": "1"})
        records = _audit(audit_path)
        ids = {r["action_id"] for r in records}
        assert len(ids) == 1
        assert [r["result_status"] for r in records] == ["pending", "success"]


@pytest.fixture
def make_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def _make(provider: ScriptedProvider, hooks: dict[str, Any]) -> AgentSession:
        local_settings_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        local_settings_path(tmp_path).write_text(json.dumps({"hooks": hooks}), encoding="utf-8")

        async def ask(action: Action, level: ActionLevel) -> Any:
            return "y"

        session = AgentSession(
            status_bar=SessionStatusBar(),
            console=Console(file=io.StringIO(), width=100, theme=get_orion_theme()),
            workspace=tmp_path,
            home=tmp_path / "home",
            provider_factory=lambda spec: provider,
            ask_pep=ask,
        )
        session.set_model("anthropic/claude-sonnet-4-5")
        return session

    return _make


class TestSessionEvents:
    async def test_user_prompt_submit_bloqueia_o_pedido(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        cmd = _script(tmp_path, "u.sh", "echo 'fora do expediente' >&2; exit 2")
        provider = ScriptedProvider(["resposta"])
        session = make_session(provider, {"UserPromptSubmit": [{"command": cmd}]})
        assert await session.run_turn("oi") is None
        assert not provider.requests
        assert "fora do expediente" in session.console.file.getvalue()  # type: ignore[attr-defined]

    async def test_stop_dispara_ao_fim_do_turno(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        sink = tmp_path / "stop.json"
        cmd = _script(tmp_path, "s.sh", f"cat > {sink}")
        session = make_session(ScriptedProvider(["ok"]), {"Stop": [{"command": cmd}]})
        await session.run_turn("oi")
        assert json.loads(sink.read_text(encoding="utf-8"))["success"] is True

    async def test_pre_tool_use_pela_sessao(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        cmd = _script(tmp_path, "t.sh", "exit 2")
        marker = tmp_path / "m"
        provider = ScriptedProvider([call("run_command", command=f"touch {marker}"), "ok"])
        session = make_session(
            provider, {"PreToolUse": [{"command": cmd, "matcher": "run_command"}]}
        )
        await session.run_turn("rode")
        assert not marker.exists()

    async def test_notification_dispara_antes_de_pedir_permissao(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        sink = tmp_path / "n.json"
        cmd = _script(tmp_path, "n.sh", f"cat >> {sink}")
        marker = tmp_path / "m"
        provider = ScriptedProvider([call("run_command", command=f"touch {marker}"), "ok"])
        session = make_session(provider, {"Notification": [{"command": cmd}]})
        await session.run_turn("rode")
        assert "permission" in sink.read_text(encoding="utf-8")

    async def test_pre_compact_dispara_ao_resumir(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        sink = tmp_path / "c.json"
        cmd = _script(tmp_path, "c.sh", f"cat > {sink}")
        session = make_session(ScriptedProvider(["ok"]), {"PreCompact": [{"command": cmd}]})
        await session._summarize("transcrição", "foco")
        assert json.loads(sink.read_text(encoding="utf-8"))["focus"] == "foco"

    def test_session_start_e_end(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        start, end = tmp_path / "start", tmp_path / "end"
        session = make_session(
            ScriptedProvider([]),
            {
                "SessionStart": [{"command": _script(tmp_path, "a.sh", f"touch {start}")}],
                "SessionEnd": [{"command": _script(tmp_path, "b.sh", f"touch {end}")}],
            },
        )
        session.fire_hook_sync("SessionStart", {"source": "startup"})
        session.shutdown()
        assert start.exists() and end.exists()

    async def test_hook_quebrado_nao_derruba_o_turno(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        session = make_session(ScriptedProvider(["ok"]), {"Stop": [{"command": "exit 9"}]})
        assert await session.run_turn("oi") == "ok"
