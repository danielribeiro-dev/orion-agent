"""Saída de uma sessão desacoplada do terminal (ADR-032).

A :class:`~orion.tui.session.AgentSession` só fala com um :class:`SessionSink`:

* :data:`RichSink` é o ``StreamRenderer`` de sempre (terminal, Rich Live);
* :class:`IpcSink` transforma cada chamada num evento JSON que o daemon publica para os clientes
  anexados (``orion-agent attach``, futuramente a aba e a voz);
* :class:`NullSink` descarta tudo (sessões sem ninguém olhando, testes).

O cliente reconstrói a tela aplicando os eventos num ``RichSink`` local com :func:`apply_sink_event`,
então a TUI anexada é exatamente a mesma TUI local. Os pensamentos (``add_reasoning``) só saem
pelo IPC com ``ui.show_thinking`` ligado (ADR-034).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any, Protocol, runtime_checkable

from orion.tui.diff_viewer import DiffHunk, DiffLine, FileDiff
from orion.tui.stream_renderer import StreamRenderer

#: O sink de terminal é o próprio renderer do turno.
RichSink = StreamRenderer

SINK_EVENT = "sink"

#: Métodos que atravessam o IPC (o restante é estado local do terminal).
SINK_METHODS: frozenset[str] = frozenset(
    {
        "begin_thinking",
        "add_reasoning",
        "add_text",
        "end_message",
        "tool_started",
        "tool_finished",
        "agent_line",
        "warn",
        "error",
        "close",
    }
)


@runtime_checkable
class SessionSink(Protocol):
    """Tudo o que uma sessão emite durante um turno."""

    def begin_thinking(self) -> None: ...

    def add_reasoning(self, delta: str) -> None: ...

    def add_text(self, delta: str) -> None: ...

    def end_message(self) -> None: ...

    def tool_started(self, tool: str, params: dict[str, Any], key: str = "") -> None: ...

    def tool_finished(
        self,
        tool: str,
        success: bool,
        output: str = "",
        metadata: dict[str, Any] | None = None,
        diff: FileDiff | None = None,
        key: str = "",
    ) -> None: ...

    def agent_line(self, text: str, *, style: str = "text_dim") -> None: ...

    def warn(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...

    def close(self) -> None: ...


class NullSink:
    """Descarta a saída; guarda avisos e erros para quem quiser inspecionar."""

    def __init__(self) -> None:
        self.text = ""
        self.notices: list[str] = []

    def begin_thinking(self) -> None:
        return None

    def add_reasoning(self, delta: str) -> None:
        return None

    def add_text(self, delta: str) -> None:
        self.text += delta

    def end_message(self) -> None:
        return None

    def tool_started(self, tool: str, params: dict[str, Any], key: str = "") -> None:
        return None

    def tool_finished(
        self,
        tool: str,
        success: bool,
        output: str = "",
        metadata: dict[str, Any] | None = None,
        diff: FileDiff | None = None,
        key: str = "",
    ) -> None:
        return None

    def agent_line(self, text: str, *, style: str = "text_dim") -> None:
        self.notices.append(text)

    def warn(self, message: str) -> None:
        self.notices.append(f"! {message}")

    def error(self, message: str) -> None:
        self.notices.append(f"✖ {message}")

    def pause(self) -> None:
        return None

    def resume(self) -> None:
        return None

    def close(self) -> None:
        return None


Publish = Callable[[dict[str, Any]], None]

_MAX_OUTPUT_CHARS = 20_000


def _diff_to_json(diff: FileDiff) -> dict[str, Any]:
    return asdict(diff)


def _diff_from_json(data: dict[str, Any]) -> FileDiff:
    hunks = [
        DiffHunk(header=str(h.get("header", "")), lines=[DiffLine(**ln) for ln in h.get("lines", [])])
        for h in data.get("hunks", [])
    ]
    return FileDiff(path=str(data.get("path", "")), hunks=hunks)


class IpcSink:
    """Serializa cada chamada como evento ``{"kind": "sink", "method": ..., "args": {...}}``.

    ``publish`` é chamado de forma síncrona; o servidor do daemon enfileira para os clientes.
    """

    def __init__(self, publish: Publish, *, show_thinking: bool = False) -> None:
        self._publish = publish
        self.show_thinking = show_thinking

    def _emit(self, method: str, **args: Any) -> None:
        self._publish({"kind": SINK_EVENT, "method": method, "args": args})

    def begin_thinking(self) -> None:
        self._emit("begin_thinking")

    def add_reasoning(self, delta: str) -> None:
        if self.show_thinking:  # canal de pensamentos é opt-in (ADR-034)
            self._emit("add_reasoning", delta=delta)

    def add_text(self, delta: str) -> None:
        self._emit("add_text", delta=delta)

    def end_message(self) -> None:
        self._emit("end_message")

    def tool_started(self, tool: str, params: dict[str, Any], key: str = "") -> None:
        self._emit("tool_started", tool=tool, params=_jsonable(params), key=key)

    def tool_finished(
        self,
        tool: str,
        success: bool,
        output: str = "",
        metadata: dict[str, Any] | None = None,
        diff: FileDiff | None = None,
        key: str = "",
    ) -> None:
        self._emit(
            "tool_finished",
            tool=tool,
            success=success,
            output=output[:_MAX_OUTPUT_CHARS],
            metadata=_jsonable(metadata or {}),
            diff=_diff_to_json(diff) if diff is not None else None,
            key=key,
        )

    def agent_line(self, text: str, *, style: str = "text_dim") -> None:
        self._emit("agent_line", text=text, style=style)

    def warn(self, message: str) -> None:
        self._emit("warn", message=message)

    def error(self, message: str) -> None:
        self._emit("error", message=message)

    def pause(self) -> None:
        return None  # pausa é estado do terminal do cliente

    def resume(self) -> None:
        return None

    def close(self) -> None:
        self._emit("close")


def _jsonable(value: Any) -> Any:
    """Converte para algo que ``json.dumps`` aceita (o resto vira ``str``)."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def apply_sink_event(sink: SessionSink, event: dict[str, Any]) -> bool:
    """Reaplica num sink local um evento produzido por :class:`IpcSink`.

    Devolve ``False`` (sem efeito) para eventos que não são de sink ou métodos desconhecidos:
    o cliente nunca executa nada além da lista fechada :data:`SINK_METHODS`.
    """
    if event.get("kind") != SINK_EVENT:
        return False
    method = event.get("method")
    if not isinstance(method, str) or method not in SINK_METHODS:
        return False
    args = dict(event.get("args") or {})
    if method == "tool_finished":
        raw = args.get("diff")
        args["diff"] = _diff_from_json(raw) if isinstance(raw, dict) else None
    try:
        getattr(sink, method)(**args)
    except TypeError:
        return False
    return True
