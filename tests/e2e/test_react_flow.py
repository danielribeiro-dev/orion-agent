"""
O.R.I.O.N — Testes E2E: Fluxo ReAct Ponta a Ponta (Sprint 4)

Valida o ciclo cognitivo completo:
  Meta do usuário → Turn Budgeting → Tool Calls → PEP → LocalRuntimeProvider
  → Observation → Artefato Markdown Estruturado

Todos os testes rodam com:
  - PEP em modo FULLY_AUTO (sem prompt interativo)
  - WorkspaceScope apontando para tmp_path (isolamento)
  - LLM substituído por stubs assíncronos determinísticos
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from orion.artifacts.store import ArtifactStore
from orion.config import PathsConfig
from orion.core.engine import ReActEngine
from orion.core.errors import TurnBudgetExceeded
from orion.core.event_bus import EventBus
from orion.core.events import (
    Action,
    ActionEmitted,
    FinalAnswer,
    Observation,
    ObservationReceived,
    RiskLevel,
    Thinking,
    TurnCompleted,
    TurnStarted,
)
from orion.governance.audit import AuditLogger
from orion.governance.pep import AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import WorkspaceScope
from orion.runtime.local_provider import LocalRuntimeProvider


# ---------------------------------------------------------------------------
# Fixtures compartilhados
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Diretório temporário isolado usado como workspace autorizado."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture()
def scope(workspace: Path) -> WorkspaceScope:
    return WorkspaceScope(roots=[workspace])


@pytest.fixture()
def audit_log(tmp_path: Path) -> Path:
    return tmp_path / "audit.log"


@pytest.fixture()
def pep(scope: WorkspaceScope, audit_log: Path) -> PolicyEnforcementPoint:
    """PEP em FULLY_AUTO para testes sem interação humana."""
    return PolicyEnforcementPoint(
        scope=scope,
        mode=AutonomyMode.FULLY_AUTO,
        audit_logger=AuditLogger(log_path=audit_log),
    )


@pytest.fixture()
def runtime(pep: PolicyEnforcementPoint, scope: WorkspaceScope) -> LocalRuntimeProvider:
    return LocalRuntimeProvider(pep=pep, scope=scope)


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def artifact_store(tmp_path: Path) -> ArtifactStore:
    paths = PathsConfig(
        global_home=tmp_path / ".orion_global",
        local_home=tmp_path / ".orion_local",
    )
    return ArtifactStore(paths=paths, session_id="e2e-test-session")


# ---------------------------------------------------------------------------
# Helpers de LLM stub
# ---------------------------------------------------------------------------


def _llm_final(answer: str):
    """Stub LLM que responde imediatamente com uma FinalAnswer."""
    async def _llm(_prompt: str):
        return ("final_answer", answer)
    return _llm


def _llm_sequence(*responses):
    """Stub LLM que emite respostas em sequência (tool_calls + final)."""
    call_count = 0

    async def _llm(_prompt: str):
        nonlocal call_count
        resp = responses[min(call_count, len(responses) - 1)]
        call_count += 1
        return resp

    return _llm


# ---------------------------------------------------------------------------
# TC-E2E-01: Resposta direta sem tool calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_direct_final_answer(bus: EventBus, runtime: LocalRuntimeProvider):
    """Fluxo mais simples: LLM responde diretamente sem nenhuma ferramenta."""
    events_received: list[str] = []

    async def _on_turn_started(e: TurnStarted) -> None:
        events_received.append("TurnStarted")

    async def _on_final_answer(e: FinalAnswer) -> None:
        events_received.append("FinalAnswer")

    async def _on_turn_completed(e: TurnCompleted) -> None:
        events_received.append("TurnCompleted")

    bus.subscribe_handler(TurnStarted, _on_turn_started)
    bus.subscribe_handler(FinalAnswer, _on_final_answer)
    bus.subscribe_handler(TurnCompleted, _on_turn_completed)

    engine = ReActEngine(
        event_bus=bus,
        llm=_llm_final("Olá! Sou o ORION."),
        max_turns=5,
        runtime=runtime,
    )

    result = await engine.run("Quem és tu?")

    assert result == "Olá! Sou o ORION."
    assert "TurnStarted" in events_received
    assert "FinalAnswer" in events_received
    assert "TurnCompleted" in events_received


# ---------------------------------------------------------------------------
# TC-E2E-02: Loop ReAct com read_file → FinalAnswer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_read_file_then_answer(
    bus: EventBus,
    runtime: LocalRuntimeProvider,
    workspace: Path,
):
    """Ciclo completo: LLM lê um arquivo e depois emite FinalAnswer."""
    # Prepara arquivo de conteúdo no workspace
    target_file = workspace / "info.txt"
    target_file.write_text("ORION v0.1.0 — Release Notes\n", encoding="utf-8")

    observations_received: list[Observation] = []

    async def _on_obs(e: Observation) -> None:
        observations_received.append(e)

    bus.subscribe_handler(Observation, _on_obs)

    llm = _llm_sequence(
        ("tool_call", "read_file", {"path": str(target_file)}, RiskLevel.SAFE, "Preciso ler o arquivo"),
        ("final_answer", "Conteúdo lido com sucesso: ORION v0.1.0 — Release Notes"),
    )

    engine = ReActEngine(
        event_bus=bus,
        llm=llm,
        max_turns=5,
        runtime=runtime,
    )

    result = await engine.run("Leia o arquivo info.txt e me diga o que está lá.")

    assert "Release Notes" in result
    assert len(observations_received) == 1
    assert observations_received[0].success is True
    assert "ORION v0.1.0" in observations_received[0].output


# ---------------------------------------------------------------------------
# TC-E2E-03: Loop ReAct com write_file → FinalAnswer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_write_file_then_answer(
    bus: EventBus,
    runtime: LocalRuntimeProvider,
    workspace: Path,
):
    """Ciclo completo: LLM escreve um arquivo e confirma com FinalAnswer."""
    output_file = workspace / "output.txt"

    actions_emitted: list[ActionEmitted] = []

    async def _on_action_emitted(e: ActionEmitted) -> None:
        actions_emitted.append(e)

    bus.subscribe_handler(ActionEmitted, _on_action_emitted)

    llm = _llm_sequence(
        (
            "tool_call",
            "write_file",
            {"path": str(output_file), "content": "Arquivo gerado pelo ORION\n"},
            RiskLevel.CONTROLLED,
            "Vou criar o arquivo solicitado",
        ),
        ("final_answer", "Arquivo criado com sucesso."),
    )

    engine = ReActEngine(
        event_bus=bus,
        llm=llm,
        max_turns=5,
        runtime=runtime,
    )

    result = await engine.run("Crie um arquivo output.txt no workspace.")

    assert "sucesso" in result
    assert output_file.exists()
    assert output_file.read_text(encoding="utf-8") == "Arquivo gerado pelo ORION\n"
    assert len(actions_emitted) == 1
    assert actions_emitted[0].tool == "write_file"


# ---------------------------------------------------------------------------
# TC-E2E-04: Loop ReAct com run_command → FinalAnswer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_run_command_then_answer(
    bus: EventBus,
    runtime: LocalRuntimeProvider,
):
    """Ciclo completo: LLM executa um comando shell seguro."""
    obs_list: list[Observation] = []

    async def _on_obs(e: Observation) -> None:
        obs_list.append(e)

    bus.subscribe_handler(Observation, _on_obs)

    llm = _llm_sequence(
        (
            "tool_call",
            "run_command",
            {"command": "echo 'orion_e2e_ok'"},
            RiskLevel.CRITICAL,
            "Vou verificar o ambiente",
        ),
        ("final_answer", "Comando executado. Output: orion_e2e_ok"),
    )

    engine = ReActEngine(
        event_bus=bus,
        llm=llm,
        max_turns=5,
        runtime=runtime,
    )

    result = await engine.run("Execute echo orion_e2e_ok.")

    assert "Comando executado" in result
    assert len(obs_list) == 1
    assert "orion_e2e_ok" in obs_list[0].output


# ---------------------------------------------------------------------------
# TC-E2E-05: Ciclo multi-turn (read → edit → answer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_multi_turn_read_edit_answer(
    bus: EventBus,
    runtime: LocalRuntimeProvider,
    workspace: Path,
):
    """Multi-turn: lê arquivo, edita-o cirurgicamente e emite resposta final."""
    target = workspace / "doc.md"
    target.write_text("# Título\nConteúdo original.", encoding="utf-8")

    turn_started_count = 0

    async def _count_turns(e: TurnStarted) -> None:
        nonlocal turn_started_count
        turn_started_count += 1

    bus.subscribe_handler(TurnStarted, _count_turns)

    llm = _llm_sequence(
        (
            "tool_call",
            "read_file",
            {"path": str(target)},
            RiskLevel.SAFE,
            "Vou ler o arquivo antes de editar",
        ),
        (
            "tool_call",
            "edit_file",
            {"path": str(target), "target": "Conteúdo original.", "replacement": "Conteúdo atualizado pelo ORION."},
            RiskLevel.CONTROLLED,
            "Agora vou aplicar a edição cirúrgica",
        ),
        ("final_answer", "Arquivo editado com sucesso."),
    )

    engine = ReActEngine(
        event_bus=bus,
        llm=llm,
        max_turns=10,
        runtime=runtime,
    )

    result = await engine.run("Leia doc.md e substitua 'Conteúdo original.' por 'Conteúdo atualizado pelo ORION.'")

    assert "editado" in result
    assert turn_started_count == 3  # 3 turns: read + edit + final
    updated_text = target.read_text(encoding="utf-8")
    assert "Conteúdo atualizado pelo ORION." in updated_text
    assert "Conteúdo original." not in updated_text


# ---------------------------------------------------------------------------
# TC-E2E-06: Turn Budget Exceeded (sem FinalAnswer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_turn_budget_exceeded(bus: EventBus, runtime: LocalRuntimeProvider):
    """Engine deve levantar TurnBudgetExceeded quando max_turns é atingido."""
    turn_completed_events: list[TurnCompleted] = []

    async def _on_turn_completed(e: TurnCompleted) -> None:
        turn_completed_events.append(e)

    bus.subscribe_handler(TurnCompleted, _on_turn_completed)

    async def _llm_infinite(_prompt: str):
        return ("tool_call", "run_command", {"command": "echo loop"}, RiskLevel.CRITICAL, None)

    engine = ReActEngine(
        event_bus=bus,
        llm=_llm_infinite,
        max_turns=3,
        runtime=runtime,
    )

    with pytest.raises(TurnBudgetExceeded) as exc_info:
        await engine.run("Faça algo sem terminar.")

    assert exc_info.value.max_turns == 3
    assert len(turn_completed_events) == 1
    assert turn_completed_events[0].success is False


# ---------------------------------------------------------------------------
# TC-E2E-07: Artefato Markdown gerado e persistido após loop ReAct
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_artifact_generation(
    bus: EventBus,
    runtime: LocalRuntimeProvider,
    artifact_store: ArtifactStore,
):
    """Valida criação de artefato estruturado após o ciclo ReAct."""
    engine = ReActEngine(
        event_bus=bus,
        llm=_llm_final("Análise concluída."),
        max_turns=5,
        runtime=runtime,
    )

    result = await engine.run("Analise o projeto e gere um relatório.")
    assert result == "Análise concluída."

    # Simula geração de artefato markdown como o motor faria no v0.3.0+
    artifact = artifact_store.create(
        filename="analysis_report.md",
        content=(
            "# Relatório de Análise\n\n"
            "**Gerado por:** O.R.I.O.N v0.1.0\n\n"
            "## Resumo\n\nAnálise concluída com sucesso.\n"
        ),
        summary="Relatório de análise gerado pelo ciclo ReAct E2E.",
        user_facing=True,
        request_feedback=False,
    )

    assert artifact.filename == "analysis_report.md"
    assert artifact.metadata.user_facing is True
    assert artifact.metadata.global_path is not None
    assert artifact.metadata.global_path.exists()
    assert "Relatório de Análise" in artifact.metadata.global_path.read_text(encoding="utf-8")

    retrieved = artifact_store.get(artifact.artifact_id)
    assert retrieved.artifact_id == artifact.artifact_id

    user_facing = artifact_store.list_user_facing()
    assert any(a.artifact_id == artifact.artifact_id for a in user_facing)


# ---------------------------------------------------------------------------
# TC-E2E-08: EventBus — todos os eventos do fluxo ReAct são emitidos em ordem
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_event_stream_completeness(
    bus: EventBus,
    runtime: LocalRuntimeProvider,
    workspace: Path,
):
    """Garante que todos os eventos esperados são emitidos em ordem."""
    event_log: list[str] = []

    async def _log_turn_started(e: TurnStarted) -> None:
        event_log.append("TurnStarted")

    async def _log_thinking(e: Thinking) -> None:
        event_log.append("Thinking")

    async def _log_action_emitted(e: ActionEmitted) -> None:
        event_log.append("ActionEmitted")

    async def _log_obs_received(e: ObservationReceived) -> None:
        event_log.append("ObservationReceived")

    async def _log_observation(e: Observation) -> None:
        event_log.append("Observation")

    async def _log_final_answer(e: FinalAnswer) -> None:
        event_log.append("FinalAnswer")

    async def _log_turn_completed(e: TurnCompleted) -> None:
        event_log.append("TurnCompleted")

    bus.subscribe_handler(TurnStarted, _log_turn_started)
    bus.subscribe_handler(Thinking, _log_thinking)
    bus.subscribe_handler(ActionEmitted, _log_action_emitted)
    bus.subscribe_handler(ObservationReceived, _log_obs_received)
    bus.subscribe_handler(Observation, _log_observation)
    bus.subscribe_handler(FinalAnswer, _log_final_answer)
    bus.subscribe_handler(TurnCompleted, _log_turn_completed)

    target = workspace / "target.txt"
    target.write_text("hello orion", encoding="utf-8")

    llm = _llm_sequence(
        ("tool_call", "read_file", {"path": str(target)}, RiskLevel.SAFE, "Lendo"),
        ("final_answer", "Pronto."),
    )

    engine = ReActEngine(
        event_bus=bus,
        llm=llm,
        max_turns=5,
        runtime=runtime,
    )

    await engine.run("Leia target.txt.")

    # Verifica ordenação dos eventos por turn
    assert event_log.index("TurnStarted") < event_log.index("ActionEmitted")
    assert event_log.index("ActionEmitted") < event_log.index("ObservationReceived")
    assert event_log.index("ObservationReceived") < event_log.index("FinalAnswer")
    assert event_log.index("FinalAnswer") < event_log.index("TurnCompleted")
    assert event_log.count("TurnCompleted") == 1
    assert event_log[-1] == "TurnCompleted"


# ---------------------------------------------------------------------------
# TC-E2E-09: search_files dentro do workspace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_search_files(
    bus: EventBus,
    runtime: LocalRuntimeProvider,
    workspace: Path,
):
    """Valida search_files como parte de um ciclo ReAct."""
    (workspace / "alpha.py").write_text("def hello(): pass\n", encoding="utf-8")
    (workspace / "beta.py").write_text("def world(): pass\n", encoding="utf-8")

    obs_list: list[Observation] = []

    async def _on_obs(e: Observation) -> None:
        obs_list.append(e)

    bus.subscribe_handler(Observation, _on_obs)

    llm = _llm_sequence(
        (
            "tool_call",
            "search_files",
            {"path": str(workspace), "pattern": "*.py"},
            RiskLevel.SAFE,
            "Vou listar os arquivos Python",
        ),
        ("final_answer", "Encontrei os arquivos Python."),
    )

    engine = ReActEngine(
        event_bus=bus,
        llm=llm,
        max_turns=5,
        runtime=runtime,
    )

    result = await engine.run("Liste os arquivos .py no workspace.")

    assert "Python" in result
    assert len(obs_list) == 1
    assert obs_list[0].success is True


# ---------------------------------------------------------------------------
# TC-E2E-10: Token accounting — Prompt assembly contém delimitadores corretos
# ---------------------------------------------------------------------------


def test_e2e_prompt_assembly_delimiters():
    """Verifica que o prompt montado contém todos os delimitadores formais."""
    from orion.core.engine import (
        DELIM_CONTEXT_END,
        DELIM_CONTEXT_START,
        DELIM_SYSTEM_END,
        DELIM_SYSTEM_START,
        DELIM_TOOL_END,
        DELIM_TOOL_START,
        DELIM_USER_END,
        DELIM_USER_START,
    )

    bus = EventBus()
    engine = ReActEngine(
        event_bus=bus,
        llm=_llm_final("ok"),
        max_turns=5,
    )

    # Turno 0 sem observações
    prompt_0 = engine._assemble_prompt("Qual o status?", 0)
    assert DELIM_SYSTEM_START in prompt_0
    assert DELIM_SYSTEM_END in prompt_0
    assert DELIM_USER_START in prompt_0
    assert DELIM_USER_END in prompt_0
    assert "Qual o status?" in prompt_0
    # Sem observações — bloco de contexto não deve aparecer
    assert DELIM_CONTEXT_START not in prompt_0

    # Injeta uma observação manualmente para testar o bloco de contexto
    engine._observations.append(
        Observation(action_id="test-id-001", success=True, output="resultado da ferramenta")
    )

    prompt_1 = engine._assemble_prompt("Qual o status?", 1)
    assert DELIM_CONTEXT_START in prompt_1
    assert DELIM_CONTEXT_END in prompt_1
    assert DELIM_TOOL_START in prompt_1
    assert DELIM_TOOL_END in prompt_1
    assert "resultado da ferramenta" in prompt_1
    assert "4 turns remaining" in prompt_1  # max_turns(5) - turn_index(1)
