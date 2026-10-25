"""
Tests for the 5 Native Primitive Tools — Sprint 3.

Coverage:
  ReadFileTool:
    - read full file
    - read with start_line/end_line
    - read with byte_offset
    - file not found error
    - path is a directory error

  WriteFileTool:
    - create new file
    - overwrite existing file
    - append to existing file
    - fail if file exists without overwrite=True
    - overwrite and append mutually exclusive

  EditFileTool:
    - replace unique target
    - delete target (empty replacement)
    - fail when target not found
    - fail when target appears multiple times (ambiguity guard)
    - fail when target is empty string

  RunCommandTool:
    - successful command with output
    - command exits non-zero
    - timeout kills process and returns failure
    - empty command rejected

  SearchFilesTool:
    - glob mode finds files
    - glob mode no matches
    - grep mode finds lines
    - grep mode no matches
    - grep mode with invalid regex
    - hidden files excluded by default
    - ignored dirs excluded

  LocalRuntimeProvider:
    - execute dispatches to correct tool (via execute_direct)
    - execute returns failure for unknown tool
    - execute_direct bypasses PEP
    - execute goes through PEP (FULLY_AUTO → runs)
    - supports() returns correct booleans

  Engine integration:
    - tool_call dispatched to LocalRuntimeProvider → Observation reflects result
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path

import pytest

from orion.core.event_bus import EventBus
from orion.core.engine import ReActEngine
from orion.core.events import Observation
from orion.governance.audit import AuditLogger
from orion.governance.pep import AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import WorkspaceScope
from orion.runtime.local_provider import LocalRuntimeProvider
from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.edit_file import EditFileTool
from orion.runtime.tools.read_file import ReadFileTool
from orion.runtime.tools.run_command import RunCommandTool
from orion.runtime.tools.search_files import SearchFilesTool
from orion.runtime.tools.write_file import WriteFileTool


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _file(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# ReadFileTool
# ─────────────────────────────────────────────────────────────────────────────


class TestReadFileTool:
    @pytest.fixture()
    def tool(self) -> ReadFileTool:
        return ReadFileTool()

    @pytest.mark.asyncio
    async def test_read_full_file(self, tool: ReadFileTool, tmp_path: Path) -> None:
        p = _file(tmp_path, "hello.txt", "line1\nline2\nline3\n")
        result = await tool.run(path=str(p))
        assert result.success
        assert "line1" in result.output
        assert "line3" in result.output
        assert result.metadata["total_lines"] == 3

    @pytest.mark.asyncio
    async def test_read_line_range(self, tool: ReadFileTool, tmp_path: Path) -> None:
        p = _file(tmp_path, "lines.txt", "a\nb\nc\nd\ne\n")
        result = await tool.run(path=str(p), start_line=2, end_line=4)
        assert result.success
        assert result.output.strip() == "b\nc\nd"

    @pytest.mark.asyncio
    async def test_read_byte_offset(self, tool: ReadFileTool, tmp_path: Path) -> None:
        p = _file(tmp_path, "offset.txt", "ABCDEF")
        result = await tool.run(path=str(p), byte_offset=3)
        assert result.success
        assert result.output == "DEF"

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, tool: ReadFileTool, tmp_path: Path) -> None:
        result = await tool.run(path=str(tmp_path / "ghost.txt"))
        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_read_path_is_directory(self, tool: ReadFileTool, tmp_path: Path) -> None:
        result = await tool.run(path=str(tmp_path))
        assert not result.success
        assert "not a regular file" in result.error

    @pytest.mark.asyncio
    async def test_read_empty_path(self, tool: ReadFileTool) -> None:
        result = await tool.run(path="")
        assert not result.success
        assert "required" in result.error

    @pytest.mark.asyncio
    async def test_read_max_bytes_truncates(self, tool: ReadFileTool, tmp_path: Path) -> None:
        p = _file(tmp_path, "big.txt", "x" * 200)
        result = await tool.run(path=str(p), max_bytes=10)
        assert result.success
        assert len(result.output) <= 10
        assert result.metadata["truncated"] is True


# ─────────────────────────────────────────────────────────────────────────────
# WriteFileTool
# ─────────────────────────────────────────────────────────────────────────────


class TestWriteFileTool:
    @pytest.fixture()
    def tool(self) -> WriteFileTool:
        return WriteFileTool()

    @pytest.mark.asyncio
    async def test_write_creates_new_file(self, tool: WriteFileTool, tmp_path: Path) -> None:
        target = tmp_path / "new.txt"
        result = await tool.run(path=str(target), content="hello world")
        assert result.success
        assert target.read_text() == "hello world"
        assert result.metadata["created"] is True

    @pytest.mark.asyncio
    async def test_write_fails_if_exists_without_overwrite(
        self, tool: WriteFileTool, tmp_path: Path
    ) -> None:
        target = _file(tmp_path, "exists.txt", "original")
        result = await tool.run(path=str(target), content="new")
        assert not result.success
        assert "already exists" in result.error
        assert target.read_text() == "original"

    @pytest.mark.asyncio
    async def test_write_overwrite(self, tool: WriteFileTool, tmp_path: Path) -> None:
        target = _file(tmp_path, "over.txt", "old")
        result = await tool.run(path=str(target), content="new", overwrite=True)
        assert result.success
        assert target.read_text() == "new"

    @pytest.mark.asyncio
    async def test_write_append(self, tool: WriteFileTool, tmp_path: Path) -> None:
        target = _file(tmp_path, "append.txt", "line1\n")
        result = await tool.run(path=str(target), content="line2\n", append=True)
        assert result.success
        assert target.read_text() == "line1\nline2\n"

    @pytest.mark.asyncio
    async def test_write_append_creates_if_absent(
        self, tool: WriteFileTool, tmp_path: Path
    ) -> None:
        target = tmp_path / "brand_new.txt"
        result = await tool.run(path=str(target), content="data", append=True)
        assert result.success
        assert target.read_text() == "data"

    @pytest.mark.asyncio
    async def test_write_overwrite_and_append_mutually_exclusive(
        self, tool: WriteFileTool, tmp_path: Path
    ) -> None:
        target = tmp_path / "x.txt"
        result = await tool.run(path=str(target), content="x", overwrite=True, append=True)
        assert not result.success
        assert "mutually exclusive" in result.error

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tool: WriteFileTool, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c.txt"
        result = await tool.run(path=str(target), content="deep")
        assert result.success
        assert target.read_text() == "deep"

    @pytest.mark.asyncio
    async def test_write_empty_path(self, tool: WriteFileTool) -> None:
        result = await tool.run(path="", content="x")
        assert not result.success


# ─────────────────────────────────────────────────────────────────────────────
# EditFileTool
# ─────────────────────────────────────────────────────────────────────────────


class TestEditFileTool:
    @pytest.fixture()
    def tool(self) -> EditFileTool:
        return EditFileTool()

    @pytest.mark.asyncio
    async def test_edit_replaces_unique_target(
        self, tool: EditFileTool, tmp_path: Path
    ) -> None:
        p = _file(tmp_path, "code.py", "def foo():\n    return 1\n")
        result = await tool.run(path=str(p), target="return 1", replacement="return 42")
        assert result.success
        assert "return 42" in p.read_text()
        assert result.metadata["occurrences_found"] == 1

    @pytest.mark.asyncio
    async def test_edit_deletes_target(self, tool: EditFileTool, tmp_path: Path) -> None:
        p = _file(tmp_path, "del.txt", "KEEP\nDELETE_ME\nKEEP\n")
        result = await tool.run(path=str(p), target="DELETE_ME\n", replacement="")
        assert result.success
        assert "DELETE_ME" not in p.read_text()

    @pytest.mark.asyncio
    async def test_edit_fails_target_not_found(
        self, tool: EditFileTool, tmp_path: Path
    ) -> None:
        p = _file(tmp_path, "notfound.py", "x = 1\n")
        result = await tool.run(path=str(p), target="MISSING_TOKEN", replacement="y")
        assert not result.success
        assert "not found" in result.error
        assert result.metadata.get("occurrences_found") == 0

    @pytest.mark.asyncio
    async def test_edit_fails_target_not_unique(
        self, tool: EditFileTool, tmp_path: Path
    ) -> None:
        p = _file(tmp_path, "dup.py", "x = 1\nx = 1\n")
        result = await tool.run(path=str(p), target="x = 1", replacement="x = 2")
        assert not result.success
        assert "2 times" in result.error
        assert result.metadata.get("occurrences_found") == 2
        # File must be unchanged
        assert p.read_text() == "x = 1\nx = 1\n"

    @pytest.mark.asyncio
    async def test_edit_fails_empty_target(self, tool: EditFileTool, tmp_path: Path) -> None:
        p = _file(tmp_path, "e.py", "x = 1\n")
        result = await tool.run(path=str(p), target="", replacement="y")
        assert not result.success
        assert "required" in result.error

    @pytest.mark.asyncio
    async def test_edit_fails_file_not_found(self, tool: EditFileTool, tmp_path: Path) -> None:
        result = await tool.run(
            path=str(tmp_path / "ghost.py"), target="x", replacement="y"
        )
        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_edit_is_atomic(self, tool: EditFileTool, tmp_path: Path) -> None:
        """After a successful edit, no temp files should linger."""
        p = _file(tmp_path, "clean.py", "VAL = 'old'\n")
        await tool.run(path=str(p), target="old", replacement="new")
        remaining = list(tmp_path.glob(".orion_edit_*"))
        assert remaining == []


# ─────────────────────────────────────────────────────────────────────────────
# RunCommandTool
# ─────────────────────────────────────────────────────────────────────────────


class TestRunCommandTool:
    @pytest.fixture()
    def tool(self) -> RunCommandTool:
        return RunCommandTool()

    @pytest.mark.asyncio
    async def test_run_echo(self, tool: RunCommandTool) -> None:
        result = await tool.run(command="echo hello_orion")
        assert result.success
        assert "hello_orion" in result.output
        assert result.metadata["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_run_exit_nonzero(self, tool: RunCommandTool) -> None:
        result = await tool.run(command="exit 42", timeout=5.0)
        assert not result.success
        assert result.metadata["exit_code"] == 42

    @pytest.mark.asyncio
    async def test_run_timeout_kills_process(self, tool: RunCommandTool) -> None:
        result = await tool.run(command="sleep 60", timeout=0.5)
        assert not result.success
        assert result.metadata["timed_out"] is True

    @pytest.mark.asyncio
    async def test_run_empty_command_rejected(self, tool: RunCommandTool) -> None:
        result = await tool.run(command="")
        assert not result.success
        assert "required" in result.error

    @pytest.mark.asyncio
    async def test_run_captures_stderr_via_stdout_merge(self, tool: RunCommandTool) -> None:
        result = await tool.run(command="echo err >&2 && echo out")
        assert result.success
        assert "out" in result.output

    @pytest.mark.asyncio
    async def test_run_with_cwd(self, tool: RunCommandTool, tmp_path: Path) -> None:
        result = await tool.run(command="pwd", cwd=str(tmp_path))
        assert result.success
        assert str(tmp_path) in result.output.strip()


# ─────────────────────────────────────────────────────────────────────────────
# SearchFilesTool
# ─────────────────────────────────────────────────────────────────────────────


class TestSearchFilesTool:
    @pytest.fixture()
    def tool(self) -> SearchFilesTool:
        return SearchFilesTool()

    @pytest.fixture()
    def repo(self, tmp_path: Path) -> Path:
        """Create a small fake repo structure."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("def hello(): pass\n")
        (tmp_path / "src" / "utils.py").write_text("def helper(): return 42\n")
        (tmp_path / "README.md").write_text("# Project\n")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"\x00\x01")
        (tmp_path / ".hidden_dir").mkdir()
        (tmp_path / ".hidden_dir" / "secret.txt").write_text("hidden")
        return tmp_path

    @pytest.mark.asyncio
    async def test_glob_finds_python_files(
        self, tool: SearchFilesTool, repo: Path
    ) -> None:
        result = await tool.run(path=str(repo), pattern="*.py", mode="glob")
        assert result.success
        assert "main.py" in result.output
        assert "utils.py" in result.output

    @pytest.mark.asyncio
    async def test_glob_excludes_pycache(
        self, tool: SearchFilesTool, repo: Path
    ) -> None:
        result = await tool.run(path=str(repo), pattern="*.pyc", mode="glob")
        assert result.success
        assert "__pycache__" not in result.output

    @pytest.mark.asyncio
    async def test_glob_excludes_hidden_by_default(
        self, tool: SearchFilesTool, repo: Path
    ) -> None:
        result = await tool.run(path=str(repo), pattern="*.txt", mode="glob")
        assert ".hidden_dir" not in result.output

    @pytest.mark.asyncio
    async def test_glob_includes_hidden_when_requested(
        self, tool: SearchFilesTool, repo: Path
    ) -> None:
        result = await tool.run(
            path=str(repo), pattern="*.txt", mode="glob", include_hidden=True
        )
        assert "secret.txt" in result.output

    @pytest.mark.asyncio
    async def test_glob_no_matches(self, tool: SearchFilesTool, repo: Path) -> None:
        result = await tool.run(path=str(repo), pattern="*.rs", mode="glob")
        assert result.success
        assert "no files" in result.output

    @pytest.mark.asyncio
    async def test_grep_finds_function(
        self, tool: SearchFilesTool, repo: Path
    ) -> None:
        result = await tool.run(
            path=str(repo), pattern="*.py", mode="grep", regex=r"def \w+"
        )
        assert result.success
        assert "main.py" in result.output
        assert "def hello" in result.output

    @pytest.mark.asyncio
    async def test_grep_case_insensitive(
        self, tool: SearchFilesTool, repo: Path
    ) -> None:
        result = await tool.run(
            path=str(repo),
            pattern="*.md",
            mode="grep",
            regex="project",
            case_sensitive=False,
        )
        assert result.success
        assert "README.md" in result.output

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, tool: SearchFilesTool, repo: Path) -> None:
        result = await tool.run(
            path=str(repo), pattern="*.py", mode="grep", regex="NONEXISTENT_SYMBOL"
        )
        assert result.success
        assert "no matches" in result.output

    @pytest.mark.asyncio
    async def test_grep_invalid_regex(self, tool: SearchFilesTool, repo: Path) -> None:
        result = await tool.run(
            path=str(repo), pattern="*.py", mode="grep", regex="[invalid"
        )
        assert not result.success
        assert "invalid regex" in result.error

    @pytest.mark.asyncio
    async def test_unknown_mode(self, tool: SearchFilesTool, tmp_path: Path) -> None:
        result = await tool.run(path=str(tmp_path), pattern="*", mode="bad_mode")
        assert not result.success
        assert "unknown mode" in result.error

    @pytest.mark.asyncio
    async def test_path_not_found(self, tool: SearchFilesTool, tmp_path: Path) -> None:
        result = await tool.run(path=str(tmp_path / "nope"), pattern="*")
        assert not result.success


# ─────────────────────────────────────────────────────────────────────────────
# LocalRuntimeProvider
# ─────────────────────────────────────────────────────────────────────────────


class TestLocalRuntimeProvider:
    @pytest.fixture()
    def fully_auto_provider(self, tmp_path: Path) -> LocalRuntimeProvider:
        scope = WorkspaceScope(roots=[tmp_path])
        pep = PolicyEnforcementPoint(
            scope=scope,
            mode=AutonomyMode.FULLY_AUTO,
            audit_logger=AuditLogger(log_path=tmp_path / "audit.log"),
            confirm=lambda _: True,
        )
        return LocalRuntimeProvider(pep=pep, scope=scope)

    def test_supports_all_five_tools(
        self, fully_auto_provider: LocalRuntimeProvider
    ) -> None:
        for name in ("read_file", "write_file", "edit_file", "search_files", "run_command"):
            assert fully_auto_provider.supports(name)

    def test_does_not_support_unknown_tool(
        self, fully_auto_provider: LocalRuntimeProvider
    ) -> None:
        assert not fully_auto_provider.supports("nonexistent")

    @pytest.mark.asyncio
    async def test_execute_direct_bypasses_pep(
        self, fully_auto_provider: LocalRuntimeProvider, tmp_path: Path
    ) -> None:
        target = tmp_path / "direct.txt"
        result = await fully_auto_provider.execute_direct(
            "write_file", {"path": str(target), "content": "direct_write"}
        )
        assert result.success
        assert target.read_text() == "direct_write"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_fails(
        self, fully_auto_provider: LocalRuntimeProvider
    ) -> None:
        result = await fully_auto_provider.execute("ghost_tool", {})
        assert not result.success
        assert "unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_execute_via_pep_fully_auto(
        self, fully_auto_provider: LocalRuntimeProvider, tmp_path: Path
    ) -> None:
        result = await fully_auto_provider.execute(
            "run_command", {"command": "echo pep_test"}
        )
        assert result.success
        assert "pep_test" in result.output

    @pytest.mark.asyncio
    async def test_pep_denies_path_outside_workspace(
        self, fully_auto_provider: LocalRuntimeProvider
    ) -> None:
        result = await fully_auto_provider.execute(
            "write_file", {"path": "/etc/orion_test.conf", "content": "x"}
        )
        assert not result.success
        assert result.metadata.get("denied") is True


# ─────────────────────────────────────────────────────────────────────────────
# Engine integration: tool_call dispatched to LocalRuntimeProvider
# ─────────────────────────────────────────────────────────────────────────────


class TestEngineWithRuntime:
    @pytest.fixture()
    def runtime(self, tmp_path: Path) -> LocalRuntimeProvider:
        scope = WorkspaceScope(roots=[tmp_path])
        pep = PolicyEnforcementPoint(
            scope=scope,
            mode=AutonomyMode.FULLY_AUTO,
            audit_logger=AuditLogger(log_path=tmp_path / "audit.log"),
            confirm=lambda _: True,
        )
        return LocalRuntimeProvider(pep=pep, scope=scope)

    @pytest.mark.asyncio
    async def test_engine_dispatches_tool_call_to_runtime(
        self, runtime: LocalRuntimeProvider
    ) -> None:
        """Engine should route tool_call response through the real runtime."""
        call_count = 0

        async def llm(prompt: str):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("tool_call", "run_command", {"command": "echo engine_test"}, 3, None)
            return ("final_answer", "done")

        bus = EventBus()
        engine = ReActEngine(event_bus=bus, llm=llm, runtime=runtime)
        answer = await engine.run("run echo please")
        assert answer == "done"
        # Verify we went through 2 turns (tool_call + final_answer)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_engine_observation_reflects_real_output(
        self, runtime: LocalRuntimeProvider
    ) -> None:
        """The Observation output should contain actual shell output."""
        observations: list[Observation] = []

        async def llm(prompt: str):
            # Turn 1: emit tool_call
            if not observations:
                return ("tool_call", "run_command", {"command": "echo REAL_OUTPUT"}, 3, None)
            return ("final_answer", observations[-1].output)

        bus = EventBus()

        @bus.subscribe(Observation)
        async def capture_obs(event) -> None:
            observations.append(event)

        engine = ReActEngine(event_bus=bus, llm=llm, runtime=runtime)
        answer = await engine.run("test")
        assert "REAL_OUTPUT" in answer

    @pytest.mark.asyncio
    async def test_engine_without_runtime_uses_stub(self) -> None:
        """When runtime=None, the engine should still work using the stub."""
        async def llm(prompt: str):
            return ("final_answer", "stub_answer")

        bus = EventBus()
        engine = ReActEngine(event_bus=bus, llm=llm)
        answer = await engine.run("hello")
        assert answer == "stub_answer"
