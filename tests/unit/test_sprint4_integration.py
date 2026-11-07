"""v0.5.0 Sprint 4 — níveis PEP, imagens no engine, sessão (todo/ask_user/plan mode) e startup limpo."""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from orion.cli import configure_logging
from orion.core.engine import ReActEngine
from orion.core.event_bus import EventBus
from orion.governance.pep import AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import (
    SERIAL_TOOLS,
    TOOL_LEVELS,
    ActionLevel,
    WorkspaceScope,
    is_read_only_tool,
    tool_action_level,
)
from orion.runtime.local_provider import LocalRuntimeProvider
from orion.tui.panels import render_plan_approval, render_question
from orion.tui.session import AgentMode, AgentSession
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme
from tests.llm_script import ScriptedLLM, say, use
from tests.unit.test_agent_session import ScriptedProvider, call, output
from tests.unit.test_tools_read_search import PNG

NEW_TOOLS = {
    "glob": ActionLevel.LEVEL_1,
    "grep": ActionLevel.LEVEL_1,
    "bash_output": ActionLevel.LEVEL_1,
    "kill_shell": ActionLevel.LEVEL_2,
    "notebook_edit": ActionLevel.LEVEL_2,
    "web_fetch": ActionLevel.LEVEL_2,
    "web_search": ActionLevel.LEVEL_2,
    "todo_write": ActionLevel.LEVEL_0,
    "ask_user": ActionLevel.LEVEL_0,
    "enter_plan_mode": ActionLevel.LEVEL_0,
    "exit_plan_mode": ActionLevel.LEVEL_0,
}


class TestPepLevels:
    def test_every_new_tool_has_its_declared_level(self) -> None:
        for name, level in NEW_TOOLS.items():
            assert TOOL_LEVELS[name] == level, name

    def test_modal_tools_never_run_in_parallel(self) -> None:
        assert {"ask_user", "enter_plan_mode", "exit_plan_mode"} == SERIAL_TOOLS
        assert not any(is_read_only_tool(t) for t in SERIAL_TOOLS)
        assert is_read_only_tool("grep") and is_read_only_tool("todo_write")

    async def test_runtime_exposes_all_tools_and_gates_mutations(self, tmp_path: Path) -> None:
        scope = WorkspaceScope([tmp_path])
        asked: list[str] = []

        async def deny(action: Any, level: ActionLevel) -> bool:
            asked.append(action.tool)
            return False

        pep = PolicyEnforcementPoint(scope=scope, mode=AutonomyMode.SUPERVISED, action_confirm=deny)
        rt = LocalRuntimeProvider(pep=pep, scope=scope)
        assert {"glob", "grep", "web_fetch", "web_search", "notebook_edit", "bash_output", "kill_shell"} <= set(rt.available_tools)
        for name in rt.available_tools:
            assert tool_action_level(name) != ActionLevel.LEVEL_3 or name == "run_command", name
        # LEVEL_2 de rede e de processo passam pelo PEP; leitura não.
        assert (await rt.execute("web_fetch", {"url": "https://docs.python.org/"})).metadata["denied"]
        assert (await rt.execute("kill_shell", {"shell_id": "shell_1"})).metadata["denied"]
        assert asked == ["web_fetch", "kill_shell"]
        (tmp_path / "x.txt").write_text("hi")
        assert (await rt.execute("grep", {"pattern": "hi", "path": str(tmp_path)})).success
        assert asked == ["web_fetch", "kill_shell"]

    async def test_background_command_goes_through_pep_level_3(self, tmp_path: Path) -> None:
        scope = WorkspaceScope([tmp_path])
        asked: list[str] = []

        async def deny(action: Any, level: ActionLevel) -> bool:
            asked.append(f"{action.tool}:{int(level)}")
            return False

        rt = LocalRuntimeProvider(
            pep=PolicyEnforcementPoint(scope=scope, mode=AutonomyMode.SUPERVISED, action_confirm=deny), scope=scope
        )
        r = await rt.execute("run_command", {"command": "sleep 30", "run_in_background": True})
        assert not r.success and asked == ["run_command:3"] and not rt.shells.list()


class TestEngineImages:
    async def test_tool_image_reaches_the_model_as_image_block(self, tmp_path: Path) -> None:
        img = tmp_path / "p.png"
        img.write_bytes(PNG)
        scope = WorkspaceScope([tmp_path])
        rt = LocalRuntimeProvider(pep=PolicyEnforcementPoint(scope=scope, mode=AutonomyMode.FULLY_AUTO), scope=scope)
        llm = ScriptedLLM(use("read_file", {"path": str(img)}), say("É um pixel."))
        engine = ReActEngine(event_bus=EventBus(), llm=llm, runtime=rt)
        assert await engine.run("o que há na imagem?") == "É um pixel."
        result = llm.requests[1][-1].content[0]
        assert result.type == "tool_result" and not result.is_error
        kinds = [b.type for b in result.content]  # type: ignore[union-attr]
        assert kinds == ["text", "image"]
        assert result.content[1].source["data"] == base64.standard_b64encode(PNG).decode()  # type: ignore[index,union-attr]

    async def test_user_attachments_become_leading_image_blocks(self) -> None:
        llm = ScriptedLLM(say("ok"))
        engine = ReActEngine(event_bus=EventBus(), llm=llm)
        src = {"type": "base64", "media_type": "image/png", "data": "AAAA"}
        await engine.run("veja", images=[src])
        content = llm.requests[0][0].content
        assert [b.type for b in content] == ["image", "text"]  # type: ignore[union-attr]

    async def test_image_never_leaks_into_observation_metadata(self, tmp_path: Path) -> None:
        img = tmp_path / "p.png"
        img.write_bytes(PNG)
        scope = WorkspaceScope([tmp_path])
        rt = LocalRuntimeProvider(pep=PolicyEnforcementPoint(scope=scope, mode=AutonomyMode.FULLY_AUTO), scope=scope)
        bus = EventBus()
        seen: list[Any] = []
        from orion.core.events import Observation

        async def grab(event: Observation) -> None:
            seen.append(event)

        bus.subscribe_handler(Observation, grab)
        await ReActEngine(event_bus=bus, llm=ScriptedLLM(use("read_file", {"path": str(img)}), say("ok")), runtime=rt).run("x")
        assert seen and "image" not in seen[0].metadata and "image" not in seen[0].model_dump()


@pytest.fixture
def make_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def _make(provider: ScriptedProvider, answers: list[Any] | None = None) -> AgentSession:
        pending = list(answers or [])

        async def ask(action: Any, level: ActionLevel) -> Any:
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
    async def test_todo_write_updates_session_and_card(self, make_session) -> None:  # type: ignore[no-untyped-def]
        provider = ScriptedProvider([
            call("todo_write", todos=[{"content": "Corrigir bug", "status": "in_progress"}]),
            "Pronto.",
        ])
        session = make_session(provider)
        await session.run_turn("faça")
        assert [(i.content, i.status) for i in session.todos.items] == [("Corrigir bug", "in_progress")]
        assert "Corrigir bug" in output(session)

    async def test_ask_user_answer_flows_back_to_model(self, make_session) -> None:  # type: ignore[no-untyped-def]
        provider = ScriptedProvider([
            call("ask_user", question="Qual banco?", options=[{"label": "SQLite"}, {"label": "Postgres"}]),
            "Usarei SQLite.",
        ])
        session = make_session(provider)

        async def fake(question: str, options: list[dict[str, str]], multi: bool) -> list[str] | None:
            assert question == "Qual banco?"
            return ["SQLite"]

        session._ask_user = fake  # type: ignore[method-assign]
        session.runtime._tools["ask_user"]._asker = fake
        await session.run_turn("escolha")
        last = provider.requests[1].messages[-1]
        assert "User answered: SQLite" in str(last.content)

    async def test_plan_mode_roundtrip_with_approval(self, make_session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        provider = ScriptedProvider([
            call("enter_plan_mode"),
            call("exit_plan_mode", plan="# Plano\n1. Ler\n2. Corrigir"),
            "Plano aprovado.",
        ])
        session = make_session(provider)
        session.set_mode(AgentMode.AUTO)

        async def approve(console: Any, plan: str, label: str) -> bool:
            assert session.mode == AgentMode.PLAN and "Corrigir" in plan and label == "auto"
            return True

        monkeypatch.setattr("orion.tui.modal.approve_plan", approve)
        await session.run_turn("planeje")
        assert session.mode == AgentMode.AUTO  # voltou ao modo anterior após a aprovação

    async def test_plan_rejection_keeps_plan_mode_and_denies_mutation(self, make_session, monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
        target = tmp_path / "x.txt"
        provider = ScriptedProvider([
            call("enter_plan_mode"),
            call("exit_plan_mode", plan="# Plano\n1. Escrever x"),
            call("write_file", path=str(target), content="x"),
            "Entendido.",
        ])
        session = make_session(provider)

        async def reject(console: Any, plan: str, label: str) -> bool:
            return False

        monkeypatch.setattr("orion.tui.modal.approve_plan", reject)
        await session.run_turn("planeje")
        assert session.mode == AgentMode.PLAN and not target.exists()

    async def test_image_mention_is_attached_not_inlined_as_text(self, make_session, tmp_path) -> None:  # type: ignore[no-untyped-def]
        (tmp_path / "shot.png").write_bytes(PNG)
        provider = ScriptedProvider(["Vejo um pixel."])
        session = make_session(provider)
        await session.run_turn("analise @shot.png")
        content = provider.requests[0].messages[1].content  # [0] é o system (provider não-Anthropic)
        assert [b.type for b in content][0] == "image"  # type: ignore[union-attr]
        assert "\x89PNG" not in str(content)
        assert "apenas modelos Anthropic" in output(session)

    def test_shells_live_under_home_and_die_with_manager(self, make_session, tmp_path) -> None:  # type: ignore[no-untyped-def]
        session = make_session(ScriptedProvider([]))
        shell = session.shells.start("sleep 30")
        assert tmp_path / "home" / "shells" in shell.log_path.parents
        session.shells.kill_all()
        assert not shell.running


class TestPanels:
    def test_question_and_plan_panels_use_only_allowed_glyphs(self) -> None:
        console = Console(file=io.StringIO(), width=90, theme=get_orion_theme(), force_terminal=False)
        console.print(render_question("Qual?", [{"label": "A", "description": "d"}], 0, set(), False))
        console.print(render_question("Qual?", [{"label": "A"}], 1, {0}, True))
        console.print(render_plan_approval("# Plano\n- passo", "auto"))
        text = console.file.getvalue()  # type: ignore[attr-defined]
        assert "Outro" in text and "[x] A" in text and "Plano para aprovação" in text
        assert "✓" not in text and "✗" not in text


class TestAskChoiceModal:
    def test_keys(self) -> None:
        from orion.tui.modal import AskChoice

        modal = AskChoice("Q?", [{"label": "A"}, {"label": "B"}])
        assert not modal.on_key("down") and modal.selected == 1
        assert modal.on_key("enter") and modal.answers == ["B"]
        modal = AskChoice("Q?", [{"label": "A"}, {"label": "B"}])
        assert modal.on_key("1") and modal.answers == ["A"]
        modal = AskChoice("Q?", [{"label": "A"}, {"label": "B"}])
        assert modal.on_key("3") and modal.wants_text  # "Outro"
        modal = AskChoice("Q?", [{"label": "A"}, {"label": "B"}])
        assert modal.on_key("escape") and modal.answers == []

    def test_multi_select(self) -> None:
        from orion.tui.modal import AskChoice

        modal = AskChoice("Q?", [{"label": "A"}, {"label": "B"}, {"label": "C"}], multi=True)
        assert not modal.on_key(" ")
        modal.on_key("down")
        modal.on_key("down")
        modal.on_key(" ")
        assert modal.on_key("enter") and modal.answers == ["A", "C"]

    async def test_non_interactive_returns_none_and_denies_plan(self) -> None:
        from orion.tui.modal import approve_plan, ask_user_choice

        console = Console(file=io.StringIO())
        assert await ask_user_choice(console, "Q?", [{"label": "A"}]) is None
        assert await approve_plan(console, "# plano", "auto") is False

    def test_plan_approval_keys(self) -> None:
        from orion.tui.modal import PlanApproval

        yes = PlanApproval("p", "auto")
        assert yes.on_key("y") and yes.approved
        no = PlanApproval("p", "auto")
        assert no.on_key("n") and not no.approved
        assert not PlanApproval("p", "auto").on_key("x")


class TestCleanStartup:
    def test_logging_goes_to_file_not_stderr(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        root = logging.getLogger()
        saved = list(root.handlers), root.level
        try:
            log = configure_logging(tmp_path)
            logging.getLogger("orion.mcp.client").warning("Skipping MCP server serena: boom")
            for h in root.handlers:
                h.flush()
            assert log is not None and "Skipping MCP server serena" in log.read_text()
            assert capsys.readouterr().err == ""
        finally:
            for h in list(root.handlers):
                if h not in saved[0]:
                    root.removeHandler(h)
                    h.close()
            root.handlers[:] = saved[0]
            root.setLevel(saved[1])

    async def test_mcp_server_stderr_is_redirected_to_a_log_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
    ) -> None:
        from orion.mcp.client import MCPClient
        from orion.mcp.models import MCPServerConfig
        from orion.mcp.transports import server_log_path

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        noisy = tmp_path / "noisy.py"
        noisy.write_text(
            "import sys\n"
            "sys.stderr.write('NOISE-FROM-NPX-INSTALL\\n'); sys.stderr.flush()\n"
            + (Path(__file__).parents[1] / "fixtures" / "echo_mcp_server.py").read_text()
        )
        cfg = MCPServerConfig(name="no isy/1", command="python", args=[str(noisy)])
        client = MCPClient({"n": cfg}, connect_timeout=30)
        await client.start()
        try:
            assert client.servers["n"].status == "connected", client.servers["n"].error
        finally:
            await client.close()
        assert "NOISE-FROM-NPX-INSTALL" not in capfd.readouterr().err
        log = server_log_path("no isy/1")
        assert log.parent == tmp_path / ".orion" / "logs" and log.name == "mcp-no_isy_1.log"
        assert "NOISE-FROM-NPX-INSTALL" in log.read_text()

    def test_dock_to_bottom_pads_only_on_a_real_terminal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from orion.tui.prompt import InteractivePrompt

        buf = io.StringIO()
        monkeypatch.setattr("shutil.get_terminal_size", lambda fallback=(80, 24): __import__("os").terminal_size((80, 40)))
        prompt = InteractivePrompt(history_path="/tmp/orion-test-history", console=Console(file=buf, force_terminal=False))
        prompt.dock_to_bottom(10)
        assert buf.getvalue() == ""  # sem TTY: nada
        tty = Console(file=buf, force_terminal=True)
        prompt = InteractivePrompt(history_path="/tmp/orion-test-history", console=tty)
        prompt.dock_to_bottom(10)
        assert buf.getvalue().count("\n") == 40 - 10 - 4 - 1 + 1  # prompt + barra + folga reservados
        buf.truncate(0)
        buf.seek(0)
        prompt.dock_to_bottom(60)  # banner maior que a tela: não imprime
        assert buf.getvalue() == ""


def test_describe_action_flags_background_commands() -> None:
    """F-01: o modal avisa que o comando continua rodando após a aprovação."""
    from orion.tui.panels import describe_action

    _, _, sync_impact = describe_action("run_command", {"command": "sleep 1"})
    _, _, bg_impact = describe_action("run_command", {"command": "sleep 1", "run_in_background": True})
    assert "segundo plano" not in sync_impact
    assert "segundo plano" in bg_impact


def test_plan_approval_renders_markdown_not_raw() -> None:
    """F-04: '# Plano' não pode aparecer literal."""
    from io import StringIO

    from rich.console import Console

    buf = StringIO()
    Console(file=buf, width=80, force_terminal=False).print(render_plan_approval("# Plano\n- passo", "auto"))
    out = buf.getvalue()
    assert "# Plano" not in out
    assert "Plano" in out and "passo" in out


def test_prompt_has_rules_above_and_below_the_input() -> None:
    """F-08: réguas são Windows do HSplit (crescem com o input), uma acima e uma abaixo."""
    from prompt_toolkit.layout.containers import Window

    from orion.tui.prompt import InteractivePrompt

    children = InteractivePrompt(history_path=None).session.layout.container.children  # type: ignore[attr-defined]
    rules = [i for i, c in enumerate(children) if isinstance(c, Window) and c.char == "─"]
    assert len(rules) == 2
    assert rules[1] - rules[0] == 2  # o input fica entre as duas


def test_prompt_input_does_not_stretch_and_rules_are_light() -> None:
    """F-08: o input não absorve altura extra (réguas seguem o texto) e a régua é clara."""
    from prompt_toolkit.layout.controls import BufferControl

    from orion.tui.prompt import InteractivePrompt, get_prompt_style
    from orion.tui.theme import ORION_COLORS

    prompt = InteractivePrompt(history_path=None)
    inputs = [
        w
        for w in prompt.session.layout.find_all_windows()
        if isinstance(w.content, BufferControl) and w.content.buffer is prompt.session.default_buffer
    ]
    assert inputs and all(w.dont_extend_height() for w in inputs)
    rules = dict(get_prompt_style().style_rules)
    assert ORION_COLORS["text_primary"].lstrip("#").lower() in rules["prompt.border"].lower()
