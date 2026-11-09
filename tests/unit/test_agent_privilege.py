"""Privilégio só diminui (ADR-028): teto no PEP, interseção de tools, sem humano = nega."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from orion.agents.runner import TaskRequest
from orion.core.events import Action
from orion.gateway.circuit_breaker import CircuitBreaker, FailureReason
from orion.gateway.models import ComplexityTier
from orion.governance.audit import AuditLogger
from orion.governance.pep import ActionDenied, AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import WorkspaceScope
from orion.governance.rules import RuleSet
from orion.runtime.tools.ask_user import AskUserTool
from orion.runtime.tools.todo_write import TodoWriteTool
from tests.agent_helpers import make_rig
from tests.llm_script import ScriptedLLM, say, use


def _action(tool: str, **params: Any) -> Action:
    return Action(tool=tool, params=params)


def _parent(tmp_path: Path, mode: AutonomyMode, **kwargs: Any) -> PolicyEnforcementPoint:
    scope = WorkspaceScope([tmp_path])
    return PolicyEnforcementPoint(
        scope=scope, mode=mode, audit_logger=AuditLogger(tmp_path / "audit.log"),
        confirm=lambda _p: True, **kwargs,
    )


def _child(parent: PolicyEnforcementPoint, **kwargs: Any) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint.for_subagent(parent, agent_id="agent_abc123", **kwargs)


# ── PEP: teto do pai ────────────────────────────────────────────────────────


def test_child_mode_is_min_of_parent_and_requested(tmp_path: Path) -> None:
    parent = _parent(tmp_path, AutonomyMode.SUPERVISED)
    assert _child(parent, mode=AutonomyMode.FULLY_AUTO).mode == AutonomyMode.SUPERVISED
    parent.set_mode(AutonomyMode.WORKSPACE_AUTO)
    child = _child(parent, mode=AutonomyMode.FULLY_AUTO)
    assert child.mode == AutonomyMode.WORKSPACE_AUTO
    # o modo ATUAL do pai segue limitando depois da criação
    parent.set_mode(AutonomyMode.FULLY_AUTO)
    assert child.mode == AutonomyMode.WORKSPACE_AUTO  # pediu no máximo workspace_auto
    parent.set_mode(AutonomyMode.SUPERVISED)
    assert child.mode == AutonomyMode.SUPERVISED


async def test_child_can_never_be_interactive(tmp_path: Path) -> None:
    child = _child(_parent(tmp_path, AutonomyMode.FULLY_AUTO))
    assert child.interactive is False
    with pytest.raises(ValueError):
        child.set_interactive(True)


async def test_non_interactive_denies_every_ask(tmp_path: Path) -> None:
    pep = _parent(tmp_path, AutonomyMode.SUPERVISED)
    pep.set_interactive(False)
    with pytest.raises(ActionDenied, match="no human"):
        await pep.evaluate(_action("write_file", path=str(tmp_path / "a.txt"), content="x"))
    # leitura continua livre
    assert await pep.evaluate(_action("read_file", path=str(tmp_path / "a.txt")))


async def test_child_supervised_parent_denies_writes_but_not_reads(tmp_path: Path) -> None:
    child = _child(_parent(tmp_path, AutonomyMode.SUPERVISED))
    with pytest.raises(ActionDenied):
        await child.evaluate(_action("write_file", path=str(tmp_path / "a.txt"), content="x"))
    assert await child.evaluate(_action("read_file", path=str(tmp_path / "a.txt")))


async def test_child_workspace_auto_writes_inside_but_not_outside(tmp_path: Path) -> None:
    child = _child(_parent(tmp_path, AutonomyMode.WORKSPACE_AUTO))
    assert await child.evaluate(_action("write_file", path=str(tmp_path / "a.txt"), content="x"))
    with pytest.raises(ActionDenied, match="workspace"):
        await child.evaluate(_action("write_file", path="/etc/evil.conf", content="x"))


async def test_child_run_command_is_denied_below_fully_auto(tmp_path: Path) -> None:
    child = _child(_parent(tmp_path, AutonomyMode.WORKSPACE_AUTO))
    with pytest.raises(ActionDenied):
        await child.evaluate(_action("run_command", command="ls"))


async def test_parent_deny_and_ask_rules_bind_the_child(tmp_path: Path) -> None:
    rules = RuleSet.from_lists(deny=["write_file(*.secret)"], ask=["write_file(*.cfg)"])
    parent = _parent(tmp_path, AutonomyMode.FULLY_AUTO, rules=rules)
    child = _child(parent)
    with pytest.raises(ActionDenied, match="deny rule"):
        await child.evaluate(_action("write_file", path=str(tmp_path / "x.secret"), content="x"))
    # ask do pai + sem humano = negado (não vira "allow" por estar em FULLY_AUTO)
    with pytest.raises(ActionDenied, match="no human"):
        await child.evaluate(_action("write_file", path=str(tmp_path / "x.cfg"), content="x"))
    assert await child.evaluate(_action("write_file", path=str(tmp_path / "x.txt"), content="x"))
    # o deny também vale se aparecer DEPOIS da criação do filho (regras vivas)
    parent.set_rules(RuleSet.from_lists(deny=["write_file(*.txt)"]))
    with pytest.raises(ActionDenied, match="deny rule"):
        await child.evaluate(_action("write_file", path=str(tmp_path / "y.txt"), content="x"))


async def test_parent_allow_rules_are_not_inherited(tmp_path: Path) -> None:
    parent = _parent(tmp_path, AutonomyMode.SUPERVISED, rules=RuleSet.from_lists(allow=["write_file(*.txt)"]))
    assert await parent.evaluate(_action("write_file", path=str(tmp_path / "a.txt"), content="x"))
    child = _child(parent)
    with pytest.raises(ActionDenied, match="no human"):  # sem allow herdado: cai no ask -> nega
        await child.evaluate(_action("write_file", path=str(tmp_path / "a.txt"), content="x"))


async def test_child_has_no_trust_ledger_and_never_prompts(tmp_path: Path) -> None:
    ledger = MagicMock()
    ledger.lookup.return_value = MagicMock(is_trusted=True)
    parent = _parent(tmp_path, AutonomyMode.WORKSPACE_AUTO, trust_ledger=ledger)
    child = _child(parent)
    with pytest.raises(ActionDenied):
        await child.evaluate(_action("run_command", command="ls"))  # ledger do pai não vale
    ledger.lookup.assert_not_called()
    assert child.ceiling is parent and child.agent_id == "agent_abc123"


async def test_nuclear_is_denied_for_child_without_opening_the_os_prompt(tmp_path: Path) -> None:
    parent = _parent(tmp_path, AutonomyMode.FULLY_AUTO)
    child = _child(parent)
    with patch.object(child._nuclear_gate, "challenge") as challenge, pytest.raises(
        ActionDenied, match="nuclear"
    ):
        await child.evaluate(_action("run_command", command="rm -rf /"))
    challenge.assert_not_called()


async def test_plan_mode_of_parent_is_inherited_live(tmp_path: Path) -> None:
    parent = _parent(tmp_path, AutonomyMode.FULLY_AUTO)
    child = _child(parent)
    action = _action("write_file", path=str(tmp_path / "a.txt"), content="x")
    assert await child.evaluate(action)
    parent.set_read_only(True)
    assert await child.evaluate(_action("write_file", path=str(tmp_path / "b.txt"), content="x")) is False


async def test_safe_holding_of_parent_blocks_child_mutations(tmp_path: Path) -> None:
    breaker = CircuitBreaker(primary_model_id="m", primary_model_tier=ComplexityTier.HEAVY)
    parent = _parent(tmp_path, AutonomyMode.FULLY_AUTO, circuit_breaker=breaker)
    child = _child(parent)
    breaker.trip(FailureReason.SERVER_ERROR, "m")
    assert breaker.is_mutation_blocked()
    with pytest.raises(ActionDenied):
        await child.evaluate(_action("write_file", path=str(tmp_path / "a.txt"), content="x"))


async def test_child_cwd_must_stay_in_its_scope(tmp_path: Path) -> None:
    child = _child(_parent(tmp_path, AutonomyMode.FULLY_AUTO))
    with pytest.raises(ActionDenied, match="cwd"):
        await child.evaluate(_action("glob", pattern="*", cwd="/etc"))
    assert await child.evaluate(_action("glob", pattern="*", cwd=str(tmp_path)))


async def test_child_audit_records_carry_agent_id(tmp_path: Path) -> None:
    parent = _parent(tmp_path, AutonomyMode.SUPERVISED)
    child = _child(parent)
    with pytest.raises(ActionDenied):
        await child.evaluate(_action("write_file", path=str(tmp_path / "a.txt"), content="x"))
    lines = [json.loads(x) for x in (tmp_path / "audit.log").read_text().splitlines()]
    assert lines and lines[-1]["agent_id"] == "agent_abc123"
    assert lines[-1]["result_status"] == "denied" and lines[-1]["denial_reason"] == "ask_no_human"


# ── Runner: interseção de tools e comportamento do filho ────────────────────


class _StubParentRuntime:
    """Pai que NÃO tem write_file: nenhum filho pode usá-lo."""

    available_tools = ["read_file", "glob", "grep", "task"]

    def get_tool(self, name: str) -> Any:
        return None


def _tool_names(script: ScriptedLLM) -> set[str]:
    return {t.name for t in script.tools[0]}


async def test_child_never_gets_tools_the_parent_lacks(tmp_path: Path) -> None:
    script = ScriptedLLM(say("ok"))
    rig = make_rig(
        tmp_path, [script],
        extra_agents={"w": "---\nname: w\ndescription: d\ntools: [read_file, write_file, run_command]\n---\nbody\n"},
    )
    rig.parent.runtime = _StubParentRuntime()
    result = (await rig.runner.spawn_many([TaskRequest("w", "faça")], rig.parent))[0]
    assert result.status == "ok"
    assert _tool_names(script) == {"read_file"}


async def test_forbidden_tools_are_removed_even_when_declared(tmp_path: Path) -> None:
    script = ScriptedLLM(say("ok"))
    rig = make_rig(
        tmp_path, [script],
        extra_agents={
            "sneaky": "---\nname: sneaky\ndescription: d\n"
            "tools: [read_file, ask_user, task, memorize, record_decision, enter_plan_mode, todo_write]\n---\nbody\n"
        },
    )
    rig.runtime.register_tool(AskUserTool(lambda *a: None))
    rig.runtime.register_tool(TodoWriteTool())
    await rig.runner.spawn_many([TaskRequest("sneaky", "x")], rig.parent)
    assert _tool_names(script) == {"read_file"}


async def test_inherited_tools_exclude_forbidden_and_disallowed(tmp_path: Path) -> None:
    script = ScriptedLLM(say("ok"))
    rig = make_rig(
        tmp_path, [script],
        extra_agents={"gp": "---\nname: gp\ndescription: d\ndisallowedTools: Bash, web_fetch\n---\nbody\n"},
    )
    rig.runtime.register_tool(AskUserTool(lambda *a: None))
    rig.runtime.register_tool(TodoWriteTool())
    await rig.runner.spawn_many([TaskRequest("gp", "x")], rig.parent)
    names = _tool_names(script)
    assert {"read_file", "write_file", "edit_file", "glob", "grep"} <= names
    assert not names & {"run_command", "web_fetch", "ask_user", "todo_write", "task"}


async def test_denied_tool_returns_error_to_child_which_keeps_going(tmp_path: Path) -> None:
    # pai SUPERVISED: o filho não escreve (sem humano) mas continua e termina
    script = ScriptedLLM(use("write_file", {"path": str(tmp_path / "ws" / "a.txt"), "content": "x"}), say("não consegui escrever"))
    rig = make_rig(tmp_path, [script], mode=AutonomyMode.SUPERVISED)
    result = (await rig.runner.spawn_many([TaskRequest("general-purpose", "escreva a.txt")], rig.parent))[0]
    assert result.status == "ok" and "não consegui" in result.summary
    assert not (rig.workspace / "a.txt").exists()
    feedback = json.dumps([m.model_dump(mode="json") for m in script.requests[1]])
    assert "no human" in feedback  # o motivo chegou ao filho
    audit = [json.loads(x) for x in (rig.home / "audit.log").read_text().splitlines()]
    denied = [r for r in audit if r.get("denial_reason") == "ask_no_human"]
    assert denied and denied[0]["agent_id"] == result.agent_id


async def test_child_writes_inside_workspace_when_parent_is_workspace_auto(tmp_path: Path) -> None:
    target = tmp_path / "ws" / "a.txt"
    script = ScriptedLLM(use("write_file", {"path": str(target), "content": "olá"}), say("feito"))
    rig = make_rig(tmp_path, [script], mode=AutonomyMode.WORKSPACE_AUTO)
    result = (await rig.runner.spawn_many([TaskRequest("general-purpose", "escreva")], rig.parent))[0]
    assert result.status == "ok" and target.read_text() == "olá"
    assert not (rig.workspace / ".orion" / "settings.local.json").exists()  # filho nunca grava regra


async def test_child_cannot_write_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    script = ScriptedLLM(use("write_file", {"path": str(outside), "content": "x"}), say("negado"))
    rig = make_rig(tmp_path, [script], mode=AutonomyMode.FULLY_AUTO)
    await rig.runner.spawn_many([TaskRequest("general-purpose", "escreva fora")], rig.parent)
    assert not outside.exists()


async def test_untrusted_project_agent_cannot_widen_tools(tmp_path: Path) -> None:
    script = ScriptedLLM(say("ok"))
    rig = make_rig(tmp_path, [script])
    project = rig.workspace / ".orion" / "agents"
    project.mkdir(parents=True)
    (project / "evil.md").write_text(
        "---\nname: evil\ndescription: d\ntools: [read_file, write_file, run_command]\nmodel_tier: heavy\n---\nbody\n"
    )
    from orion.agents.definitions import load_agents
    from orion.settings.models import AgentsSettings

    catalog = load_agents(rig.home, rig.workspace, limits=AgentsSettings().resolved())
    rig.runner.deps.catalog = lambda: catalog
    await rig.runner.spawn_many([TaskRequest("evil", "x")], rig.parent)
    assert _tool_names(script) == {"read_file"}
    assert rig.gateway.resolved[-1]["tier"] == "balanced" and rig.gateway.resolved[-1]["mutating"] is False


async def test_mutating_flag_reflects_effective_tools(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, [ScriptedLLM(say("a")), ScriptedLLM(say("b"))])
    await rig.runner.spawn_many([TaskRequest("explore", "x")], rig.parent)
    await rig.runner.spawn_many([TaskRequest("general-purpose", "x")], rig.parent)
    assert [r["mutating"] for r in rig.gateway.resolved] == [False, True]


async def test_child_cannot_call_a_tool_outside_its_set(tmp_path: Path) -> None:
    script = ScriptedLLM(use("run_command", {"command": "echo hi"}), say("fim"))
    rig = make_rig(tmp_path, [script], mode=AutonomyMode.FULLY_AUTO)
    result = (await rig.runner.spawn_many([TaskRequest("explore", "x")], rig.parent))[0]
    assert result.status == "ok"
    assert "not available to this subagent" in json.dumps(
        [m.model_dump(mode="json") for m in script.requests[1]]
    )


async def test_depth_is_one_by_default(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, [ScriptedLLM(say("a"))])
    from orion.agents.runner import ParentHandle

    deep = ParentHandle(pep=rig.pep, runtime=rig.runtime, depth=1)
    result = (await rig.runner.spawn_many([TaskRequest("explore", "x")], deep))[0]
    assert result.status == "error" and "depth limit" in result.summary


async def test_nested_delegation_is_capped_by_the_childs_own_tools(tmp_path: Path) -> None:
    """Com max_depth=2 o filho pode delegar, mas o neto nunca excede o conjunto do filho."""
    from orion.runtime.tools.task import TaskTool
    from orion.settings.models import AgentsSettings

    child_script = ScriptedLLM(
        use("task", {"agent": "general-purpose", "goal": "sub"}), say("filho concluiu")
    )
    grandchild_script = ScriptedLLM(say("neto concluiu"))
    rig = make_rig(
        tmp_path, [child_script, grandchild_script],
        limits=AgentsSettings(max_depth=2),
        extra_agents={"delegator": "---\nname: delegator\ndescription: d\ntools: [read_file, task]\n---\nbody\n"},
    )
    rig.runtime.register_tool(TaskTool(rig.runner.bind(rig.parent)))
    result = (await rig.runner.spawn_many([TaskRequest("delegator", "delegue")], rig.parent))[0]
    assert result.status == "ok" and "filho concluiu" in result.summary
    assert _tool_names(child_script) == {"read_file", "task"}
    assert _tool_names(grandchild_script) == {"read_file"}  # herda só o que o filho tinha


# ── Propriedade: o filho nunca pode mais do que o pai ───────────────────────

_ACTIONS = [
    ("read_file", {"path": "a.txt"}),
    ("glob", {"pattern": "*"}),
    ("write_file", {"path": "a.txt", "content": "x"}),
    ("write_file", {"path": "/etc/x", "content": "x"}),
    ("edit_file", {"path": "a.txt", "old_string": "a", "new_string": "b"}),
    ("run_command", {"command": "ls"}),
    ("run_command", {"command": "sudo apt update"}),
    ("run_command", {"command": "rm -rf /"}),
    ("web_fetch", {"url": "https://example.com"}),
    ("kill_shell", {"shell_id": "shell_1"}),
]


@pytest.mark.parametrize("mode", list(AutonomyMode))
@pytest.mark.parametrize("plan_mode", [False, True])
@pytest.mark.parametrize("tool, params", _ACTIONS)
async def test_property_child_never_exceeds_parent(
    tmp_path: Path, mode: AutonomyMode, plan_mode: bool, tool: str, params: dict[str, Any]
) -> None:
    """Pai sem humano disponível (confirma nada): tudo que o filho executa o pai também executaria."""
    rules = RuleSet.from_lists(deny=["run_command(rm:*)"])
    parent = PolicyEnforcementPoint(
        scope=WorkspaceScope([tmp_path]), mode=mode, rules=rules,
        audit_logger=AuditLogger(tmp_path / "a.log"), confirm=lambda _p: False,
    )
    parent.set_read_only(plan_mode)
    child = _child(parent, mode=AutonomyMode.FULLY_AUTO)  # o filho "pede" o máximo
    fixed = {k: (str(tmp_path / v) if k == "path" and not str(v).startswith("/") else v) for k, v in params.items()}

    async def decision(pep: PolicyEnforcementPoint) -> bool:
        try:
            return await pep.evaluate(Action(tool=tool, params=dict(fixed)))
        except ActionDenied:
            return False

    parent_ok = await decision(parent)
    child_ok = await decision(child)
    assert not (child_ok and not parent_ok), f"{tool} {fixed}: filho executou o que o pai não executaria"
