"""v0.5.0 Sprint 4 — shell em background, todo_write, ask_user, plan mode, notebook_edit."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from orion.runtime.tools.ask_user import AskUserTool
from orion.runtime.tools.bash_output import BashOutputTool
from orion.runtime.tools.kill_shell import KillShellTool
from orion.runtime.tools.notebook_edit import NotebookEditTool
from orion.runtime.tools.plan_mode import EnterPlanModeTool, ExitPlanModeTool
from orion.runtime.tools.run_command import RunCommandTool
from orion.runtime.tools.shells import ShellManager
from orion.runtime.tools.todo_write import TodoList, TodoWriteTool


@pytest.fixture()
def shells(tmp_path: Path):  # type: ignore[no-untyped-def]
    manager = ShellManager(tmp_path / "shells")
    yield manager
    manager.kill_all()


async def wait_for(predicate, timeout: float = 5.0) -> None:  # type: ignore[no-untyped-def]
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("timeout")


class TestBackgroundShell:
    async def test_run_read_incrementally_and_exit_code(self, shells: ShellManager) -> None:
        run, out = RunCommandTool(shells), BashOutputTool(shells)
        started = await run.run(command="echo one; sleep 0.3; echo two; exit 3", run_in_background=True)
        assert started.success and started.metadata["shell_id"] == "shell_1"
        sid = started.metadata["shell_id"]
        await wait_for(lambda: not shells.get(sid).running)  # type: ignore[union-attr]
        first = await out.run(shell_id=sid)
        assert "one" in first.output and "two" in first.output and "exited (3)" in first.output
        again = await out.run(shell_id=sid)
        assert "(no new output)" in again.output  # só o que é novo

    async def test_filter_and_invalid_filter_and_unknown_id(self, shells: ShellManager) -> None:
        sid = (await RunCommandTool(shells).run(command="printf 'a\\nERR b\\nc\\n'", run_in_background=True)).metadata["shell_id"]
        await wait_for(lambda: not shells.get(sid).running)  # type: ignore[union-attr]
        out = BashOutputTool(shells)
        assert not (await out.run(shell_id=sid, filter="(")).success
        r = await out.run(shell_id=sid, filter="ERR")
        assert "ERR b" in r.output and "\na\n" not in r.output
        unknown = await out.run(shell_id="nope")
        assert not unknown.success and "shell_1" in unknown.error

    async def test_kill_stops_whole_process_group(self, shells: ShellManager) -> None:
        sid = (await RunCommandTool(shells).run(command="sleep 60 & sleep 60", run_in_background=True)).metadata["shell_id"]
        kill = KillShellTool(shells)
        assert shells.get(sid).running  # type: ignore[union-attr]
        r = await kill.run(shell_id=sid)
        assert r.success and r.metadata["killed"] is True
        assert not shells.get(sid).running  # type: ignore[union-attr]
        again = await kill.run(shell_id=sid)
        assert again.metadata["killed"] is False
        assert not (await kill.run(shell_id="zzz")).success

    async def test_background_without_manager_fails_cleanly(self) -> None:
        r = await RunCommandTool().run(command="echo x", run_in_background=True)
        assert not r.success and "not available" in r.error

    async def test_foreground_still_works(self) -> None:
        r = await RunCommandTool().run(command="echo ok")
        assert r.success and r.output.strip() == "ok"


class TestTodoWrite:
    async def test_replaces_list_and_renders_with_allowed_glyphs(self) -> None:
        seen: list[int] = []
        tool = TodoWriteTool(TodoList(), on_update=lambda todos: seen.append(len(todos.items)))
        r = await tool.run(todos=[
            {"content": "A", "status": "completed"},
            {"content": "B", "status": "in_progress"},
            {"content": "C", "status": "pending"},
        ])
        assert "Tarefas 1/3" in r.output and "✔ A" in r.output and "● B" in r.output and "· C" in r.output
        assert seen == [3] and tool.todos.items[1].status == "in_progress"
        assert (await tool.run(todos=[])).output == "(empty todo list)"

    async def test_two_in_progress_rejected_and_state_kept(self) -> None:
        tool = TodoWriteTool()
        await tool.run(todos=[{"content": "A", "status": "pending"}])
        r = await tool.run(todos=[{"content": "A", "status": "in_progress"}, {"content": "B", "status": "in_progress"}])
        assert not r.success and len(tool.todos.items) == 1


class TestAskUser:
    async def test_answer_is_returned(self) -> None:
        async def asker(q: str, opts: list[dict[str, str]], multi: bool) -> list[str] | None:
            assert q == "Qual?" and [o["label"] for o in opts] == ["A", "B"] and not multi
            return ["B"]

        r = await AskUserTool(asker).run(question="Qual?", options=[{"label": "A"}, {"label": "B"}])
        assert r.success and "B" in r.output

    async def test_no_channel_or_no_answer_fails(self) -> None:
        assert not (await AskUserTool().run(question="Qual?")).success

        async def silent(q: str, o: list[dict[str, str]], m: bool) -> list[str] | None:
            return None

        r = await AskUserTool(silent).run(question="Qual?")
        assert not r.success and "did not answer" in r.error


class TestPlanMode:
    async def test_enter_calls_hook(self) -> None:
        calls: list[int] = []
        assert (await EnterPlanModeTool(lambda: calls.append(1)).run()).success and calls == [1]
        assert not (await EnterPlanModeTool().run()).success

    async def test_exit_requires_plan_mode_and_approval(self) -> None:
        approved = {"v": True}

        async def approver(plan: str) -> bool:
            return approved["v"]

        state = {"plan": False}
        tool = ExitPlanModeTool(approver, lambda: state["plan"])
        assert "not in plan mode" in (await tool.run(plan="# Plano completo")).error
        state["plan"] = True
        assert (await tool.run(plan="# Plano completo")).metadata["approved"] is True
        approved["v"] = False
        rejected = await tool.run(plan="# Plano completo")
        assert not rejected.success and "not approved" in rejected.error
        assert not (await ExitPlanModeTool().run(plan="# Plano completo")).success


def _notebook(path: Path) -> Path:
    nb = {
        "cells": [
            {"cell_type": "code", "metadata": {}, "source": ["print(1)\n"], "outputs": [{"x": 1}], "execution_count": 3},
            {"cell_type": "markdown", "metadata": {}, "source": ["# T\n"]},
        ],
        "metadata": {}, "nbformat": 4, "nbformat_minor": 5,
    }
    path.write_text(json.dumps(nb))
    return path


class TestNotebookEdit:
    async def test_replace_clears_outputs(self, tmp_path: Path) -> None:
        nb = _notebook(tmp_path / "n.ipynb")
        r = await NotebookEditTool().run(path=str(nb), cell_index=0, new_source="print(2)\nprint(3)")
        cell = json.loads(nb.read_text())["cells"][0]
        assert r.success and cell["source"] == ["print(2)\n", "print(3)"]
        assert cell["outputs"] == [] and cell["execution_count"] is None

    async def test_insert_delete_and_type_change(self, tmp_path: Path) -> None:
        nb = _notebook(tmp_path / "n.ipynb")
        tool = NotebookEditTool()
        await tool.run(path=str(nb), new_source="# topo", cell_type="markdown", edit_mode="insert")
        cells = json.loads(nb.read_text())["cells"]
        assert cells[0]["source"] == ["# topo"] and "outputs" not in cells[0] and len(cells) == 3
        await tool.run(path=str(nb), cell_index=1, new_source="x=1", edit_mode="insert")
        assert json.loads(nb.read_text())["cells"][2]["source"] == ["x=1"]
        await tool.run(path=str(nb), cell_index=0, edit_mode="delete")
        assert len(json.loads(nb.read_text())["cells"]) == 3
        await tool.run(path=str(nb), cell_index=2, new_source="y", cell_type="code")
        assert json.loads(nb.read_text())["cells"][2]["outputs"] == []

    async def test_invalid_inputs(self, tmp_path: Path) -> None:
        nb = _notebook(tmp_path / "n.ipynb")
        tool = NotebookEditTool()
        assert not (await tool.run(path=str(tmp_path / "x.txt"))).success
        assert not (await tool.run(path=str(tmp_path / "missing.ipynb"))).success
        assert not (await tool.run(path=str(nb), cell_index=9, new_source="x")).success
        assert not (await tool.run(path=str(nb), new_source="x")).success  # sem cell_index
        assert not (await tool.run(path=str(nb), cell_index=0)).success  # sem new_source
        assert not (await tool.run(path=str(nb), cell_index=9, new_source="x", edit_mode="insert")).success
        bad = tmp_path / "bad.ipynb"
        bad.write_text("{not json")
        assert not (await tool.run(path=str(bad), cell_index=0, new_source="x")).success
