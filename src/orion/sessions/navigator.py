"""
O.R.I.O.N — Navegação entre daily e threads (v0.5.3 Sprint 3, ADR-051)

Decide para onde a conversa vai, sem tocar na sessão viva: a ``AgentSession`` aplica o
``SessionSwitch`` devolvido (id, histórico, semente a gravar, mensagens a acrescentar).

- Daily: ``daily_switch`` anexa à daily do dia; a semente é o resumo curto da anterior.
- Thread: registrada no índice no primeiro pedido, com evento-link na daily.
- ``branch``: thread filha com contexto mínimo (últimos 2 turnos + resumo).
- ``find``: sessão por id, título ou data (``session_switch``, ``/resume <filtro>``).
- ``merge``: fecha a thread filha com checkpoint e volta ao pai só com ele (substitui o
  ``BranchManager`` em RAM da v0.2.0).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from orion.gateway.models import LLMMessage, MessageRole
from orion.sessions.clock import day_of_daily
from orion.sessions.daily import DailyBook, daily_title
from orion.sessions.index import SessionIndex, SessionKind, SessionRecord, provisional_title
from orion.sessions.query import SessionQuery, parse_query
from orion.sessions.store import JsonlSessionStore, SessionNotFoundError
from orion.sessions.transcript import TranscriptEntry, replay, user_turns
from orion.timeline.autocompact import turn_starts
from orion.timeline.checkpoint_synthesis import synthesize_checkpoint

#: Pedidos anteriores citados no resumo da semente de uma thread.
_SEED_PREVIEWS = 8


@dataclass
class SessionSwitch:
    """Troca de sessão a aplicar na ``AgentSession``."""

    session_id: str
    kind: SessionKind
    daily_id: str | None
    parent_id: str | None
    history: list[LLMMessage]
    notice: str
    seed: list[LLMMessage] | None = None  # gravada como ``compact`` no transcript novo
    append: list[LLMMessage] = field(default_factory=list)  # gravadas como mensagens depois
    follow_today: bool = False  # a daily acompanha a virada do dia


def _pair(text: str) -> list[LLMMessage]:
    return [
        LLMMessage(role=MessageRole.USER, content=text),
        LLMMessage(role=MessageRole.ASSISTANT, content="Entendido."),
    ]


class SessionNavigator:
    """Índice + store + daily: o mapa das sessões do Senhor."""

    def __init__(self, index: SessionIndex, store: JsonlSessionStore, workspace: Path, user_home: Path) -> None:
        self.index = index
        self.store = store
        self.dailies = DailyBook(index, store)
        self.workspace = workspace.resolve()
        self.user_home = user_home.resolve()

    @property
    def in_home(self) -> bool:
        return self.workspace == self.user_home

    @property
    def workspace_label(self) -> str | None:
        """Workspace gravado nas threads (None em ``~``: a vida, não um projeto)."""
        return None if self.in_home else str(self.workspace)

    def _history(self, session_id: str) -> tuple[list[LLMMessage], int]:
        try:
            entries = self.store.load(session_id)
        except SessionNotFoundError:
            return [], 0
        return replay(entries), len(user_turns(entries))

    # ── Daily ──

    def daily_switch(self) -> SessionSwitch:
        state = self.dailies.ensure()
        today = state.today
        history, turns = self._history(today.id)
        seed: list[LLMMessage] | None = None
        if not history and today.opening:
            seed = _pair(f"Resumo da daily anterior (contexto, não é um pedido):\n{today.opening}")
            history = list(seed)
        if turns:
            notice = f"{daily_title(today.id)}: {turns} pedido(s)."
        elif seed:
            notice = f"{daily_title(today.id)} aberta com o resumo da anterior."
        else:
            notice = f"{daily_title(today.id)} aberta."
        return SessionSwitch(
            session_id=today.id,
            kind="daily",
            daily_id=today.id,
            parent_id=None,
            history=history,
            notice=notice,
            seed=seed,
            follow_today=True,
        )

    # ── Registro por turno ──

    def ensure_registered(
        self, session_id: str, *, kind: SessionKind, daily_id: str, parent_id: str | None, first_text: str
    ) -> SessionRecord:
        """Thread nasce no índice no primeiro pedido e ganha um evento-link na daily."""
        existing = self.index.get(session_id)
        if existing is not None:
            return existing
        record = self.index.register(
            session_id,
            kind,
            daily_id=daily_id,
            parent_id=parent_id,
            workspace=self.workspace_label if kind == "thread" else None,
        )
        if kind == "thread":
            self._link(daily_id, record, provisional_title(first_text))
        return record

    def _link(self, daily_id: str, record: SessionRecord, title: str) -> None:
        self.store.append_event(
            daily_id,
            TranscriptEntry.of_meta(
                event="thread_opened",
                thread_id=record.id,
                title=title,
                workspace=record.workspace or "",
                parent_id=record.parent_id or "",
            ),
        )

    # ── Thread a partir da conversa (session_branch, /branch) ──

    def branch(
        self, title: str, reason: str, *, origin_id: str, history: list[LLMMessage]
    ) -> SessionSwitch:
        title = provisional_title(title) or "Thread"
        today = self.dailies.ensure().today
        origin = self.index.get(origin_id)
        starts = turn_starts(history)
        cut = starts[-2] if len(starts) >= 2 else (starts[0] if starts else len(history))
        earlier, tail = history[:cut], history[cut:]
        previews = [
            " ".join(earlier[i].text.split())[:80] for i in turn_starts(earlier) if earlier[i].text.strip()
        ][-_SEED_PREVIEWS:]
        origin_name = origin.display_title if origin else origin_id[:8]
        lines = [f"Thread '{title}' aberta a partir de '{origin_name}'."]
        if reason:
            lines.append(f"Motivo: {reason}")
        if previews:
            lines.append("Antes disso, na conversa de origem: " + "; ".join(previews))
        seed = _pair("\n".join(lines)) + list(tail)
        thread_id = str(uuid.uuid4())
        record = self.index.register(
            thread_id,
            "thread",
            title=title,
            daily_id=today.id,
            parent_id=origin_id,
            workspace=self.workspace_label,
            turn_count=len(turn_starts(tail)),
        )
        self._link(today.id, record, title)
        return SessionSwitch(
            session_id=thread_id,
            kind="thread",
            daily_id=today.id,
            parent_id=origin_id,
            history=list(seed),
            notice=f"Thread '{title}' aberta ({thread_id[:8]}).",
            seed=seed,
        )

    # ── Achar e voltar ──

    def candidates(self, text: str, *, exclude: str | None = None, limit: int = 5) -> list[SessionRecord]:
        """Sessões que casam com id/prefixo ou com o filtro (nome e data)."""
        token = text.strip()
        if token and " " not in token:
            ids = self.index.resolve(token)
            if len(ids) == 1:
                record = self.index.get(ids[0])
                if record is not None and record.id != exclude:
                    return [record]
        query = self.parse(token)
        found = [r for r in self.index.search(query, limit=limit + 1) if r.id != exclude]
        return found[:limit]

    def parse(self, text: str) -> SessionQuery:
        today = day_of_daily(self.dailies.today_id())
        assert today is not None
        return parse_query(text, today, self.workspace)

    def switch_to(self, record: SessionRecord) -> SessionSwitch:
        history, turns = self._history(record.id)
        today_id = self.dailies.today_id()
        return SessionSwitch(
            session_id=record.id,
            kind=record.kind,
            daily_id=record.daily_id,
            parent_id=record.parent_id,
            history=history,
            notice=f"Sessão '{record.display_title}' retomada: {turns} pedido(s).",
            follow_today=record.id == today_id,
        )

    def find(self, text: str, *, current: str) -> tuple[SessionSwitch, list[SessionRecord]]:
        """Melhor sessão para ``text`` (a mais recente que casa) e as demais candidatas."""
        found = self.candidates(text, exclude=current)
        if not found:
            raise LookupError(f"nenhuma sessão casa com '{text}'.")
        return self.switch_to(found[0]), found[1:]

    # ── /merge ──

    def merge(self, current: str, outcome: str) -> tuple[str, SessionSwitch]:
        record = self.index.get(current)
        if record is None or not record.parent_id:
            raise ValueError("Não há o que mesclar: esta sessão não é uma thread aberta por /branch.")
        try:
            entries = self.store.load(current)
        except SessionNotFoundError:
            entries = []
        actions = [t.preview for t in user_turns(entries)]
        files = sorted({e.file.path for e in entries if e.kind == "file_change" and e.file is not None})
        checkpoint = synthesize_checkpoint(
            branch_name=record.display_title, actions_summary=actions[:10], modified_files=files, outcome=outcome
        )
        self.index.close_session(current, card={"checkpoint": checkpoint, "actions": actions[:10], "files": files})
        parent = self.index.get(record.parent_id)
        history, _turns = self._history(record.parent_id)
        extra = _pair(f"Checkpoint da thread '{record.display_title}':\n{checkpoint}")
        switch = SessionSwitch(
            session_id=record.parent_id,
            kind=parent.kind if parent else "thread",
            daily_id=parent.daily_id if parent else record.daily_id,
            parent_id=parent.parent_id if parent else None,
            history=history + extra,
            notice=f"De volta a '{parent.display_title if parent else record.parent_id[:8]}'.",
            append=extra,
            follow_today=bool(parent and parent.kind == "daily" and parent.id == self.dailies.today_id()),
        )
        return checkpoint, switch
