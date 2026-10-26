"""
O.R.I.O.N — Testes E2E: Continuidade Cognitiva & Memória das 5 Esferas (v0.2.0)

Valida o ciclo cognitivo completo com o subsistema de memória integrado:
  1. Injeção do Cognitive Manifest (< 250 tokens), Identidade Jarvis e Skills no Prompt do ReActEngine
  2. Execução de ferramentas cognitivas no ReAct loop através do PEP:
     - inspect_environment
     - memorize
     - use_skill (system-doctor)
     - recall
  3. Barreira de anti-poisoning em tempo real durante a execução do ReAct
  4. Dynamic Context Compaction com preservação de vital tail e arquivos ativos
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from orion.core.engine import LLMResponse, ReActEngine
from orion.core.event_bus import EventBus
from orion.core.identity import IdentityManager
from orion.governance.pep import AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import WorkspaceScope
from orion.memory.facts_store import FactsStore
from orion.memory.manifest import CognitiveManifestGenerator
from orion.memory.models import FactCategory, FactStatus
from orion.runtime.environment import EnvironmentMonitor
from orion.runtime.local_provider import LocalRuntimeProvider
from orion.skills.engine import SkillsEngine
from orion.skills.loader import SkillsLoader
from orion.timeline.compactor import ContextCompactor, TurnData


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def scope(workspace: Path) -> WorkspaceScope:
    return WorkspaceScope(roots=[workspace])


@pytest.fixture
def pep(scope: WorkspaceScope) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(scope=scope, mode=AutonomyMode.FULLY_AUTO)


@pytest.fixture
def facts_store(tmp_path: Path) -> FactsStore:
    store = FactsStore(db_path=tmp_path / "test_facts.db")
    store.initialize()
    yield store
    store.close()


@pytest.fixture
def env_monitor() -> EnvironmentMonitor:
    return EnvironmentMonitor()


@pytest.fixture
def identity_mgr(tmp_path: Path) -> IdentityManager:
    return IdentityManager(persona_path=tmp_path / "persona.json")


@pytest.fixture
def skills_engine() -> SkillsEngine:
    loader = SkillsLoader(workspace_dir=None, global_dir=None)
    engine = SkillsEngine(loader)
    engine.reload()
    return engine


# ---------------------------------------------------------------------------
# Teste E2E 1: Fluxo Completo de Continuidade Cognitiva
# ---------------------------------------------------------------------------


class TestCognitiveContinuityE2E:
    @pytest.mark.asyncio
    async def test_full_cognitive_react_loop(
        self,
        workspace: Path,
        pep: PolicyEnforcementPoint,
        facts_store: FactsStore,
        env_monitor: EnvironmentMonitor,
        identity_mgr: IdentityManager,
        skills_engine: SkillsEngine,
    ) -> None:
        """
        Executa um fluxo ReAct multi-turnos completo onde o agente:
          Turno 0: Inspeciona o hardware (inspect_environment)
          Turno 1: Memoriza uma regra de arquitetura confirmada (memorize)
          Turno 2: Ativa a habilidade nativa (use_skill)
          Turno 3: Recupera os fatos estruturados (recall)
          Turno 4: Conclui com FinalAnswer
        """
        bus = EventBus()
        runtime = LocalRuntimeProvider(
            pep=pep,
            scope=pep.scope,
            facts_store=facts_store,
            environment_monitor=env_monitor,
            skills_engine=skills_engine,
        )

        manifest_gen = CognitiveManifestGenerator.from_live_data(
            user_name="Daniel",
            call_sign="Senhor",
            project_root=workspace,
            confirmed_facts_count=0,
            timeline_event_count=10,
            available_skills_count=1,
        )

        # Sequência planejada de respostas do LLM stub
        scripted_responses: list[LLMResponse] = [
            # Turno 0: Inspecionar ambiente
            ("tool_call", "inspect_environment", {}),
            # Turno 1: Memorizar decisão arquitetural confirmada
            (
                "tool_call",
                "memorize",
                {
                    "key": "primary_database",
                    "value": "SQLite WAL",
                    "category": "INFRASTRUCTURE",
                    "status": "CONFIRMED",
                    "source": "user",
                },
            ),
            # Turno 2: Ativar skill de diagnóstico
            ("tool_call", "use_skill", {"skill_name": "system-doctor"}),
            # Turno 3: Fazer recall da regra
            ("tool_call", "recall", {"query": "primary_database"}),
            # Turno 4: Finalizar resposta
            ("final_answer", "Ambiente auditado, regra gravada e skill carregada com sucesso, Senhor."),
        ]

        turn_counter = 0

        async def scripted_llm(prompt: str) -> LLMResponse:
            nonlocal turn_counter
            # Validação no prompt do Turno 0
            if turn_counter == 0:
                assert "Daniel Ribeiro" in prompt
                assert "Jarvis" in prompt
                assert "<COGNITIVE_MANIFEST>" in prompt
                assert "<AVAILABLE_SKILLS>" in prompt
                assert "system-doctor" in prompt

            resp = scripted_responses[turn_counter]
            turn_counter += 1
            return resp

        engine = ReActEngine(
            event_bus=bus,
            llm=scripted_llm,
            max_turns=10,
            runtime=runtime,
            identity_manager=identity_mgr,
            manifest_generator=manifest_gen,
            skills_engine=skills_engine,
        )

        final_result = await engine.run("Audite o sistema e prepare o ambiente operacional.")

        assert "Senhor" in final_result
        assert "sucesso" in final_result
        assert turn_counter == 5

        # Verificação do estado persistido no FactsStore
        saved_fact = facts_store.get("primary_database")
        assert saved_fact is not None
        assert saved_fact.value == "SQLite WAL"
        assert saved_fact.status == FactStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_anti_poisoning_in_react_loop(
        self,
        pep: PolicyEnforcementPoint,
        facts_store: FactsStore,
        env_monitor: EnvironmentMonitor,
    ) -> None:
        """
        Valida que o loop ReAct bloqueia tentativas de sobrescrita de fatos CONFIRMED
        com inferências soltas (anti-poisoning).
        """
        # Fato previamente confirmado pelo usuário
        facts_store.upsert(
            from_key="auth_standard",
            fact=facts_store.get("auth_standard")
            or facts_store.upsert(
                from_key="auth_standard",
                fact=None,  # helper will insert
            )
            if False
            else None,
        ) if False else None

        from orion.memory.models import FactEntry

        facts_store.upsert(
            FactEntry(
                key="security_rule",
                value="strict_ed25519",
                category=FactCategory.CODING_STANDARD,
                status=FactStatus.CONFIRMED,
            )
        )

        runtime = LocalRuntimeProvider(
            pep=pep,
            scope=pep.scope,
            facts_store=facts_store,
            environment_monitor=env_monitor,
        )

        scripted_responses: list[LLMResponse] = [
            # O modelo tenta inferir e sobrescrever uma regra confirmada
            (
                "tool_call",
                "memorize",
                {
                    "key": "security_rule",
                    "value": "insecure_md5",
                    "category": "CODING_STANDARD",
                    "status": "INFERRED",
                },
            ),
            ("final_answer", "Tentativa concluída."),
        ]
        turn_counter = 0

        async def scripted_llm(_prompt: str) -> LLMResponse:
            nonlocal turn_counter
            resp = scripted_responses[turn_counter]
            turn_counter += 1
            return resp

        engine = ReActEngine(
            event_bus=EventBus(),
            llm=scripted_llm,
            max_turns=5,
            runtime=runtime,
        )

        await engine.run("Tente atualizar a regra de segurança.")

        # A regra no FactsStore NÃO deve ter sido corrompida
        fact = facts_store.get("security_rule")
        assert fact is not None
        assert fact.value == "strict_ed25519"
        assert fact.status == FactStatus.CONFIRMED

    def test_e2e_compactor_integration(self) -> None:
        """Valida que o compactor opera no histórico completo do ReAct."""
        compactor = ContextCompactor(threshold_percent=0.80, vital_tail_count=3)

        turns = [
            TurnData(
                turn_index=i,
                user_input=f"Turno {i}",
                tool_name="read_file",
                tool_output="x" * 500,  # Saída volumosa
                modified_files=["src/auth.py"] if i == 5 else [],
            )
            for i in range(20)
        ]

        result = compactor.compact(turns)
        assert result.original_turns == 20
        assert result.preserved_tail_turns == 3
        assert "src/auth.py" in result.active_files
        assert result.tokens_saved > 0
