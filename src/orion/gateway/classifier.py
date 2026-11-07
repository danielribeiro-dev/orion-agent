"""
O.R.I.O.N — Complexity Classifier (v0.3.0 Sprint 2)

Avaliador heurístico de complexidade cognitiva do turno para o
Dynamic Auto-Routing. Analisa léxica e contextualmente o prompt do
usuário e o histórico de mensagens para determinar o tier de
complexidade adequado: FAST, BALANCED ou HEAVY.

Inspirado na arquitetura do RouteLLM com heurísticas de domínio
específico para fluxos de engenharia de software.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from orion.gateway.models import ComplexityTier, LLMMessage

# ---------------------------------------------------------------------------
# Sinais de Complexidade
# ---------------------------------------------------------------------------

# Indicadores de alta complexidade (tier HEAVY)
_HEAVY_SLASH_COMMANDS: frozenset[str] = frozenset(
    {
        "/plan",
        "/architect",
        "/design",
        "/review",
        "/refactor",
        "/audit",
        "/analyze",
        "/diagnose",
        "/optimize",
        "/security",
    }
)

_HEAVY_KEYWORDS: frozenset[str] = frozenset(
    {
        # Arquitetura & design
        "architecture",
        "arquitetura",
        "design pattern",
        "padrão de design",
        "microservices",
        "microsserviços",
        "distributed system",
        "sistema distribuído",
        "trade-off",
        "tradeoff",
        # Refatoração complexa
        "refactor",
        "refatorar",
        "refactoring",
        "refatoração",
        "rewrite",
        "reescrever",
        "migrate",
        "migrar",
        "migration",
        "migração",
        # Segurança
        "security",
        "segurança",
        "vulnerability",
        "vulnerabilidade",
        "cve",
        "exploit",
        "cryptography",
        "criptografia",
        "authentication",
        "autenticação",
        "authorization",
        "autorização",
        "sql injection",
        "xss",
        "csrf",
        # Debugging profundo
        "race condition",
        "condição de corrida",
        "deadlock",
        "memory leak",
        "vazamento de memória",
        "segfault",
        "undefined behavior",
        "comportamento indefinido",
        "performance bottleneck",
        "gargalo",
        # Raciocínio e planejamento
        "step by step",
        "passo a passo",
        "explain in detail",
        "explique em detalhes",
        "how does",
        "como funciona",
        "why does",
        "por que",
        "trade off",
        "pros and cons",
        "prós e contras",
        "compare",
        "comparar",
        "best approach",
        "melhor abordagem",
        # Tarefas multi-arquivo
        "across all files",
        "em todos os arquivos",
        "entire codebase",
        "código todo",
        "multiple modules",
        "múltiplos módulos",
        "end-to-end",
        "ponta a ponta",
        # Algoritmos complexos
        "algorithm",
        "algoritmo",
        "complexity analysis",
        "análise de complexidade",
        "big o",
        "dynamic programming",
        "programação dinâmica",
        "graph",
        "grafo",
    }
)

# Keywords de alta relevância que por si só são suficientes para HEAVY.
# Peso individual = _HEAVY_SCORE_THRESHOLD (garante classificação imediata).
_HEAVY_CRITICAL_KEYWORDS: frozenset[str] = frozenset(
    {
        # Debugging de sistemas (sempre exigem raciocínio profundo)
        "race condition",
        "condição de corrida",
        "deadlock",
        "memory leak",
        "vazamento de memória",
        "segfault",
        "undefined behavior",
        "comportamento indefinido",
        # Segurança de alto impacto
        "segurança",
        "security",
        "vulnerability",
        "vulnerabilidade",
        "sql injection",
        "exploit",
        # Arquitetura
        "architecture",
        "arquitetura",
        "microservices",
        "microsserviços",
        "distributed system",
        "sistema distribuído",
        # Refatoração estrutural
        "refactor",
        "refatorar",
        "refactoring",
        "refatoração",
    }
)

# Indicadores de baixa complexidade (tier FAST)
_FAST_SLASH_COMMANDS: frozenset[str] = frozenset(
    {
        "/ls",
        "/list",
        "/status",
        "/check",
        "/show",
        "/read",
        "/cat",
        "/grep",
        "/find",
        "/diff",
    }
)

_FAST_KEYWORDS: frozenset[str] = frozenset(
    {
        # Leitura e inspeção
        "list files",
        "listar arquivos",
        "show files",
        "mostrar arquivos",
        "read file",
        "ler arquivo",
        "what is in",
        "o que tem em",
        "what does",
        "o que faz",
        "show me",
        "me mostre",
        "print",
        "display",
        "exibir",
        # Formatação simples
        "format",
        "formatar",
        "indent",
        "indentar",
        "sort",
        "ordenar",
        "rename variable",
        "renomear variável",
        "fix typo",
        "corrigir typo",
        "fix spelling",
        # Status & checagem
        "check status",
        "verificar status",
        "is it running",
        "está rodando",
        "version",
        "versão",
        "what version",
        "qual versão",
        "ping",
        # Sumarização curta
        "summarize briefly",
        "resuma brevemente",
        "tldr",
        "quick summary",
        "resumo rápido",
        "one line",
        "em uma linha",
        # Busca e grep
        "grep",
        "search for",
        "buscar",
        "find all",
        "encontrar",
        "where is",
        "onde está",
        "locate",
        "localizar",
        # Git simples
        "git status",
        "git log",
        "git diff",
        "git show",
    }
)


# ---------------------------------------------------------------------------
# Resultado da Classificação
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassificationResult:
    """Resultado da análise de complexidade de um turno.

    Attributes:
        tier: Tier de complexidade determinado pelo classificador.
        confidence: Confiança da classificação (0.0 a 1.0).
        reason: Justificativa legível por humanos da decisão.
        signals_heavy: Sinais de alta complexidade detectados.
        signals_fast: Sinais de baixa complexidade detectados.
    """

    tier: ComplexityTier
    confidence: float
    reason: str
    signals_heavy: list[str] = field(default_factory=list)
    signals_fast: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")


# ---------------------------------------------------------------------------
# Classificador Principal
# ---------------------------------------------------------------------------


class ComplexityClassifier:
    """Avaliador heurístico de complexidade cognitiva de turnos de inferência.

    Analisa o texto do prompt (e opcionalmente o histórico de mensagens)
    para determinar o tier de complexidade mais adequado usando:

    1. Detecção de slash commands (alta/baixa complexidade).
    2. Varredura léxica por palavras-chave de domínio.
    3. Heurísticas estruturais (tamanho do prompt, número de mensagens).
    4. Análise de tarefas múltiplas (múltiplos imperatives no mesmo prompt).

    A decisão final respeita a hierarquia:
        HEAVY > BALANCED > FAST
    """

    # Limites heurísticos de tamanho de prompt
    _FAST_MAX_WORDS: int = 15        # Prompts curtíssimos → FAST
    _HEAVY_MIN_WORDS: int = 80       # Prompts longos e detalhados → inclinação a HEAVY
    _HEAVY_MIN_HISTORY: int = 8      # Históricos longos indicam tarefa complexa em andamento

    # Thresholds de score para decisão final
    _HEAVY_SCORE_THRESHOLD: float = 2.0
    _FAST_SCORE_THRESHOLD: float = 1.5

    def __init__(
        self,
        heavy_keywords: frozenset[str] | None = None,
        fast_keywords: frozenset[str] | None = None,
        heavy_slash_commands: frozenset[str] | None = None,
        fast_slash_commands: frozenset[str] | None = None,
        heavy_critical_keywords: frozenset[str] | None = None,
    ) -> None:
        """Inicializa o classificador.

        Args:
            heavy_keywords: Palavras-chave customizadas para HEAVY (substitui padrão).
            fast_keywords: Palavras-chave customizadas para FAST (substitui padrão).
            heavy_slash_commands: Slash commands para HEAVY (substitui padrão).
            fast_slash_commands: Slash commands para FAST (substitui padrão).
            heavy_critical_keywords: Keywords críticas que sozinhas disparam HEAVY
                (substitui padrão). Quando None, usa ``_HEAVY_CRITICAL_KEYWORDS``.
        """
        self._heavy_keywords = heavy_keywords or _HEAVY_KEYWORDS
        self._fast_keywords = fast_keywords or _FAST_KEYWORDS
        self._heavy_slash_commands = heavy_slash_commands or _HEAVY_SLASH_COMMANDS
        self._fast_slash_commands = fast_slash_commands or _FAST_SLASH_COMMANDS
        # Críticas: se heavy_keywords customizado for fornecido, tratar TODO ele como crítico
        self._heavy_critical_keywords: frozenset[str] = (
            heavy_critical_keywords
            if heavy_critical_keywords is not None
            else (_HEAVY_CRITICAL_KEYWORDS if heavy_keywords is None else heavy_keywords)
        )

    # ── API pública ──────────────────────────────────────────────────────────

    def classify(
        self,
        prompt: str,
        history: list[LLMMessage] | None = None,
    ) -> ClassificationResult:
        """Classifica a complexidade cognitiva do turno.

        Args:
            prompt: Texto do turno atual do usuário.
            history: Histórico de mensagens anteriores (opcional).

        Returns:
            ``ClassificationResult`` com tier, confiança e justificativa.
        """
        prompt_lower = prompt.lower().strip()
        history = history or []

        heavy_score: float = 0.0
        fast_score: float = 0.0
        signals_heavy: list[str] = []
        signals_fast: list[str] = []

        # ── 1. Slash commands ────────────────────────────────────────────────
        detected_slash = self._extract_slash_command(prompt_lower)
        if detected_slash:
            if detected_slash in self._heavy_slash_commands:
                heavy_score += 3.0  # peso máximo — intenção explícita
                signals_heavy.append(f"slash_command:{detected_slash}")
            elif detected_slash in self._fast_slash_commands:
                fast_score += 3.0
                signals_fast.append(f"slash_command:{detected_slash}")

        # ── 2. Palavras-chave de alta complexidade ───────────────────────────
        # Keywords críticas recebem peso 2.0 (suficiente para atingir o threshold sozinhas).
        # Keywords padrão recebem peso 1.0.
        for kw in self._heavy_keywords:
            if kw in prompt_lower:
                weight = 2.0 if kw in self._heavy_critical_keywords else 1.0
                heavy_score += weight
                signals_heavy.append(f"keyword:{kw}")
                if heavy_score >= 4.0:
                    break  # pontuação já alta suficiente — early exit

        # ── 3. Palavras-chave de baixa complexidade ──────────────────────────
        for kw in self._fast_keywords:
            if kw in prompt_lower:
                fast_score += 1.0
                signals_fast.append(f"keyword:{kw}")
                if fast_score >= 4.0:
                    break

        # ── 4. Heurísticas estruturais ───────────────────────────────────────
        word_count = len(prompt.split())

        if word_count <= self._FAST_MAX_WORDS:
            fast_score += 0.5
            signals_fast.append(f"short_prompt:{word_count}_words")
        elif word_count >= self._HEAVY_MIN_WORDS:
            heavy_score += 0.8
            signals_heavy.append(f"long_prompt:{word_count}_words")

        if len(history) >= self._HEAVY_MIN_HISTORY:
            heavy_score += 0.6
            signals_heavy.append(f"long_history:{len(history)}_messages")

        # ── 5. Múltiplos imperativos / subtarefas ────────────────────────────
        imperative_count = self._count_imperatives(prompt_lower)
        if imperative_count >= 3:
            heavy_score += min(1.5, imperative_count * 0.4)
            signals_heavy.append(f"multi_task:{imperative_count}_imperatives")

        # ── 6. Decisão final ─────────────────────────────────────────────────
        return self._decide(heavy_score, fast_score, signals_heavy, signals_fast)

    # ── Helpers internos ─────────────────────────────────────────────────────

    @staticmethod
    def _extract_slash_command(text: str) -> str | None:
        """Extrai o slash command do início do texto, se presente."""
        match = re.match(r"^(/[a-z_\-]+)", text.strip())
        return match.group(1) if match else None

    @staticmethod
    def _count_imperatives(text: str) -> int:
        """Conta cláusulas imperativas conectadas por 'e', 'then', 'depois', ';' ou 'também'."""
        connectors = re.findall(
            r"\b(and then|e depois|e também|and also|then|depois|também|;\s*\w)\b",
            text,
        )
        return len(connectors) + 1 if connectors else 1

    def _decide(
        self,
        heavy_score: float,
        fast_score: float,
        signals_heavy: list[str],
        signals_fast: list[str],
    ) -> ClassificationResult:
        """Converte os scores numéricos em um ``ClassificationResult``."""
        total = heavy_score + fast_score

        if total == 0.0:
            return ClassificationResult(
                tier=ComplexityTier.BALANCED,
                confidence=0.5,
                reason="Sem sinais suficientes; usando tier padrão BALANCED.",
                signals_heavy=signals_heavy,
                signals_fast=signals_fast,
            )

        if heavy_score >= self._HEAVY_SCORE_THRESHOLD and heavy_score > fast_score:
            confidence = min(1.0, heavy_score / (total + 1e-9))
            reason = (
                f"Sinais de alta complexidade detectados (score={heavy_score:.1f}): "
                + ", ".join(signals_heavy[:3])
            )
            return ClassificationResult(
                tier=ComplexityTier.HEAVY,
                confidence=round(confidence, 3),
                reason=reason,
                signals_heavy=signals_heavy,
                signals_fast=signals_fast,
            )

        if fast_score >= self._FAST_SCORE_THRESHOLD and fast_score > heavy_score:
            confidence = min(1.0, fast_score / (total + 1e-9))
            reason = (
                f"Sinais de baixa complexidade detectados (score={fast_score:.1f}): "
                + ", ".join(signals_fast[:3])
            )
            return ClassificationResult(
                tier=ComplexityTier.FAST,
                confidence=round(confidence, 3),
                reason=reason,
                signals_heavy=signals_heavy,
                signals_fast=signals_fast,
            )

        # Scores próximos ou sem dominância clara → BALANCED
        confidence = 0.5 + abs(heavy_score - fast_score) / (2.0 * (total + 1e-9))
        reason = (
            f"Complexidade moderada (heavy={heavy_score:.1f}, fast={fast_score:.1f}). "
            "Usando BALANCED como tier intermediário."
        )
        return ClassificationResult(
            tier=ComplexityTier.BALANCED,
            confidence=round(min(confidence, 0.8), 3),
            reason=reason,
            signals_heavy=signals_heavy,
            signals_fast=signals_fast,
        )
