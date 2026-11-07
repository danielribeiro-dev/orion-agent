"""
O.R.I.O.N — Auto-compactação e poda de contexto (v0.5.0 Sprint 3, CA-03)

Mantém sessões longas dentro da janela sem perder a tarefa ativa. Roda ANTES de cada
chamada ao modelo (gancho ``prepare_messages`` do engine), em dois degraus:

  1. ``prune_tool_results`` (>= 60% da janela): resultados antigos de tools perdem o corpo
     e mantêm só o início; o pareamento ``tool_use``/``tool_result`` permanece intacto.
  2. ``compact_messages`` (>= 80%): o histórico antigo vira um resumo (LLM barato, com
     fallback determinístico); a cauda recente e o pedido ativo do usuário seguem LITERAIS.

Podar/compactar altera o prefixo e invalida o cache de prompt dali em diante, por isso
só acontece sob pressão de contexto. Invariante (critério de parada 2): o último pedido
do usuário nunca é descartado; se a verificação falhar, nada é alterado.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from orion.gateway.models import ContentBlock, LLMMessage, MessageRole
from orion.timeline.compactor import ContextCompactor, estimate_tokens

logger = logging.getLogger(__name__)

Summarizer = Callable[[str, str | None], Awaitable[str]]
"""``await summarizer(transcript, focus) -> resumo`` (modelo barato; pode falhar)."""

PRUNE_THRESHOLD = 0.60
COMPACT_THRESHOLD = 0.80
KEEP_RECENT_RESULTS = 6
PRUNED_KEEP_CHARS = 240
KEEP_TURNS = 2
INTRA_TURN_TAIL = 6
MAX_TRANSCRIPT_CHARS = 60_000
PRUNED_MARK = "[... resultado antigo podado para economizar contexto ...]"

SUMMARY_HEADER = "Resumo da conversa anterior (compactada automaticamente):"

SUMMARY_PROMPT = (
    "Resuma a conversa abaixo para que o trabalho continue sem perda de contexto. Preserve, de forma "
    "densa e factual: (1) o que o usuário pediu, literal quando curto; (2) decisões tomadas e seus "
    "motivos; (3) caminhos de arquivos lidos ou modificados; (4) estado atual e erros pendentes; "
    "(5) próximos passos. Não invente nada. Responda no idioma da conversa, em no máximo 600 palavras."
)

_PATH_KEYS = ("path", "file_path", "target_path", "file")
_MUTATING = {"write_file", "edit_file"}


# ---------------------------------------------------------------------------
# Medição
# ---------------------------------------------------------------------------


def message_tokens(message: LLMMessage) -> int:
    """Estimativa de tokens de uma mensagem (inclui o thinking, que volta à API)."""
    extra = sum(len(b.thinking or "") + len(b.data or "") for b in message.blocks)
    return estimate_tokens(message.text) + extra // 4


def estimate_messages(messages: list[LLMMessage]) -> int:
    return sum(message_tokens(m) for m in messages)


def is_turn_start(message: LLMMessage) -> bool:
    """Mensagem de usuário com pedido (texto), e não apenas ``tool_result``."""
    if message.role != MessageRole.USER:
        return False
    return isinstance(message.content, str) or any(b.type != "tool_result" for b in message.blocks)


def turn_starts(messages: list[LLMMessage]) -> list[int]:
    return [i for i, m in enumerate(messages) if is_turn_start(m)]


# ---------------------------------------------------------------------------
# Degrau 1 — poda de tool_result
# ---------------------------------------------------------------------------


def _result_text(block: ContentBlock) -> str:
    inner = block.content
    if isinstance(inner, str):
        return inner
    return "".join(b.text or "" for b in (inner or []))


def prune_tool_results(
    messages: list[LLMMessage],
    keep_recent: int = KEEP_RECENT_RESULTS,
    keep_chars: int = PRUNED_KEEP_CHARS,
) -> tuple[list[LLMMessage], int]:
    """Troca o corpo de ``tool_result`` antigos por um trecho curto. Devolve (mensagens, podados)."""
    positions = [
        (i, j)
        for i, m in enumerate(messages)
        for j, b in enumerate(m.blocks)
        if m.role == MessageRole.USER and b.type == "tool_result"
    ]
    stale = set(positions[:-keep_recent] if keep_recent else positions)
    if not stale:
        return messages, 0

    pruned = 0
    out: list[LLMMessage] = []
    for i, message in enumerate(messages):
        blocks = message.blocks
        if not any((i, j) in stale for j in range(len(blocks))):
            out.append(message)
            continue
        rebuilt: list[ContentBlock] = []
        for j, block in enumerate(blocks):
            text = _result_text(block) if (i, j) in stale else ""
            if (i, j) in stale and len(text) > keep_chars * 2 and PRUNED_MARK not in text:
                block = block.model_copy(update={"content": f"{text[:keep_chars]}\n{PRUNED_MARK}"})
                pruned += 1
            rebuilt.append(block)
        out.append(message.model_copy(update={"content": rebuilt}))
    return out, pruned


# ---------------------------------------------------------------------------
# Degrau 2 — compactação
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompactionOutcome:
    """Resultado de uma compactação de mensagens."""

    messages: list[LLMMessage]
    condensed_messages: int
    tokens_before: int
    tokens_after: int
    used_llm: bool
    active_files: list[str] = field(default_factory=list)

    @property
    def tokens_saved(self) -> int:
        return max(0, self.tokens_before - self.tokens_after)


def _user_text(message: LLMMessage) -> str:
    return "".join(b.text or "" for b in message.blocks if b.type == "text")


def _tool_paths(messages: list[LLMMessage]) -> tuple[list[str], list[str]]:
    """(arquivos tocados por tools, arquivos modificados) na ordem de primeira aparição."""
    touched: dict[str, None] = {}
    modified: dict[str, None] = {}
    for m in messages:
        for b in m.blocks:
            if b.type != "tool_use":
                continue
            for key in _PATH_KEYS:
                value = (b.input or {}).get(key)
                if isinstance(value, str) and value.strip():
                    touched[value.strip()] = None
                    if b.name in _MUTATING:
                        modified[value.strip()] = None
    return list(touched), list(modified)


def render_transcript(messages: list[LLMMessage], limit: int = MAX_TRANSCRIPT_CHARS) -> str:
    """Texto plano da conversa para o resumidor (resultados de tools cortados)."""
    lines: list[str] = []
    for m in messages:
        for b in m.blocks:
            if b.type == "text":
                lines.append(f"[{m.role.value}] {b.text}")
            elif b.type == "tool_use":
                lines.append(f"[tool_use] {b.name} {json.dumps(b.input or {}, ensure_ascii=False)[:400]}")
            elif b.type == "tool_result":
                flag = " erro" if b.is_error else ""
                lines.append(f"[tool_result{flag}] {_result_text(b)[:500]}")
    text = "\n".join(lines)
    return text[-limit:]


def deterministic_summary(messages: list[LLMMessage]) -> str:
    """Resumo sem LLM: pedidos literais, ações executadas, arquivos e últimas respostas."""
    requests = [_user_text(m).strip() for m in messages if is_turn_start(m)]
    actions: dict[str, int] = {}
    answers: list[str] = []
    for m in messages:
        for b in m.blocks:
            if b.type == "tool_use":
                actions[b.name or "?"] = actions.get(b.name or "?", 0) + 1
        if m.role == MessageRole.ASSISTANT:
            text = _user_text(m).strip()
            if text:
                answers.append(text)
    lines = ["Pedidos do usuário (em ordem):"]
    lines += [f"  - {r[:300]}" for r in requests if r] or ["  - (nenhum)"]
    if actions:
        lines.append("Ações executadas: " + ", ".join(f"{n}x {name}" for name, n in sorted(actions.items())))
    if answers:
        lines.append("Últimas respostas do assistente:")
        lines += [f"  - {a[:300]}" for a in answers[-3:]]
    return "\n".join(lines) + "\n" + _files_line(messages)


def _files_line(messages: list[LLMMessage]) -> str:
    touched, modified = _tool_paths(messages)
    active = list(dict.fromkeys([*modified, *touched]))[:40]
    parts = []
    if modified:
        parts.append("Arquivos modificados: " + ", ".join(modified[:40]))
    if active:
        parts.append("Arquivos relevantes: " + ", ".join(active))
    return "\n".join(parts)


def _choose_cut(
    messages: list[LLMMessage], keep_turns: int, allow_intra: bool = True
) -> tuple[int, bool] | None:
    """Índice onde começa a cauda preservada e se o corte é dentro do turno atual."""
    starts = turn_starts(messages)
    if not starts:
        return None
    if len(starts) > keep_turns:
        return starts[-keep_turns], False
    if not allow_intra:
        return None
    # Poucos turnos: corta dentro do turno atual, numa mensagem de assistente (pareamento intacto).
    current = starts[-1]
    for cut in range(len(messages) - INTRA_TURN_TAIL, current, -1):
        if messages[cut].role == MessageRole.ASSISTANT:
            return cut, True
    return None


async def compact_messages(
    messages: list[LLMMessage],
    *,
    compactor: ContextCompactor,
    summarizer: Summarizer | None = None,
    focus: str | None = None,
    keep_turns: int = KEEP_TURNS,
    allow_intra: bool = True,
) -> CompactionOutcome | None:
    """Substitui o histórico antigo por um resumo. ``None`` se não há o que compactar com segurança.

    ``allow_intra=False`` (``/compact`` manual) só corta entre turnos completos.
    """
    cut = _choose_cut(messages, keep_turns, allow_intra)
    if cut is None:
        return None
    index, intra = cut
    head, tail = messages[:index], messages[index:]
    if not head:
        return None

    summary = ""
    used_llm = False
    if summarizer is not None:
        try:
            summary = (await summarizer(render_transcript(head), focus)).strip()
            used_llm = bool(summary)
        except Exception as exc:  # noqa: BLE001 - qualquer falha cai no resumo determinístico
            logger.warning("Auto-compactação: resumidor falhou (%s); usando resumo determinístico.", exc)
    if not summary:
        summary = deterministic_summary(head)
    elif used_llm:
        summary += "\n" + _files_line(head)
    if focus:
        summary = f"Foco: {focus}\n{summary}"

    starts = turn_starts(messages)
    if intra:
        current = messages[starts[-1]]
        instruction = _user_text(current) or current.text
        first = LLMMessage(
            role=MessageRole.USER,
            content=(
                f"{SUMMARY_HEADER}\n{summary}\n\n"
                f"Pedido atual (literal, ainda em andamento):\n{instruction}"
            ),
        )
        new = [first, *tail]
    else:
        new = [
            LLMMessage(role=MessageRole.USER, content=f"{SUMMARY_HEADER}\n{summary}"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Entendido."),
            *tail,
        ]

    if not _keeps_active_request(messages, new):
        logger.error("Auto-compactação abortada: o pedido ativo do usuário não foi preservado.")
        return None
    touched, _ = _tool_paths(head)
    return CompactionOutcome(
        messages=new,
        condensed_messages=len(head),
        tokens_before=estimate_messages(messages),
        tokens_after=estimate_messages(new),
        used_llm=used_llm,
        active_files=touched,
    )


def _keeps_active_request(before: list[LLMMessage], after: list[LLMMessage]) -> bool:
    """O texto do último pedido do usuário deve sobreviver literalmente."""
    starts = turn_starts(before)
    if not starts:
        return True
    wanted = _user_text(before[starts[-1]]) or before[starts[-1]].text
    return any(wanted and wanted in (_user_text(m) or m.text) for m in after)


# ---------------------------------------------------------------------------
# Gancho do engine
# ---------------------------------------------------------------------------


class AutoCompactor:
    """Gancho ``prepare_messages``: poda a 60% e compacta a 80% da janela.

    ``overhead`` informa os tokens fixos (system + tools); ``observe`` calibra a estimativa
    de 4 caracteres/token contra o ``prompt_tokens`` real devolvido pelo provedor.
    """

    def __init__(
        self,
        *,
        compactor: ContextCompactor,
        window: Callable[[], int],
        overhead: Callable[[], int],
        summarizer: Summarizer | None = None,
        on_compact: Callable[[CompactionOutcome], None] | None = None,
        on_replace: Callable[[list[LLMMessage]], None] | None = None,
        prune_at: float = PRUNE_THRESHOLD,
        compact_at: float = COMPACT_THRESHOLD,
        keep_turns: int = KEEP_TURNS,
    ) -> None:
        self._compactor = compactor
        self._window = window
        self._overhead = overhead
        self._summarizer = summarizer
        self._on_compact = on_compact
        self._on_replace = on_replace
        self._prune_at = prune_at
        self._compact_at = compact_at
        self._keep_turns = keep_turns
        self.ratio = 1.0
        self.last_estimate = 0

    def estimate(self, messages: list[LLMMessage]) -> int:
        """Tokens estimados da próxima requisição, calibrados pela razão observada."""
        self.last_estimate = int((self._overhead() + estimate_messages(messages)) * self.ratio)
        return self.last_estimate

    def observe(self, prompt_tokens: int) -> None:
        """Calibra com o uso real da última chamada (limita a razão a [0.5, 3])."""
        if prompt_tokens > 0 and self.last_estimate > 0:
            raw = self.last_estimate / self.ratio
            self.ratio = min(3.0, max(0.5, prompt_tokens / raw))

    def usage_ratio(self, messages: list[LLMMessage]) -> float:
        window = self._window()
        return self.estimate(messages) / window if window > 0 else 0.0

    async def __call__(self, messages: list[LLMMessage]) -> list[LLMMessage] | None:
        if self.usage_ratio(messages) < self._prune_at:
            return None
        current = messages
        changed = False
        pruned_messages, pruned = prune_tool_results(current)
        if pruned:
            current, changed = pruned_messages, True
        if self.usage_ratio(current) >= self._compact_at:
            outcome = await compact_messages(
                current,
                compactor=self._compactor,
                summarizer=self._summarizer,
                keep_turns=self._keep_turns,
            )
            if outcome is not None:
                current, changed = outcome.messages, True
                if self._on_compact is not None:
                    self._on_compact(outcome)
        if changed and self._on_replace is not None:
            self._on_replace(current)
        return current if changed else None

