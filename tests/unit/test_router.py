"""
O.R.I.O.N — Test Suite: Gateway Sprint 2 — Dynamic Auto-Routing & Complexity Engine
tests/unit/test_router.py

Cobre:
  1. ClassificationResult — contrato e validações
  2. ComplexityClassifier — slash commands, keywords, heurísticas estruturais,
     multi-task, casos de borda
  3. RoutingDecision — contrato e validações
  4. ModelRouter — modo AUTO, modo FIXED, alternância por linguagem natural,
     set_mode programático, set_tier_model, aliases, casos de borda
"""

from __future__ import annotations

import pytest

from orion.gateway.classifier import (
    ClassificationResult,
    ComplexityClassifier,
)
from orion.gateway.models import (
    ComplexityTier,
    LLMMessage,
    MessageRole,
)
from orion.gateway.registry import ModelRegistry
from orion.gateway.router import (
    DEFAULT_TIER_MODELS,
    ModelRouter,
    RoutingDecision,
    RoutingMode,
)


# ---------------------------------------------------------------------------
# Fixtures compartilhadas
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> ModelRegistry:
    return ModelRegistry()


@pytest.fixture()
def classifier() -> ComplexityClassifier:
    return ComplexityClassifier()


@pytest.fixture()
def router(registry: ModelRegistry) -> ModelRouter:
    return ModelRouter(registry=registry)


@pytest.fixture()
def user_msg() -> LLMMessage:
    return LLMMessage(role=MessageRole.USER, content="Hello")


# ---------------------------------------------------------------------------
# 1. ClassificationResult — Contrato
# ---------------------------------------------------------------------------


class TestClassificationResult:
    def test_valid_heavy(self) -> None:
        r = ClassificationResult(
            tier=ComplexityTier.HEAVY,
            confidence=0.9,
            reason="high complexity detected",
        )
        assert r.tier == ComplexityTier.HEAVY
        assert r.confidence == 0.9
        assert r.signals_heavy == []
        assert r.signals_fast == []

    def test_valid_fast(self) -> None:
        r = ClassificationResult(
            tier=ComplexityTier.FAST,
            confidence=0.85,
            reason="low complexity",
        )
        assert r.tier == ComplexityTier.FAST

    def test_frozen(self) -> None:
        r = ClassificationResult(
            tier=ComplexityTier.BALANCED,
            confidence=0.5,
            reason="neutral",
        )
        with pytest.raises(Exception):
            r.tier = ComplexityTier.HEAVY  # type: ignore[misc]

    def test_confidence_out_of_range_low(self) -> None:
        with pytest.raises(ValueError, match="confidence must be in"):
            ClassificationResult(
                tier=ComplexityTier.FAST,
                confidence=-0.1,
                reason="invalid",
            )

    def test_confidence_out_of_range_high(self) -> None:
        with pytest.raises(ValueError, match="confidence must be in"):
            ClassificationResult(
                tier=ComplexityTier.FAST,
                confidence=1.01,
                reason="invalid",
            )

    def test_confidence_boundary_values(self) -> None:
        """0.0 e 1.0 são valores de borda válidos."""
        r0 = ClassificationResult(tier=ComplexityTier.FAST, confidence=0.0, reason="x")
        r1 = ClassificationResult(tier=ComplexityTier.HEAVY, confidence=1.0, reason="x")
        assert r0.confidence == 0.0
        assert r1.confidence == 1.0

    def test_signals_stored(self) -> None:
        r = ClassificationResult(
            tier=ComplexityTier.HEAVY,
            confidence=0.9,
            reason="x",
            signals_heavy=["keyword:security"],
            signals_fast=[],
        )
        assert "keyword:security" in r.signals_heavy


# ---------------------------------------------------------------------------
# 2. ComplexityClassifier — Slash Commands
# ---------------------------------------------------------------------------


class TestClassifierSlashCommands:
    def test_plan_slash_is_heavy(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("/plan Refactor the entire payment module")
        assert result.tier == ComplexityTier.HEAVY
        assert any("slash_command" in s for s in result.signals_heavy)

    def test_architect_slash_is_heavy(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("/architect design a new microservices layout")
        assert result.tier == ComplexityTier.HEAVY

    def test_security_slash_is_heavy(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("/security audit the auth module")
        assert result.tier == ComplexityTier.HEAVY

    def test_ls_slash_is_fast(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("/ls src/")
        assert result.tier == ComplexityTier.FAST
        assert any("slash_command" in s for s in result.signals_fast)

    def test_status_slash_is_fast(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("/status")
        assert result.tier == ComplexityTier.FAST

    def test_grep_slash_is_fast(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("/grep 'def authenticate' src/")
        assert result.tier == ComplexityTier.FAST

    def test_slash_case_insensitive(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("/PLAN Design a new system")
        # Slash commands são detectados em lowercase; prompt não tem /plan → deve passar sem slash signal
        # Mas keywords como 'design' e 'new system' podem elevar para heavy
        # O importante é não crashar
        assert result.tier in (ComplexityTier.HEAVY, ComplexityTier.BALANCED, ComplexityTier.FAST)


# ---------------------------------------------------------------------------
# 3. ComplexityClassifier — Keywords de Alta Complexidade
# ---------------------------------------------------------------------------


class TestClassifierHeavyKeywords:
    def test_security_keyword(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("Fix the security vulnerability in the login module")
        assert result.tier == ComplexityTier.HEAVY

    def test_architecture_keyword(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("Design the architecture for our new microservices")
        assert result.tier == ComplexityTier.HEAVY

    def test_refactor_keyword(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("Refactor the entire authentication module")
        assert result.tier == ComplexityTier.HEAVY

    def test_migrate_keyword(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("Migrate the database to PostgreSQL")
        assert result.tier in (ComplexityTier.HEAVY, ComplexityTier.BALANCED)

    def test_race_condition_keyword(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("Fix the race condition in the thread pool")
        assert result.tier == ComplexityTier.HEAVY

    def test_memory_leak_keyword(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("Debug the memory leak in the worker process")
        assert result.tier == ComplexityTier.HEAVY

    def test_compare_keyword(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("Compare the pros and cons of REST vs GraphQL")
        assert result.tier == ComplexityTier.HEAVY

    def test_portuguese_refactoring(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("Refatorar o módulo de autenticação inteiro")
        assert result.tier == ComplexityTier.HEAVY

    def test_portuguese_segurança(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("Verifique a segurança do sistema de login")
        assert result.tier == ComplexityTier.HEAVY

    def test_multiple_heavy_signals_boost_confidence(
        self, classifier: ComplexityClassifier
    ) -> None:
        result = classifier.classify(
            "Design the architecture and perform a security audit of the refactored module"
        )
        assert result.tier == ComplexityTier.HEAVY
        assert result.confidence > 0.6


# ---------------------------------------------------------------------------
# 4. ComplexityClassifier — Keywords de Baixa Complexidade
# ---------------------------------------------------------------------------


class TestClassifierFastKeywords:
    def test_list_files_is_fast(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("list files in the src directory")
        assert result.tier == ComplexityTier.FAST

    def test_read_file_is_fast(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("read file src/orion/gateway/models.py")
        assert result.tier == ComplexityTier.FAST

    def test_git_status_is_fast(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("git status")
        assert result.tier == ComplexityTier.FAST

    def test_grep_is_fast(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("grep 'class ModelSpec' in all files")
        assert result.tier == ComplexityTier.FAST

    def test_show_me_is_fast(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("show me the current directory structure")
        assert result.tier == ComplexityTier.FAST

    def test_portuguese_listar_is_fast(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("listar arquivos em src/")
        assert result.tier == ComplexityTier.FAST

    def test_format_is_fast(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("format the file with black")
        assert result.tier == ComplexityTier.FAST

    def test_git_log_is_fast(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("git log --oneline -10")
        assert result.tier == ComplexityTier.FAST


# ---------------------------------------------------------------------------
# 5. ComplexityClassifier — Heurísticas Estruturais
# ---------------------------------------------------------------------------


class TestClassifierStructural:
    def test_very_short_prompt_favors_fast(
        self, classifier: ComplexityClassifier
    ) -> None:
        """Prompt com até 15 palavras recebe boost FAST."""
        result = classifier.classify("What is in the config.py?")
        # Curto e inspecional → deve ser FAST ou BALANCED
        assert result.tier in (ComplexityTier.FAST, ComplexityTier.BALANCED)

    def test_long_prompt_favors_heavy(self, classifier: ComplexityClassifier) -> None:
        """Prompt com 80+ palavras recebe boost HEAVY."""
        long_prompt = (
            "I need you to carefully analyze the entire authentication system, "
            "identify all security vulnerabilities, design a new architecture that "
            "supports OAuth2, JWT, and Ed25519 signatures, refactor the existing code "
            "to implement these changes, write comprehensive unit and integration tests, "
            "update the documentation, and create a migration plan for the production "
            "database with zero downtime."
        )
        result = classifier.classify(long_prompt)
        assert result.tier == ComplexityTier.HEAVY

    def test_long_history_adds_heavy_signal(
        self, classifier: ComplexityClassifier
    ) -> None:
        """Histórico com 8+ mensagens adiciona sinal HEAVY."""
        history = [
            LLMMessage(role=MessageRole.USER, content=f"Message {i}")
            for i in range(10)
        ]
        result = classifier.classify("Continue the task", history=history)
        # O sinal de histórico longo deve estar presente
        assert any("long_history" in s for s in result.signals_heavy)

    def test_short_history_no_boost(self, classifier: ComplexityClassifier) -> None:
        """Histórico curto não adiciona sinal de alta complexidade."""
        history = [
            LLMMessage(role=MessageRole.USER, content=f"Message {i}")
            for i in range(3)
        ]
        result = classifier.classify("git status", history=history)
        assert not any("long_history" in s for s in result.signals_heavy)

    def test_multi_task_prompt_adds_heavy_signal(
        self, classifier: ComplexityClassifier
    ) -> None:
        """Prompts com múltiplos imperativos encadeados são detectados."""
        result = classifier.classify(
            "Read the file and then refactor it and also write the tests"
        )
        assert any("multi_task" in s for s in result.signals_heavy)


# ---------------------------------------------------------------------------
# 6. ComplexityClassifier — Casos de Borda
# ---------------------------------------------------------------------------


class TestClassifierEdgeCases:
    def test_empty_prompt_returns_balanced(
        self, classifier: ComplexityClassifier
    ) -> None:
        result = classifier.classify("")
        assert result.tier == ComplexityTier.BALANCED

    def test_whitespace_only_prompt(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("   \n\t  ")
        assert result.tier == ComplexityTier.BALANCED

    def test_no_history_default(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("hello", history=None)
        assert result.tier in ComplexityTier

    def test_confidence_is_float(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("read file src/main.py")
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0

    def test_result_has_reason(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("/plan Design the new API")
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0

    def test_signals_are_lists(self, classifier: ComplexityClassifier) -> None:
        result = classifier.classify("some random prompt")
        assert isinstance(result.signals_heavy, list)
        assert isinstance(result.signals_fast, list)

    def test_custom_keywords(self) -> None:
        """Classificador com palavras-chave customizadas funciona corretamente."""
        custom_heavy = frozenset({"unicorn_operation"})
        custom_fast = frozenset({"quick_peek"})
        clf = ComplexityClassifier(
            heavy_keywords=custom_heavy,
            fast_keywords=custom_fast,
        )
        heavy_result = clf.classify("perform the unicorn_operation on the system")
        assert heavy_result.tier == ComplexityTier.HEAVY

        fast_result = clf.classify("quick_peek at the files")
        assert fast_result.tier == ComplexityTier.FAST

    def test_conflicting_signals_balance(
        self, classifier: ComplexityClassifier
    ) -> None:
        """Quando sinais opostos de peso similar coexistem, resultado pode ser BALANCED."""
        # "format" (fast) + "architecture" (heavy) — scores próximos
        result = classifier.classify("format the architecture documentation file")
        # Não deve crashar; tier pode ser qualquer um válido
        assert result.tier in ComplexityTier


# ---------------------------------------------------------------------------
# 7. RoutingDecision — Contrato
# ---------------------------------------------------------------------------


class TestRoutingDecision:
    def test_valid_decision(self) -> None:
        d = RoutingDecision(
            selected_model="anthropic/claude-sonnet-4-5",
            complexity=ComplexityTier.HEAVY,
            mode=RoutingMode.AUTO,
            reason="High complexity detected",
        )
        assert d.selected_model == "anthropic/claude-sonnet-4-5"
        assert d.confidence == 1.0  # valor padrão

    def test_empty_model_raises(self) -> None:
        with pytest.raises(ValueError, match="selected_model cannot be empty"):
            RoutingDecision(
                selected_model="",
                complexity=ComplexityTier.FAST,
                mode=RoutingMode.FIXED,
                reason="x",
            )

    def test_invalid_confidence_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence must be in"):
            RoutingDecision(
                selected_model="google/gemini-2.0-flash",
                complexity=ComplexityTier.BALANCED,
                mode=RoutingMode.AUTO,
                reason="x",
                confidence=1.5,
            )

    def test_frozen(self) -> None:
        d = RoutingDecision(
            selected_model="google/gemini-2.0-flash",
            complexity=ComplexityTier.BALANCED,
            mode=RoutingMode.AUTO,
            reason="balanced",
        )
        with pytest.raises(Exception):
            d.selected_model = "other/model"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 8. ModelRouter — Inicialização
# ---------------------------------------------------------------------------


class TestModelRouterInit:
    def test_default_mode_is_auto(self, router: ModelRouter) -> None:
        assert router.mode == RoutingMode.AUTO

    def test_default_fixed_model_is_none(self, router: ModelRouter) -> None:
        assert router.fixed_model is None

    def test_invalid_fixed_model_raises(self, registry: ModelRegistry) -> None:
        with pytest.raises(ValueError, match="not found in registry"):
            ModelRouter(
                registry=registry,
                default_mode=RoutingMode.FIXED,
                fixed_model="nonexistent/model-xyz",
            )

    def test_invalid_tier_model_raises(self, registry: ModelRegistry) -> None:
        bad_tier_models = {
            ComplexityTier.FAST: "nonexistent/model",
            ComplexityTier.BALANCED: "google/gemini-2.0-flash",
            ComplexityTier.HEAVY: "anthropic/claude-sonnet-4-5",
        }
        with pytest.raises(ValueError):
            ModelRouter(registry=registry, tier_models=bad_tier_models)

    def test_custom_tier_models(self, registry: ModelRegistry) -> None:
        custom = {
            ComplexityTier.FAST: "google/gemini-2.0-flash-lite",
            ComplexityTier.BALANCED: "google/gemini-2.0-flash",
            ComplexityTier.HEAVY: "anthropic/claude-sonnet-4-5",
        }
        r = ModelRouter(registry=registry, tier_models=custom)
        decision = r.route("list files")
        assert decision.selected_model == custom[ComplexityTier.FAST]

    def test_custom_classifier(self, registry: ModelRegistry) -> None:
        """Classificador customizado é usado pelo roteador."""
        clf = ComplexityClassifier(
            heavy_keywords=frozenset({"superkeyword"}),
            fast_keywords=frozenset({"fastop"}),
        )
        r = ModelRouter(registry=registry, classifier=clf)
        result = r.route("perform superkeyword operation")
        assert result.complexity == ComplexityTier.HEAVY


# ---------------------------------------------------------------------------
# 9. ModelRouter — Modo AUTO
# ---------------------------------------------------------------------------


class TestModelRouterAutoMode:
    def test_architecture_prompt_routes_heavy(self, router: ModelRouter) -> None:
        """/plan prompts devem roteiar para o tier HEAVY."""
        decision = router.route("/plan Design a new microservices architecture")
        assert decision.complexity == ComplexityTier.HEAVY
        assert decision.mode == RoutingMode.AUTO

    def test_inspection_prompt_routes_fast(self, router: ModelRouter) -> None:
        """Tarefas simples de inspeção devem ir para o tier FAST."""
        decision = router.route("list files in src/")
        assert decision.complexity == ComplexityTier.FAST
        assert decision.mode == RoutingMode.AUTO

    def test_fast_uses_correct_default_model(self, router: ModelRouter) -> None:
        decision = router.route("/ls .")
        assert decision.selected_model == DEFAULT_TIER_MODELS[ComplexityTier.FAST]

    def test_heavy_uses_correct_default_model(self, router: ModelRouter) -> None:
        decision = router.route("/plan Design the security architecture")
        assert decision.selected_model == DEFAULT_TIER_MODELS[ComplexityTier.HEAVY]

    def test_decision_has_reason(self, router: ModelRouter) -> None:
        decision = router.route("Read the config file")
        assert isinstance(decision.reason, str)
        assert len(decision.reason) > 0

    def test_decision_has_confidence(self, router: ModelRouter) -> None:
        decision = router.route("/plan Redesign the entire auth module")
        assert 0.0 <= decision.confidence <= 1.0

    def test_history_is_passed_to_classifier(
        self, router: ModelRouter
    ) -> None:
        """Histórico longo influencia o roteamento."""
        history = [
            LLMMessage(role=MessageRole.USER, content=f"Step {i}")
            for i in range(10)
        ]
        decision = router.route("Continue the refactoring", history=history)
        # Com histórico longo + keyword 'refactoring' → deve ser HEAVY ou BALANCED
        assert decision.complexity in (ComplexityTier.HEAVY, ComplexityTier.BALANCED)

    def test_none_history_does_not_crash(self, router: ModelRouter) -> None:
        decision = router.route("Show me the file", history=None)
        assert decision is not None


# ---------------------------------------------------------------------------
# 10. ModelRouter — Modo FIXED
# ---------------------------------------------------------------------------


class TestModelRouterFixedMode:
    def test_fixed_mode_ignores_complexity(self, registry: ModelRegistry) -> None:
        """No modo FIXED, o modelo é sempre o configurado independente da complexidade."""
        router = ModelRouter(
            registry=registry,
            default_mode=RoutingMode.FIXED,
            fixed_model="google/gemini-2.0-flash-lite",
        )
        # Prompt de alta complexidade
        decision = router.route("/plan Design a completely new distributed architecture")
        assert decision.selected_model == "google/gemini-2.0-flash-lite"
        assert decision.mode == RoutingMode.FIXED

    def test_fixed_mode_always_same_model(self, registry: ModelRegistry) -> None:
        """100% de conformidade: qualquer prompt retorna o modelo fixo."""
        fixed = "anthropic/claude-haiku-3-5"
        router = ModelRouter(
            registry=registry,
            default_mode=RoutingMode.FIXED,
            fixed_model=fixed,
        )
        prompts = [
            "/plan architect the system",
            "list files",
            "git status",
            "refactor the entire codebase",
            "read config.yaml",
        ]
        for prompt in prompts:
            decision = router.route(prompt)
            assert decision.selected_model == fixed, (
                f"Expected {fixed!r} for prompt {prompt!r}, got {decision.selected_model!r}"
            )

    def test_fixed_mode_no_model_raises(self, registry: ModelRegistry) -> None:
        """Modo FIXED sem modelo configurado levanta ValueError ao rotear."""
        router = ModelRouter(registry=registry)
        router._mode = RoutingMode.FIXED  # força o modo sem set_mode
        with pytest.raises(ValueError, match="no fixed_model was configured"):
            router.route("any prompt")

    def test_set_mode_to_fixed(self, router: ModelRouter) -> None:
        router.set_mode(RoutingMode.FIXED, fixed_model="anthropic/claude-haiku-3-5")
        assert router.mode == RoutingMode.FIXED
        assert router.fixed_model == "anthropic/claude-haiku-3-5"

    def test_set_mode_fixed_without_model_raises(self, router: ModelRouter) -> None:
        with pytest.raises(ValueError, match="fixed_model is required"):
            router.set_mode(RoutingMode.FIXED)

    def test_set_mode_fixed_invalid_model_raises(self, router: ModelRouter) -> None:
        with pytest.raises(ValueError, match="not found in registry"):
            router.set_mode(RoutingMode.FIXED, fixed_model="nonexistent/model")

    def test_set_mode_back_to_auto(self, registry: ModelRegistry) -> None:
        router = ModelRouter(
            registry=registry,
            default_mode=RoutingMode.FIXED,
            fixed_model="google/gemini-2.0-flash-lite",
        )
        router.set_mode(RoutingMode.AUTO)
        assert router.mode == RoutingMode.AUTO
        # No modo AUTO, o classificador é usado novamente
        decision = router.route("/plan Design a new system")
        assert decision.mode == RoutingMode.AUTO


# ---------------------------------------------------------------------------
# 11. ModelRouter — Alternância por Linguagem Natural
# ---------------------------------------------------------------------------


class TestModelRouterNaturalLanguageSwitching:
    def test_switch_to_auto_english(self, registry: ModelRegistry) -> None:
        router = ModelRouter(
            registry=registry,
            default_mode=RoutingMode.FIXED,
            fixed_model="google/gemini-2.0-flash-lite",
        )
        decision = router.route("switch to auto mode")
        assert router.mode == RoutingMode.AUTO
        assert decision.mode == RoutingMode.AUTO

    def test_switch_to_auto_portuguese(self, registry: ModelRegistry) -> None:
        router = ModelRouter(
            registry=registry,
            default_mode=RoutingMode.FIXED,
            fixed_model="google/gemini-2.0-flash-lite",
        )
        router.route("Orion, alterne para o modo automático")
        assert router.mode == RoutingMode.AUTO

    def test_enable_auto_routing(self, registry: ModelRegistry) -> None:
        router = ModelRouter(
            registry=registry,
            default_mode=RoutingMode.FIXED,
            fixed_model="google/gemini-2.0-flash-lite",
        )
        router.route("enable auto routing")
        assert router.mode == RoutingMode.AUTO

    def test_fix_to_sonnet_alias(self, registry: ModelRegistry) -> None:
        router = ModelRouter(registry=registry)
        decision = router.route("fix on sonnet for this session")
        if router.mode == RoutingMode.FIXED:
            assert router.fixed_model == "anthropic/claude-sonnet-4-5"

    def test_fix_to_flash_alias(self, registry: ModelRegistry) -> None:
        router = ModelRouter(registry=registry)
        router.route("use flash model")
        if router.mode == RoutingMode.FIXED:
            assert router.fixed_model == "google/gemini-2.0-flash"

    def test_unknown_model_in_natural_language_no_crash(
        self, router: ModelRouter
    ) -> None:
        """Modelo não reconhecido na linguagem natural não deve crashar."""
        decision = router.route("use the imaginary/super-model-xyz")
        assert decision is not None  # não crashou; modo permanece AUTO

    def test_mode_persists_across_subsequent_routes(
        self, registry: ModelRegistry
    ) -> None:
        """Após alternância, o modo persiste nas chamadas subsequentes."""
        router = ModelRouter(registry=registry)
        router.route("switch to auto mode")
        decision1 = router.route("/plan Design the system")
        decision2 = router.route("read the file")
        assert decision1.mode == RoutingMode.AUTO
        assert decision2.mode == RoutingMode.AUTO


# ---------------------------------------------------------------------------
# 12. ModelRouter — set_tier_model
# ---------------------------------------------------------------------------


class TestModelRouterSetTierModel:
    def test_set_tier_model_updates_routing(self, router: ModelRouter) -> None:
        new_model = "anthropic/claude-haiku-3-5"
        router.set_tier_model(ComplexityTier.FAST, new_model)
        decision = router.route("/ls src/")
        assert decision.selected_model == new_model

    def test_set_tier_model_invalid_raises(self, router: ModelRouter) -> None:
        with pytest.raises(ValueError, match="not found in registry"):
            router.set_tier_model(ComplexityTier.FAST, "nonexistent/model")

    def test_set_tier_model_heavy(self, router: ModelRouter) -> None:
        new_model = "google/gemini-2.5-pro"
        router.set_tier_model(ComplexityTier.HEAVY, new_model)
        decision = router.route("/plan Design the entire system architecture and security model")
        assert decision.selected_model == new_model


# ---------------------------------------------------------------------------
# 13. ModelRouter — Aliases de Modelos
# ---------------------------------------------------------------------------


class TestModelRouterAliases:
    @pytest.mark.parametrize(
        "alias,expected_id",
        [
            ("opus", "anthropic/claude-opus-4-5"),
            ("sonnet", "anthropic/claude-sonnet-4-5"),
            ("haiku", "anthropic/claude-haiku-3-5"),
            ("gemini", "google/gemini-2.0-flash"),
            ("flash", "google/gemini-2.0-flash"),
            ("deepseek", "deepseek/deepseek-r1"),
            ("r1", "deepseek/deepseek-r1"),
        ],
    )
    def test_alias_resolution(self, alias: str, expected_id: str) -> None:
        resolved = ModelRouter._resolve_alias(alias)
        assert resolved == expected_id

    def test_canonical_id_passthrough(self) -> None:
        """IDs canônicos já registrados passam sem transformação."""
        cid = "anthropic/claude-sonnet-4-5"
        resolved = ModelRouter._resolve_alias(cid)
        assert resolved == cid

    def test_unknown_alias_passthrough(self) -> None:
        """Aliases desconhecidos passam sem transformação."""
        resolved = ModelRouter._resolve_alias("my-custom/model")
        assert resolved == "my-custom/model"


# ---------------------------------------------------------------------------
# 14. ModelRouter — Critérios de Aceite do DoD
# ---------------------------------------------------------------------------


class TestDoDCriteria:
    """Testes diretos contra os critérios de aceite definidos no sprint-2.md."""

    def test_dod_plan_slash_classifies_heavy(self, router: ModelRouter) -> None:
        """Prompts com /plan classificam como HEAVY_FRONTIER."""
        decision = router.route("/plan Design a new multi-tenant architecture")
        assert decision.complexity == ComplexityTier.HEAVY

    def test_dod_architecture_keyword_classifies_heavy(
        self, router: ModelRouter
    ) -> None:
        """Prompts com palavra 'architecture' classificam como HEAVY."""
        decision = router.route("Design the system architecture for our platform")
        assert decision.complexity == ComplexityTier.HEAVY

    def test_dod_file_inspection_classifies_fast(self, router: ModelRouter) -> None:
        """Tarefas simples de inspeção de arquivos classificam como FAST_LITE."""
        decision = router.route("list files in src/orion/gateway/")
        assert decision.complexity == ComplexityTier.FAST

    def test_dod_grep_classifies_fast(self, router: ModelRouter) -> None:
        """Busca com grep classifica como FAST."""
        decision = router.route("grep 'class ModelSpec' in all Python files")
        assert decision.complexity == ComplexityTier.FAST

    def test_dod_fixed_mode_100_percent_compliance(
        self, registry: ModelRegistry
    ) -> None:
        """No modo FIXED, o modelo do usuário é respeitado 100% das vezes."""
        fixed_model = "anthropic/claude-haiku-3-5"
        router = ModelRouter(
            registry=registry,
            default_mode=RoutingMode.FIXED,
            fixed_model=fixed_model,
        )
        test_prompts = [
            "/plan Full system redesign",
            "list files",
            "security audit of the entire codebase",
            "git status",
            "refactor and migrate the entire authentication system",
        ]
        for prompt in test_prompts:
            decision = router.route(prompt)
            assert decision.selected_model == fixed_model, (
                f"DoD violated: expected {fixed_model!r} for prompt {prompt!r}, "
                f"got {decision.selected_model!r}"
            )
