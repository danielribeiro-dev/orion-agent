"""
O.R.I.O.N — Circuit Breaker & Cognitive Safeguard (v0.3.0 Sprint 4)

Subsistema de Resiliência Universal para o Model Gateway.

Implementa:
  - CircuitBreaker padrão (CLOSED → OPEN → HALF_OPEN) com retentativas
    e jitter exponencial em erros transitórios (429, 502, 503, 504, timeout).
  - Salvaguarda Cognitiva (Cognitive Safeguard): ao perder o modelo de topo
    por falha externa (não por escolha do usuário), o sistema tenta um modelo
    equi-tier de fronteira alternativo. Se não houver, entra em SAFE_HOLDING —
    modo conversacional com BLOQUEIO DE MUTAÇÕES de código.
  - Modo OFFLINE_SUSPENDED: pausa graciosa em corte total de rede sem fallback,
    preservando o estado em SQLite sem congelar a máquina.
  - Local Fallback (Ollama): opcional e estritamente opt-in. Nunca habilitado
    por padrão. Nunca baixa modelos automaticamente.

DISTINÇÃO CRÍTICA DE DESIGN
────────────────────────────
  SAFE_HOLDING é um estado de *degradação emergencial*, não uma política de
  uso do modelo leve. Ele só é ativado quando TODAS as condições abaixo
  são verdadeiras simultaneamente:

    1. O modelo atualmente configurado é HEAVY (modelo de fronteira de código).
    2. Esse modelo FALHOU por razão externa (rede, API, créditos esgotados).
    3. Não há modelo equi-tier de fronteira disponível para substituir.
    4. O usuário NÃO escolheu deliberadamente um modelo leve como seu padrão.

  Se o usuário configurou um modelo FAST ou BALANCED como seu modelo de trabalho
  diário (via RoutingMode.FIXED ou ajustando o tier_models do router), o
  CircuitBreaker NUNCA entra em SAFE_HOLDING — ele opera normalmente com
  o modelo escolhido, com acesso irrestrito a todas as ferramentas.

  A flag ``intentional_lite_mode`` no CircuitBreaker captura esta distinção.

Referências: ADR-019 (Resiliência Universal & Salvaguarda Cognitiva).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from orion.gateway.models import ComplexityTier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Estados do Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitState(str, Enum):
    """Estados possíveis do Circuit Breaker.

    CLOSED        — Operação normal. Chamadas passam livremente.
    OPEN          — Falhas frequentes detectadas. Chamadas bloqueadas;
                    aguardando janela de recovery.
    HALF_OPEN     — Testando recuperação do serviço com uma chamada de prova.
    SAFE_HOLDING  — Modelo de fronteira indisponível POR FALHA EXTERNA.
                    Modelo leve ativo APENAS para diálogo com o usuário.
                    Mutações de código (write_file, edit_file, run_command
                    mutante) estão BLOQUEADAS até a volta do modelo de topo.
                    NÃO é ativado se o usuário escolheu um modelo leve
                    intencionalmente.
    OFFLINE_SUSPENDED — Sem conectividade e sem fallback local habilitado.
                    Sessão pausada graciosamente; estado persistido.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    SAFE_HOLDING = "safe_holding"
    OFFLINE_SUSPENDED = "offline_suspended"


# ---------------------------------------------------------------------------
# Motivos de Falha
# ---------------------------------------------------------------------------


class FailureReason(str, Enum):
    """Causa raiz da transição para um estado de falha."""

    RATE_LIMIT = "rate_limit"        # HTTP 429
    SERVER_ERROR = "server_error"    # HTTP 502/503/504
    TIMEOUT = "timeout"              # Timeout de rede ou API
    AUTH_ERROR = "auth_error"        # HTTP 401/403 — chave inválida ou expirada
    BUDGET_EXCEEDED = "budget_exceeded"  # Saldo de créditos esgotado
    NETWORK_OFFLINE = "network_offline"  # Sem conectividade de rede
    UNKNOWN = "unknown"              # Causa não classificada


# Mapeamento HTTP status → FailureReason
_HTTP_FAILURE_MAP: dict[int, FailureReason] = {
    429: FailureReason.RATE_LIMIT,
    401: FailureReason.AUTH_ERROR,
    403: FailureReason.AUTH_ERROR,
    502: FailureReason.SERVER_ERROR,
    503: FailureReason.SERVER_ERROR,
    504: FailureReason.SERVER_ERROR,
}


def classify_failure(
    *,
    http_status: Optional[int] = None,
    is_timeout: bool = False,
    is_offline: bool = False,
    is_budget: bool = False,
) -> FailureReason:
    """Classifica a causa de falha de uma chamada de API.

    Args:
        http_status: Código HTTP recebido (None se não aplicável).
        is_timeout: True se a falha foi por timeout de rede/API.
        is_offline: True se não há conectividade de rede.
        is_budget: True se o saldo de créditos foi esgotado.

    Returns:
        ``FailureReason`` classificado.
    """
    if is_offline:
        return FailureReason.NETWORK_OFFLINE
    if is_budget:
        return FailureReason.BUDGET_EXCEEDED
    if is_timeout:
        return FailureReason.TIMEOUT
    if http_status is not None:
        return _HTTP_FAILURE_MAP.get(http_status, FailureReason.UNKNOWN)
    return FailureReason.UNKNOWN


# ---------------------------------------------------------------------------
# Exceções do Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitOpenError(Exception):
    """Levantada quando o circuit breaker está OPEN e bloqueia a chamada.

    Attributes:
        state: Estado atual do circuit breaker.
        reason: Motivo da última falha que abriu o circuito.
        retry_after_seconds: Segundos estimados até a próxima tentativa.
    """

    def __init__(
        self,
        state: CircuitState,
        reason: FailureReason,
        retry_after_seconds: float,
    ) -> None:
        self.state = state
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Circuit breaker {state.value}: {reason.value}. "
            f"Retry in {retry_after_seconds:.1f}s."
        )


class SafeHoldingViolation(Exception):
    """Levantada pelo PEP quando uma mutação é tentada em SAFE_HOLDING.

    O SAFE_HOLDING não é uma escolha do usuário — é um estado emergencial
    causado por falha do modelo de fronteira. Mutações de código são
    proibidas até a volta do modelo de topo.

    Attributes:
        tool: Nome da ferramenta bloqueada.
        reason: Motivo da falha original que ativou o SAFE_HOLDING.
        failed_model: ID do modelo que falhou.
    """

    def __init__(
        self,
        tool: str,
        reason: FailureReason,
        failed_model: str,
    ) -> None:
        self.tool = tool
        self.reason = reason
        self.failed_model = failed_model
        super().__init__(
            f"🔒 SAFE HOLDING ATIVO — Ferramenta '{tool}' bloqueada.\n"
            f"   Causa: Modelo de fronteira '{failed_model}' indisponível "
            f"({reason.value}).\n"
            f"   Um modelo leve está ativo APENAS para diálogo. "
            f"Mutações de código estão bloqueadas até a volta do modelo de topo.\n"
            f"   Verifique o status da API / créditos e tente novamente."
        )


# ---------------------------------------------------------------------------
# Configuração do Circuit Breaker
# ---------------------------------------------------------------------------


@dataclass
class CircuitBreakerConfig:
    """Parâmetros de configuração do Circuit Breaker.

    Attributes:
        failure_threshold: Número de falhas consecutivas para abrir o circuito.
        recovery_timeout_s: Segundos em estado OPEN antes de tentar HALF_OPEN.
        success_threshold: Chamadas bem-sucedidas em HALF_OPEN para fechar.
        max_retries: Máximo de retentativas antes de considerar falha definitiva.
        base_delay_s: Delay base (em segundos) para backoff exponencial.
        max_delay_s: Delay máximo (em segundos) para backoff exponencial.
        jitter_factor: Fator de jitter aleatório (0.0–1.0) para evitar thundering herd.
        local_fallback_enabled: Habilitar Ollama como fallback local. FALSE POR PADRÃO.
                                Zero download automático. Zero auto-start.
    """

    failure_threshold: int = 3
    recovery_timeout_s: float = 30.0
    success_threshold: int = 2
    max_retries: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    jitter_factor: float = 0.25
    local_fallback_enabled: bool = False  # Opt-in explícito; nunca True por padrão


# ---------------------------------------------------------------------------
# Snapshot de Estado (para persistência e diagnóstico)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CircuitSnapshot:
    """Snapshot imutável do estado atual do Circuit Breaker.

    Attributes:
        state: Estado do circuit breaker no momento do snapshot.
        failure_count: Número de falhas consecutivas atuais.
        last_failure_reason: Motivo da última falha (None se CLOSED sem falhas).
        last_failure_at: Timestamp Unix da última falha (None se sem falhas).
        failed_model: ID do modelo que falhou e causou a transição (se houver).
        safe_holding_active: True se SAFE_HOLDING está ativo.
        intentional_lite_mode: True se o usuário escolheu um modelo leve
                               intencionalmente. Quando True, SAFE_HOLDING
                               NUNCA é ativado.
        message_for_user: Mensagem informativa para exibição ao usuário.
    """

    state: CircuitState
    failure_count: int
    last_failure_reason: Optional[FailureReason]
    last_failure_at: Optional[float]
    failed_model: Optional[str]
    safe_holding_active: bool
    intentional_lite_mode: bool
    message_for_user: str


# ---------------------------------------------------------------------------
# Ferramentas que são mutações de código (bloqueadas em SAFE_HOLDING)
# ---------------------------------------------------------------------------

#: Conjunto de ferramentas que modificam o sistema de arquivos ou executam
#: comandos arbitrários. Bloqueadas em SAFE_HOLDING para proteger a
#: integridade do código.
MUTATING_TOOLS: frozenset[str] = frozenset(
    {
        "write_file",
        "edit_file",
        "run_command",  # run_command pode ser mutante; Nuclear Gate filtra os destrutivos
    }
)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Circuit Breaker com Salvaguarda Cognitiva para o Model Gateway do ORION.

    Gerencia a resiliência de chamadas a modelos LLM, protegendo contra:
      - Falhas transitórias de API (429, 502-504, timeout)
      - Degradação silenciosa de código (downgrade de modelo sem aviso)
      - Sobrecarga de hardware (fallback local é opt-in explícito)
      - Destruição de código por modelo inadequado em modo automático

    DISTINÇÃO CRÍTICA: SAFE_HOLDING vs. Escolha Intencional de Modelo Leve
    ───────────────────────────────────────────────────────────────────────
    O SAFE_HOLDING bloqueia mutações de código SOMENTE quando um modelo
    HEAVY falhou por causa externa (não por escolha do usuário). Se o usuário
    configurou um modelo FAST/BALANCED como seu modelo diário, o sistema
    opera normalmente com acesso pleno a todas as ferramentas.

    A propriedade ``intentional_lite_mode`` controla este comportamento.
    Ela é ``True`` quando:
      - O usuário fixou explicitamente um modelo leve via RoutingMode.FIXED
      - O tier HEAVY não foi configurado (nenhum modelo HEAVY no routing)
      - O sistema foi iniciado com um modelo não-HEAVY como padrão

    Ela é ``False`` (padrão) quando:
      - O sistema está em modo AUTO com modelo HEAVY como destino
      - O modelo HEAVY falhou e o sistema está em modo de emergência

    Exemplo de uso:
        >>> cb = CircuitBreaker(primary_model_id="anthropic/claude-sonnet-4-5",
        ...                     primary_model_tier=ComplexityTier.HEAVY)
        >>> cb.record_failure(FailureReason.RATE_LIMIT)
        >>> snapshot = cb.snapshot()
        >>> snapshot.state
        CircuitState.CLOSED  # ainda não passou do threshold
        >>> cb.is_mutation_blocked()
        False
    """

    def __init__(
        self,
        primary_model_id: str,
        primary_model_tier: ComplexityTier,
        config: Optional[CircuitBreakerConfig] = None,
        equi_tier_models: Optional[list[str]] = None,
        on_state_change: Optional[Callable[[CircuitState, CircuitSnapshot], None]] = None,
        intentional_lite_mode: bool = False,
    ) -> None:
        """Inicializa o Circuit Breaker.

        Args:
            primary_model_id: ID canônico do modelo primário (ex: 'anthropic/claude-sonnet-4-5').
            primary_model_tier: Tier de complexidade do modelo primário.
            config: Parâmetros de configuração. Usa padrão se None.
            equi_tier_models: Lista de modelos de mesma potência a tentar antes
                              de entrar em SAFE_HOLDING. Ex: ['google/gemini-2.5-pro'].
            on_state_change: Callback chamado ao mudar de estado.
                             Recebe (novo_estado, snapshot).
            intentional_lite_mode: Se True, o usuário escolheu deliberadamente
                                   um modelo leve — SAFE_HOLDING NUNCA é ativado.
                                   Padrão: False.
        """
        self._primary_model_id = primary_model_id
        self._primary_model_tier = primary_model_tier
        self._config = config or CircuitBreakerConfig()
        self._equi_tier_models: list[str] = equi_tier_models or []
        self._on_state_change = on_state_change

        # DISTINÇÃO CRÍTICA: modo intencional de modelo leve
        # Quando True: usuário escolheu um modelo leve → sem SAFE_HOLDING
        # Quando False: sistema em modo normal com esperativa de modelo HEAVY
        self._intentional_lite_mode: bool = intentional_lite_mode

        # Estado interno
        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count_half_open: int = 0
        self._last_failure_reason: Optional[FailureReason] = None
        self._last_failure_at: Optional[float] = None
        self._failed_model: Optional[str] = None
        self._current_equi_tier_index: int = 0

        # Lock para segurança em contextos async concorrentes
        self._lock = asyncio.Lock()

    # ── Propriedades de estado ────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        """Estado atual do circuit breaker."""
        return self._state

    @property
    def intentional_lite_mode(self) -> bool:
        """True se o usuário escolheu deliberadamente um modelo leve.

        Quando True, SAFE_HOLDING nunca é ativado — o usuário tem acesso
        pleno a todas as ferramentas independente do tier do modelo.
        """
        return self._intentional_lite_mode

    @property
    def primary_model_id(self) -> str:
        return self._primary_model_id

    @property
    def primary_model_tier(self) -> ComplexityTier:
        return self._primary_model_tier

    # ── API Pública ───────────────────────────────────────────────────────────

    def set_intentional_lite_mode(self, value: bool) -> None:
        """Define se o usuário escolheu intencionalmente um modelo leve.

        Chame com True quando o usuário fixar explicitamente um modelo FAST
        ou BALANCED via RoutingMode.FIXED ou configuração explícita.

        Chame com False (padrão) quando o sistema está em modo AUTO com
        modelo HEAVY configurado como destino.

        Este flag é a distinção central entre:
          - SAFE_HOLDING (emergência: modelo de topo falhou externamente)
          - Operação normal com modelo leve (escolha intencional do usuário)

        Args:
            value: True = modelo leve é intencional; False = modo normal.
        """
        old = self._intentional_lite_mode
        self._intentional_lite_mode = value
        if old != value:
            logger.info(
                "CircuitBreaker: intentional_lite_mode %s → %s "
                "(modelo: %s, tier: %s)",
                old,
                value,
                self._primary_model_id,
                self._primary_model_tier.value,
            )

    def is_mutation_blocked(self) -> bool:
        """Verifica se mutações de código estão bloqueadas.

        Retorna True SOMENTE se:
          1. O estado é SAFE_HOLDING (modelo de fronteira falhou externamente), E
          2. O usuário NÃO escolheu intencionalmente um modelo leve.

        Em todos os outros casos (incluindo usuário com modelo leve intencional),
        retorna False — as ferramentas funcionam normalmente.

        Returns:
            True se mutações estão bloqueadas; False caso contrário.
        """
        return (
            self._state == CircuitState.SAFE_HOLDING
            and not self._intentional_lite_mode
        )

    def assert_mutation_allowed(self, tool: str) -> None:
        """Lança SafeHoldingViolation se mutações estão bloqueadas.

        Deve ser chamado pelo PEP antes de executar qualquer ferramenta
        que modifica o sistema de arquivos ou executa comandos.

        Args:
            tool: Nome da ferramenta a verificar.

        Raises:
            SafeHoldingViolation: Se o estado for SAFE_HOLDING e o modo
                                  lite não for intencional.
        """
        if self.is_mutation_blocked() and tool in MUTATING_TOOLS:
            raise SafeHoldingViolation(
                tool=tool,
                reason=self._last_failure_reason or FailureReason.UNKNOWN,
                failed_model=self._failed_model or self._primary_model_id,
            )

    def record_success(self) -> None:
        """Registra uma chamada bem-sucedida ao modelo.

        Em HALF_OPEN, conta sucessos para eventual fechamento do circuito.
        Em CLOSED, reseta o contador de falhas.
        """
        if self._state == CircuitState.HALF_OPEN:
            self._success_count_half_open += 1
            if self._success_count_half_open >= self._config.success_threshold:
                self._transition_to(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(
        self,
        reason: FailureReason,
        failed_model: Optional[str] = None,
    ) -> None:
        """Registra uma falha de chamada ao modelo.

        Incrementa o contador de falhas e aciona transições de estado
        conforme os thresholds configurados.

        Args:
            reason: Causa da falha.
            failed_model: ID do modelo que falhou (padrão: modelo primário).
        """
        self._failure_count += 1
        self._last_failure_reason = reason
        self._last_failure_at = time.monotonic()
        self._failed_model = failed_model or self._primary_model_id

        logger.warning(
            "CircuitBreaker: falha registrada [%d/%d] — modelo='%s', razão=%s",
            self._failure_count,
            self._config.failure_threshold,
            self._failed_model,
            reason.value,
        )

        # Offline total — transição direta para OFFLINE_SUSPENDED
        if reason == FailureReason.NETWORK_OFFLINE:
            self._transition_to(CircuitState.OFFLINE_SUSPENDED)
            return

        # Threshold de falhas atingido
        if self._failure_count >= self._config.failure_threshold:
            self._open_circuit()

    def can_attempt(self) -> bool:
        """Verifica se o circuit breaker permite uma nova tentativa.

        Returns:
            True se o estado permite chamadas; False se OPEN e não venceu
            o timeout de recovery.

        Note:
            Não modifica o estado. Chame ``check_and_maybe_half_open()``
            para transicionar para HALF_OPEN se o timeout venceu.
        """
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.HALF_OPEN:
            return True
        if self._state in (CircuitState.SAFE_HOLDING, CircuitState.OFFLINE_SUSPENDED):
            return False  # Não faz chamadas; aguarda intervenção
        # OPEN — verifica se o timeout venceu
        if self._last_failure_at is not None:
            elapsed = time.monotonic() - self._last_failure_at
            return elapsed >= self._config.recovery_timeout_s
        return False

    def check_and_maybe_half_open(self) -> bool:
        """Verifica o timeout de recovery e transiciona para HALF_OPEN se vencido.

        Returns:
            True se pode tentar uma chamada de prova; False caso contrário.
        """
        if self._state == CircuitState.OPEN and self.can_attempt():
            self._transition_to(CircuitState.HALF_OPEN)
            return True
        return self.can_attempt()

    async def execute_with_retry(
        self,
        coro_factory: Callable[[], object],
        failure_classifier: Callable[[Exception], FailureReason],
    ) -> object:
        """Executa uma coroutine com retentativas e backoff exponencial.

        Gerencia automaticamente o estado do circuit breaker com base no
        resultado de cada tentativa.

        Args:
            coro_factory: Callable sem argumentos que retorna uma coroutine
                          a executar (ex: ``lambda: provider.complete(req)``).
            failure_classifier: Callable que recebe uma Exception e retorna
                                o FailureReason correspondente.

        Returns:
            Resultado da coroutine em caso de sucesso.

        Raises:
            CircuitOpenError: Se o circuito está OPEN ou SAFE_HOLDING.
            Exception: A exceção original se todas as retentativas falharem.
        """
        if not self.check_and_maybe_half_open():
            raise CircuitOpenError(
                state=self._state,
                reason=self._last_failure_reason or FailureReason.UNKNOWN,
                retry_after_seconds=self._seconds_until_retry(),
            )

        last_exc: Optional[Exception] = None
        for attempt in range(self._config.max_retries + 1):
            try:
                result = await coro_factory()  # type: ignore[misc]
                self.record_success()
                return result
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                reason = failure_classifier(exc)
                self.record_failure(reason)

                if attempt < self._config.max_retries:
                    delay = self._backoff_delay(attempt)
                    logger.info(
                        "CircuitBreaker: tentativa %d/%d falhou (%s). "
                        "Aguardando %.2fs antes de retentativa.",
                        attempt + 1,
                        self._config.max_retries,
                        reason.value,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "CircuitBreaker: todas as %d tentativas falharam. "
                        "Última razão: %s.",
                        self._config.max_retries + 1,
                        reason.value,
                    )

        raise last_exc  # type: ignore[misc]

    def get_next_equi_tier_model(self) -> Optional[str]:
        """Retorna o próximo modelo equi-tier disponível para substituição.

        Modelos equi-tier são de mesma potência (HEAVY) configurados como
        alternativas. São usados ANTES de entrar em SAFE_HOLDING.

        Returns:
            ID do próximo modelo equi-tier ou None se não houver mais.
        """
        if self._current_equi_tier_index < len(self._equi_tier_models):
            model = self._equi_tier_models[self._current_equi_tier_index]
            self._current_equi_tier_index += 1
            return model
        return None

    def reset(self) -> None:
        """Reseta o circuit breaker para o estado CLOSED.

        Útil quando o usuário confirma que a API voltou ou mudou o modelo.
        """
        logger.info(
            "CircuitBreaker: reset manual para CLOSED (era: %s).",
            self._state.value,
        )
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count_half_open = 0
        self._last_failure_reason = None
        self._last_failure_at = None
        self._failed_model = None
        self._current_equi_tier_index = 0

    def snapshot(self) -> CircuitSnapshot:
        """Retorna um snapshot imutável do estado atual.

        Returns:
            ``CircuitSnapshot`` com todos os dados de estado relevantes.
        """
        return CircuitSnapshot(
            state=self._state,
            failure_count=self._failure_count,
            last_failure_reason=self._last_failure_reason,
            last_failure_at=self._last_failure_at,
            failed_model=self._failed_model,
            safe_holding_active=(self._state == CircuitState.SAFE_HOLDING),
            intentional_lite_mode=self._intentional_lite_mode,
            message_for_user=self._build_user_message(),
        )

    # ── Lógica interna de transição ───────────────────────────────────────────

    def _open_circuit(self) -> None:
        """Abre o circuito após threshold de falhas.

        Política de escalonamento:
        1. Tenta modelo equi-tier de fronteira (mesma potência, outro provedor).
        2. Se não houver e o modelo falho for HEAVY (e não estiver em modo
           lite intencional), ativa SAFE_HOLDING.
        3. Se fallback local estiver habilitado (opt-in), usa Ollama.
        4. Caso contrário, abre o circuito padrão (OPEN).
        """
        # Tentar equi-tier antes de qualquer outra ação
        next_equi = self.get_next_equi_tier_model()
        if next_equi:
            logger.warning(
                "CircuitBreaker: modelo '%s' falhou. Chaveando para equi-tier: '%s'.",
                self._failed_model or self._primary_model_id,
                next_equi,
            )
            # O chamador deve usar next_equi para a próxima chamada.
            # O circuito fica OPEN enquanto testa o equi-tier.
            self._transition_to(CircuitState.OPEN)
            return

        # Sem equi-tier: verificar se deve entrar em SAFE_HOLDING
        if (
            self._primary_model_tier == ComplexityTier.HEAVY
            and not self._intentional_lite_mode
        ):
            # SAFE_HOLDING: modelo de fronteira falhou, usuário NÃO escolheu
            # um modelo leve intencionalmente. Bloquear mutações.
            logger.error(
                "CircuitBreaker: modelo de fronteira '%s' (HEAVY) falhou "
                "sem equi-tier disponível. Ativando SAFE_HOLDING. "
                "Mutações de código bloqueadas até restabelecimento.",
                self._failed_model or self._primary_model_id,
            )
            self._transition_to(CircuitState.SAFE_HOLDING)
            return

        # Fallback local (Ollama) — somente se opt-in explícito
        if self._config.local_fallback_enabled:
            logger.warning(
                "CircuitBreaker: ativando fallback local Ollama (opt-in)."
            )
            # Permanece em OPEN para que o LocalOllamaProvider seja usado
            self._transition_to(CircuitState.OPEN)
            return

        # Circuito aberto padrão
        self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        """Executa a transição para um novo estado, disparando o callback."""
        old_state = self._state
        self._state = new_state

        if new_state == CircuitState.HALF_OPEN:
            self._success_count_half_open = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count_half_open = 0
            self._last_failure_reason = None
            self._failed_model = None
            self._current_equi_tier_index = 0

        logger.info(
            "CircuitBreaker: %s → %s (modelo: %s)",
            old_state.value,
            new_state.value,
            self._primary_model_id,
        )

        if self._on_state_change and old_state != new_state:
            try:
                self._on_state_change(new_state, self.snapshot())
            except Exception:  # noqa: BLE001
                logger.exception("CircuitBreaker: erro no callback on_state_change.")

    def _backoff_delay(self, attempt: int) -> float:
        """Calcula o delay com backoff exponencial e jitter aleatório.

        Args:
            attempt: Índice da tentativa atual (começa em 0).

        Returns:
            Delay em segundos.
        """
        base = self._config.base_delay_s * (2**attempt)
        capped = min(base, self._config.max_delay_s)
        jitter = random.uniform(0, self._config.jitter_factor * capped)  # noqa: S311
        return capped + jitter

    def _seconds_until_retry(self) -> float:
        """Calcula quantos segundos faltam para a próxima tentativa."""
        if self._last_failure_at is None:
            return self._config.recovery_timeout_s
        elapsed = time.monotonic() - self._last_failure_at
        return max(0.0, self._config.recovery_timeout_s - elapsed)

    def _build_user_message(self) -> str:
        """Constrói mensagem informativa para o usuário com base no estado atual."""
        if self._state == CircuitState.CLOSED:
            return "✅ Gateway operacional."

        if self._state == CircuitState.OPEN:
            reason = self._last_failure_reason
            retry_in = self._seconds_until_retry()
            return (
                f"⚠️  Gateway temporariamente indisponível "
                f"({reason.value if reason else 'erro desconhecido'}). "
                f"Tentando recuperação em {retry_in:.0f}s."
            )

        if self._state == CircuitState.HALF_OPEN:
            return "🔄 Testando recuperação do gateway..."

        if self._state == CircuitState.SAFE_HOLDING:
            reason = self._last_failure_reason
            model = self._failed_model or self._primary_model_id
            return (
                f"🔒 SAFE HOLDING: Modelo de fronteira '{model}' indisponível "
                f"({reason.value if reason else 'razão desconhecida'}). "
                f"Modo conversacional ativo — posso dialogar mas NÃO posso "
                f"modificar código ou executar comandos. "
                f"Verifique o status da API e créditos."
            )

        if self._state == CircuitState.OFFLINE_SUSPENDED:
            return (
                "📴 SESSÃO SUSPENSA: Sem conectividade de rede. "
                "Estado preservado. Sessão será retomada automaticamente "
                "quando a conexão for restaurada."
            )

        return f"Estado desconhecido: {self._state.value}"
