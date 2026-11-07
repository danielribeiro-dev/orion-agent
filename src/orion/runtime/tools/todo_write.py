"""
O.R.I.O.N — Tool: todo_write
Lista de tarefas da sessão (substitui a lista inteira a cada chamada), renderizada na TUI.

ActionLevel: LEVEL_0 (estado em memória, sem efeitos no sistema)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool

STATUSES = ("pending", "in_progress", "completed")
_GLYPH = {"completed": "✔", "in_progress": "●", "pending": "·"}


@dataclass(frozen=True)
class TodoItem:
    content: str
    status: str


class TodoList:
    """Estado compartilhado entre a tool e a TUI."""

    def __init__(self) -> None:
        self.items: list[TodoItem] = []

    def replace(self, items: list[TodoItem]) -> None:
        self.items = list(items)

    def render(self) -> str:
        if not self.items:
            return "(empty todo list)"
        done = sum(i.status == "completed" for i in self.items)
        rows = [f"Tarefas {done}/{len(self.items)}"]
        rows += [f"  {_GLYPH[i.status]} {i.content}" for i in self.items]
        return "\n".join(rows)


class TodoWriteTool(BaseTool):
    name = "todo_write"
    description = (
        "Create and maintain a task list for multi-step work. Send the COMPLETE list every call. "
        "Each item has 'content' and 'status' (pending | in_progress | completed). Keep exactly one "
        "item in_progress while working and mark items completed as soon as they finish."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "minLength": 1},
                        "status": {"type": "string", "enum": list(STATUSES)},
                    },
                    "required": ["content", "status"],
                },
            }
        },
        "required": ["todos"],
    }
    read_only = True

    def __init__(
        self, todos: TodoList | None = None, on_update: Callable[[TodoList], None] | None = None
    ) -> None:
        self.todos = todos or TodoList()
        self._on_update = on_update

    async def run(self, todos: list[dict[str, Any]], **_: Any) -> RuntimeResult:
        items = [TodoItem(str(t["content"]).strip(), str(t["status"])) for t in todos]
        active = sum(i.status == "in_progress" for i in items)
        if active > 1:
            return RuntimeResult.fail("todo_write: only one item may be in_progress at a time.")
        self.todos.replace(items)
        if self._on_update is not None:
            self._on_update(self.todos)
        return RuntimeResult.ok(self.todos.render(), total=len(items), in_progress=active)
