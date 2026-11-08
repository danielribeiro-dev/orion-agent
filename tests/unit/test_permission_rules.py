"""Regras declarativas (deny > ask > allow), escalada com pergunta e seus limites."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from orion.core.events import Action, RiskLevel
from orion.governance.audit import AuditLogger
from orion.governance.pep import ActionDenied, AutonomyMode, PolicyEnforcementPoint, Rejection
from orion.governance.permissions import ActionLevel, WorkspaceScope
from orion.governance.rules import (
    RuleSet,
    command_segments,
    is_complex_command,
    parse_rule,
    rule_text_for,
)
from orion.settings import local_settings_path
from orion.tui.session import AgentMode, AgentSession
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme
from tests.unit.test_agent_session import ScriptedProvider, call

# ── Parser e matcher ─────────────────────────────────────────────────────────


class TestParsing:
    def test_tool_sem_padrao(self) -> None:
        rule = parse_rule("deny", "mcp__srv__*")
        assert rule and rule.tool == "mcp__srv__*" and rule.pattern is None

    def test_tool_com_padrao(self) -> None:
        rule = parse_rule("allow", "run_command(git status:*)")
        assert rule and (rule.tool, rule.pattern) == ("run_command", "git status:*")

    def test_padrao_com_parenteses(self) -> None:
        rule = parse_rule("allow", "run_command(echo (a))")
        assert rule and rule.pattern == "echo (a)"

    def test_texto_invalido(self) -> None:
        assert parse_rule("deny", "") is None

    def test_rule_text_for_comando_e_caminho(self) -> None:
        assert rule_text_for("run_command", {"command": "npm test"}) == "run_command(npm test)"
        assert rule_text_for("write_file", {"path": "a.py"}) == "write_file(a.py)"
        assert rule_text_for("recall", {}) == "recall"


class TestMatching:
    def test_prefixo_com_fronteira_de_palavra(self) -> None:
        rules = RuleSet.from_lists(allow=["run_command(git status:*)"])
        assert rules.match("run_command", {"command": "git status"})
        assert rules.match("run_command", {"command": "git status -s"})
        assert not rules.match("run_command", {"command": "git statusx"})

    def test_allow_nao_casa_comando_composto(self) -> None:
        rules = RuleSet.from_lists(allow=["run_command(git status:*)"])
        for cmd in (
            "git status && rm -rf x",
            "git status; rm x",
            "git status | sh",
            "git status > /etc/passwd",
            "git status $(rm x)",
            "git status `rm x`",
        ):
            assert rules.match("run_command", {"command": cmd}) is None, cmd

    def test_deny_casa_qualquer_trecho_do_composto(self) -> None:
        rules = RuleSet.from_lists(deny=["run_command(rm -rf:*)"])
        assert rules.match("run_command", {"command": "cd x && rm -rf build"})

    def test_deny_vence_ask_vence_allow(self) -> None:
        rules = RuleSet.from_lists(
            allow=["run_command(git push:*)"],
            ask=["run_command(git push:*)"],
            deny=["run_command(git push --force:*)"],
        )
        forced = rules.match("run_command", {"command": "git push --force origin"})
        assert forced and forced.effect == "deny"
        plain = rules.match("run_command", {"command": "git push origin"})
        assert plain and plain.effect == "ask"

    def test_glob_de_nome_de_tool(self) -> None:
        rules = RuleSet.from_lists(deny=["mcp__srv__*"])
        assert rules.match("mcp__srv__delete", {})
        assert rules.match("mcp__outro__delete", {}) is None

    def test_deny_de_caminho_pega_em_qualquer_diretorio(self, tmp_path: Path) -> None:
        rules = RuleSet.from_lists(deny=["write_file(.env)"])
        assert rules.match("write_file", {"path": str(tmp_path / "sub" / ".env")}, [tmp_path])

    def test_allow_de_caminho_relativo_ancora_no_workspace(self, tmp_path: Path) -> None:
        rules = RuleSet.from_lists(allow=["write_file(README.md)"])
        assert rules.match("write_file", {"path": str(tmp_path / "README.md")}, [tmp_path])
        assert rules.match("write_file", {"path": "/etc/README.md"}, [tmp_path]) is None

    def test_helpers_de_comando(self) -> None:
        assert command_segments("a && b | c; d") == ["a", "b", "c", "d"]
        assert is_complex_command("a && b") and not is_complex_command("git log -n 3")


# ── PEP ──────────────────────────────────────────────────────────────────────


def _action(tool: str, params: dict[str, Any]) -> Action:
    return Action(tool=tool, params=params, risk_level=RiskLevel.SAFE)


def _pep(
    tmp_path: Path,
    *,
    mode: AutonomyMode = AutonomyMode.WORKSPACE_AUTO,
    rules: RuleSet | None = None,
    answer: Any = True,
    asked: list[Action] | None = None,
) -> PolicyEnforcementPoint:
    def confirm(action: Action, level: ActionLevel) -> Any:
        if asked is not None:
            asked.append(action)
        return answer

    return PolicyEnforcementPoint(
        scope=WorkspaceScope([tmp_path]),
        mode=mode,
        audit_logger=AuditLogger(tmp_path / "audit.log"),
        action_confirm=confirm,
        rules=rules,
    )


def _audit(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / "audit.log"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


class TestPepRules:
    async def test_deny_bloqueia_mesmo_em_fully_auto(self, tmp_path: Path) -> None:
        pep = _pep(tmp_path, mode=AutonomyMode.FULLY_AUTO, rules=RuleSet.from_lists(deny=["run_command(git push:*)"]))
        with pytest.raises(ActionDenied, match="deny rule"):
            await pep.evaluate(_action("run_command", {"command": "git push origin main"}))
        assert _audit(tmp_path)[-1]["decision_source"] == "rule"

    async def test_deny_vence_allow(self, tmp_path: Path) -> None:
        rules = RuleSet.from_lists(allow=["run_command(git:*)"], deny=["run_command(git push:*)"])
        pep = _pep(tmp_path, rules=rules)
        with pytest.raises(ActionDenied):
            await pep.evaluate(_action("run_command", {"command": "git push"}))
        assert await pep.evaluate(_action("run_command", {"command": "git status"})) is True

    async def test_deny_vale_ate_para_leitura(self, tmp_path: Path) -> None:
        pep = _pep(tmp_path, rules=RuleSet.from_lists(deny=["read_file(.env)"]))
        with pytest.raises(ActionDenied):
            await pep.evaluate(_action("read_file", {"path": str(tmp_path / ".env")}))

    async def test_allow_dispensa_pergunta_em_level_3(self, tmp_path: Path) -> None:
        asked: list[Action] = []
        pep = _pep(tmp_path, rules=RuleSet.from_lists(allow=["run_command(git status:*)"]), asked=asked)
        assert await pep.evaluate(_action("run_command", {"command": "git status -s"})) is True
        assert asked == []
        assert _audit(tmp_path)[-1]["decision_source"] == "rule"

    async def test_sem_regra_ainda_pergunta(self, tmp_path: Path) -> None:
        asked: list[Action] = []
        pep = _pep(tmp_path, rules=RuleSet.from_lists(allow=["run_command(git status:*)"]), asked=asked)
        await pep.evaluate(_action("run_command", {"command": "git commit -m x"}))
        assert len(asked) == 1

    async def test_ask_forca_pergunta_em_fully_auto(self, tmp_path: Path) -> None:
        asked: list[Action] = []
        pep = _pep(tmp_path, mode=AutonomyMode.FULLY_AUTO, rules=RuleSet.from_lists(ask=["run_command(git push:*)"]), asked=asked)
        await pep.evaluate(_action("run_command", {"command": "git push"}))
        assert len(asked) == 1

    async def test_ask_recusado_nao_executa(self, tmp_path: Path) -> None:
        pep = _pep(tmp_path, mode=AutonomyMode.FULLY_AUTO, rules=RuleSet.from_lists(ask=["run_command(git push:*)"]), answer=False)
        assert await pep.evaluate(_action("run_command", {"command": "git push"})) is False

    async def test_ask_vale_para_leitura(self, tmp_path: Path) -> None:
        asked: list[Action] = []
        pep = _pep(tmp_path, rules=RuleSet.from_lists(ask=["read_file(secrets/**)"]), asked=asked)
        await pep.evaluate(_action("read_file", {"path": str(tmp_path / "secrets" / "k")}))
        assert len(asked) == 1


class TestPlanModeAndRules:
    async def test_allow_nao_fura_modo_somente_leitura(self, tmp_path: Path) -> None:
        pep = _pep(tmp_path, mode=AutonomyMode.SUPERVISED, rules=RuleSet.from_lists(allow=["write_file"]))
        pep.set_read_only(True)
        action = _action("write_file", {"path": str(tmp_path / "a"), "content": "x"})
        assert await pep.evaluate(action) is False
        assert "plan mode" in (pep.take_rejection_reason(action.event_id) or "")

    async def test_leitura_continua_no_modo_somente_leitura(self, tmp_path: Path) -> None:
        pep = _pep(tmp_path)
        pep.set_read_only(True)
        assert await pep.evaluate(_action("read_file", {"path": str(tmp_path / "a")})) is True


class TestEscalation:
    async def test_allow_nao_libera_sudo(self, tmp_path: Path) -> None:
        asked: list[Action] = []
        pep = _pep(tmp_path, rules=RuleSet.from_lists(allow=["run_command(sudo:*)"]), asked=asked)
        await pep.evaluate(_action("run_command", {"command": "sudo apt update"}))
        assert len(asked) == 1
        assert _audit(tmp_path)[-1]["decision_source"] == "user_escalation"

    async def test_sudo_dentro_de_comando_composto_e_detectado(self, tmp_path: Path) -> None:
        asked: list[Action] = []
        pep = _pep(tmp_path, asked=asked)
        await pep.evaluate(_action("run_command", {"command": "echo ok;sudo reboot"}))
        assert len(asked) == 1

    async def test_motivo_visivel_durante_a_pergunta(self, tmp_path: Path) -> None:
        seen: list[str | None] = []
        holder: dict[str, PolicyEnforcementPoint] = {}

        def confirm(action: Action, level: ActionLevel) -> bool:
            seen.append(holder["pep"].peek_escalation(action.event_id))
            return True

        pep = PolicyEnforcementPoint(
            scope=WorkspaceScope([tmp_path]),
            mode=AutonomyMode.WORKSPACE_AUTO,
            audit_logger=AuditLogger(tmp_path / "audit.log"),
            action_confirm=confirm,
        )
        holder["pep"] = pep
        action = _action("run_command", {"command": "sudo ls"})
        await pep.evaluate(action)
        assert seen and "sudo" in (seen[0] or "")
        assert pep.peek_escalation(action.event_id) is None

    async def test_allow_absoluto_cobre_fora_do_workspace(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "fora"
        asked: list[Action] = []
        rules = RuleSet.from_lists(allow=[f"write_file({outside}/**)"])
        pep = _pep(tmp_path, rules=rules, asked=asked)
        action = _action("write_file", {"path": str(outside / "a.txt"), "content": "x"})
        assert await pep.evaluate(action) is True
        assert asked == []

    async def test_allow_relativo_nao_cobre_fora_do_workspace(self, tmp_path: Path) -> None:
        asked: list[Action] = []
        pep = _pep(tmp_path, rules=RuleSet.from_lists(allow=["write_file(a.txt)"]), asked=asked)
        action = _action("write_file", {"path": "/etc/a.txt", "content": "x"})
        await pep.evaluate(action)
        assert len(asked) == 1

    async def test_edicao_que_adiciona_sudo_pergunta_de_novo(self, tmp_path: Path) -> None:
        answers = iter([{"command": "sudo touch x"}, False])
        asked: list[Action] = []

        def confirm(action: Action, level: ActionLevel) -> Any:
            asked.append(action)
            return next(answers)

        pep = PolicyEnforcementPoint(
            scope=WorkspaceScope([tmp_path]),
            mode=AutonomyMode.WORKSPACE_AUTO,
            audit_logger=AuditLogger(tmp_path / "audit.log"),
            action_confirm=confirm,
        )
        action = _action("run_command", {"command": "touch x"})
        assert await pep.evaluate(action) is False
        assert len(asked) == 2
        assert pep.take_edited_params(action.event_id) is None

    async def test_edicao_nao_escapa_de_deny(self, tmp_path: Path) -> None:
        pep = _pep(
            tmp_path,
            rules=RuleSet.from_lists(deny=["run_command(rm -rf:*)"]),
            answer={"command": "rm -rf build"},
        )
        with pytest.raises(ActionDenied):
            await pep.evaluate(_action("run_command", {"command": "touch x"}))

    async def test_rejection_do_usuario_chega_ao_modelo(self, tmp_path: Path) -> None:
        pep = _pep(tmp_path, answer=Rejection("nope"))
        action = _action("run_command", {"command": "sudo ls"})
        assert await pep.evaluate(action) is False
        assert pep.take_rejection_reason(action.event_id) == "nope"

    async def test_nuclear_continua_com_desafio_do_so(self, tmp_path: Path) -> None:
        pep = _pep(tmp_path, mode=AutonomyMode.FULLY_AUTO, rules=RuleSet.from_lists(allow=["run_command"]))
        with pytest.raises(ActionDenied, match="Nuclear"):
            await pep.evaluate(_action("run_command", {"command": "rm -rf /"}))


class TestAuditTrail:
    async def test_resultado_fecha_o_pending(self, tmp_path: Path) -> None:
        pep = _pep(tmp_path)
        action = _action("write_file", {"path": str(tmp_path / "a"), "content": "x"})
        await pep.evaluate(action)
        pep.record_result(action.event_id, "write_file", True)
        records = [r for r in _audit(tmp_path) if r["action_id"] == action.event_id]
        assert [r["result_status"] for r in records] == ["pending", "success"]

    async def test_sem_humano_registra_negacao(self, tmp_path: Path) -> None:
        pep = _pep(tmp_path)
        pep.set_interactive(False)
        with pytest.raises(ActionDenied):
            await pep.evaluate(_action("run_command", {"command": "sudo ls"}))
        last = _audit(tmp_path)[-1]
        assert last["result_status"] == "denied" and "escalation_no_human" in last["denial_reason"]


# ── Sessão ───────────────────────────────────────────────────────────────────


@pytest.fixture
def make_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def _make(provider: ScriptedProvider, answers: list[Any]) -> AgentSession:
        pending = list(answers)

        async def ask(action: Action, level: ActionLevel) -> Any:
            return pending.pop(0)

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


class TestSession:
    async def test_sempre_permitir_grava_regra_local_0600(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        marker = tmp_path / "m"
        provider = ScriptedProvider([call("run_command", command=f"touch {marker}"), "ok"])
        session = make_session(provider, ["a"])
        await session.run_turn("rode")
        data = json.loads(local_settings_path(tmp_path).read_text(encoding="utf-8"))
        assert data["permissions"]["allow"] == [f"run_command(touch {marker})"]
        assert (local_settings_path(tmp_path).stat().st_mode & 0o777) == 0o600
        assert session.settings.effective.permissions.allow

    async def test_regra_persistida_vale_na_proxima_sessao(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        marker = tmp_path / "m"
        command = f"touch {marker}"
        first = make_session(ScriptedProvider([call("run_command", command=command), "ok"]), ["a"])
        await first.run_turn("rode")
        marker.unlink()
        second = make_session(ScriptedProvider([call("run_command", command=command), "ok"]), [])
        await second.run_turn("rode")  # sem resposta pendente: se perguntasse, falharia
        assert marker.exists()

    async def test_comando_composto_fica_so_na_sessao(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        command = f"touch {tmp_path / 'x'} && true"
        provider = ScriptedProvider([call("run_command", command=command), "ok"])
        session = make_session(provider, ["a"])
        await session.run_turn("rode")
        assert not local_settings_path(tmp_path).exists()
        assert session.always_allowed

    async def test_escalada_nao_vira_sempre(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        provider = ScriptedProvider([call("run_command", command="sudo -n true"), "ok"])
        session = make_session(provider, ["a"])
        await session.run_turn("rode")
        assert not local_settings_path(tmp_path).exists()
        assert not session.always_allowed

    async def test_modo_plano_continua_somente_leitura_com_allow(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        local_settings_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        local_settings_path(tmp_path).write_text(
            json.dumps({"permissions": {"allow": ["write_file"]}}), encoding="utf-8"
        )
        target = tmp_path / "novo.txt"
        provider = ScriptedProvider([call("write_file", path=str(target), content="x"), "ok"])
        session = make_session(provider, [])
        session.set_mode(AgentMode.PLAN)
        await session.run_turn("escreva")
        assert not target.exists()

    async def test_deny_do_settings_bloqueia_na_sessao(self, make_session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        local_settings_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        local_settings_path(tmp_path).write_text(
            json.dumps({"permissions": {"deny": ["run_command(touch:*)"]}}), encoding="utf-8"
        )
        marker = tmp_path / "m"
        provider = ScriptedProvider([call("run_command", command=f"touch {marker}"), "ok"])
        session = make_session(provider, [])
        session.set_mode(AgentMode.AUTO)
        await session.run_turn("rode")
        assert not marker.exists()
