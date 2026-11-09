"""Peças de apoio da 6B: níveis do PEP, escopo com ``~``, store de sessão thread-safe, SQL seguro."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from orion.agents.models import TaskRecord, TaskStatus
from orion.agents.runner import AgentInbox, attach_parent_messages
from orion.agents.tasks import SqliteTaskStore
from orion.gateway.models import ContentBlock, LLMMessage, MessageRole
from orion.governance.permissions import (
    ActionLevel,
    WorkspaceScope,
    is_read_only_tool,
    tool_action_level,
)
from orion.sessions import JsonlSessionStore, TranscriptEntry


@pytest.mark.parametrize(
    "tool, level",
    [
        ("task", ActionLevel.LEVEL_1),
        ("task_create", ActionLevel.LEVEL_1),
        ("task_list", ActionLevel.LEVEL_0),
        ("task_get", ActionLevel.LEVEL_1),
        ("send_message", ActionLevel.LEVEL_1),
        ("task_stop", ActionLevel.LEVEL_2),
    ],
)
def test_every_new_tool_has_a_defined_pep_level(tool: str, level: ActionLevel) -> None:
    assert tool_action_level(tool) == level  # nunca cai no padrão "desconhecida = LEVEL_3"


def test_delegation_tools_run_in_parallel_but_stop_does_not() -> None:
    assert all(is_read_only_tool(t) for t in ("task", "task_create", "task_get", "task_list", "send_message"))
    assert not is_read_only_tool("task_stop")


def test_workspace_scope_expands_the_home_shortcut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    scope = WorkspaceScope([tmp_path / "ws"])
    assert not scope.is_allowed("~/.ssh/config")  # antes virava uma subpasta literal "~" do cwd
    inside = WorkspaceScope([tmp_path / "home"])
    assert inside.is_allowed("~/projeto/a.txt")


def test_session_store_appends_are_serialized_across_threads(tmp_path: Path) -> None:
    store = JsonlSessionStore(tmp_path / "sessions", tmp_path)

    def worker(n: int) -> None:
        for i in range(25):
            store.append("sess", TranscriptEntry.of_meta(writer=n, i=i))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    entries = store.load("sess")
    assert len(entries) == 1 + 6 * 25  # meta inicial + todas as gravações
    assert [e.index for e in entries] == list(range(len(entries)))  # índices únicos e contíguos


def test_task_store_is_parameterized(tmp_path: Path) -> None:
    store = SqliteTaskStore(tmp_path / "t.db")
    evil = "x'); DROP TABLE tasks; --"
    store.upsert(TaskRecord(task_id="task_1", owner=evil, agent="explore", goal=evil, status=TaskStatus.RUNNING))
    assert store.get(evil) is None and store.get("task_1").goal == evil  # type: ignore[union-attr]
    assert [r.task_id for r in store.list(owner=evil)] == ["task_1"]
    assert store.list(status=TaskStatus.DONE) == []
    store.upsert(store.get("task_1").model_copy(update={"status": TaskStatus.DONE}))  # type: ignore[union-attr]
    assert [r.status for r in store.list()] == [TaskStatus.DONE]


def test_inbox_delivers_once_and_only_to_running_agents() -> None:
    inbox = AgentInbox()
    assert inbox.post("agent_x", "oi") is False and inbox.drain("agent_x") == []
    inbox.open("agent_x")
    assert inbox.post("agent_x", "um") and inbox.post("agent_x", "dois")
    assert inbox.drain("agent_x") == ["um", "dois"] and inbox.drain("agent_x") == []
    inbox.close("agent_x")
    assert not inbox.is_open("agent_x") and inbox.post("agent_x", "tarde") is False


def test_attach_parent_messages_keeps_roles_alternating() -> None:
    result_msg = LLMMessage(role=MessageRole.USER, content=[ContentBlock.of_tool_result("t1", "saída")])
    out = attach_parent_messages([LLMMessage(role=MessageRole.ASSISTANT, content="a"), result_msg], ["foque em src/"])
    assert len(out) == 2 and out[-1].blocks[0].type == "tool_result" and out[-1].blocks[1].type == "text"
    assert "<message_from_parent>" in out[-1].text

    plain = attach_parent_messages([LLMMessage(role=MessageRole.USER, content="meta")], ["a", "b"])
    assert len(plain) == 1 and plain[0].text.startswith("meta") and "a" in plain[0].text and "b" in plain[0].text

    after_assistant = attach_parent_messages([LLMMessage(role=MessageRole.ASSISTANT, content="x")], ["oi"])
    assert [m.role for m in after_assistant] == [MessageRole.ASSISTANT, MessageRole.USER]
